"""Anthropic Messages API proxy handler."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
import re
from typing import AsyncGenerator, Any, Optional

import httpx
from fastapi.responses import StreamingResponse

from ..key_manager import KeyManager, retry_with_backoff
from ..logger import RequestLogger
from ..models import AppConfig
from ..router import ModelRouter
from ..stats import StatsTracker, estimate_cost, extract_anthropic_token_usage
from .streaming import extract_stream_usage
from .streaming import stream_anthropic_response

logger = logging.getLogger("monorelay.anthropic_proxy")

def _extract_preview(content: str = "", reasoning: str = "") -> str:
    """Extract content and thinking into a unified preview string."""
    thinking = reasoning.strip() if reasoning else ""
    main_content = content.strip() if content else ""
    if not thinking and "<thought>" in main_content:
        match = re.search(r'<thought>(.*?)</thought>', main_content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            main_content = main_content.replace(match.group(0), "").strip()
    parts = []
    if thinking: parts.append(f"[Thinking]\n{thinking}")
    if main_content: parts.append(main_content)
    return "\n\n---\n\n".join(parts) if parts else ""

def openai_to_anthropic(openai_body: dict) -> dict:
    anthropic_body = {"model": openai_body.get("model"), "max_tokens": openai_body.get("max_tokens", 4096)}
    if "temperature" in openai_body: anthropic_body["temperature"] = openai_body["temperature"]
    if "top_p" in openai_body: anthropic_body["top_p"] = openai_body["top_p"]
    if "stream" in openai_body: anthropic_body["stream"] = openai_body["stream"]
    openai_messages = openai_body.get("messages", [])
    anthropic_messages = []
    system_parts = []
    for msg in openai_messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            if isinstance(content, str): system_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text": system_parts.append(part.get("text", ""))
        else:
            role_map = {"user": "user", "assistant": "assistant", "function": "user", "tool": "user"}
            anthropic_messages.append({"role": role_map.get(role, "user"), "content": content})
    if system_parts: anthropic_body["system"] = "\n".join(system_parts)
    if anthropic_messages:
        merged = []
        for msg in anthropic_messages:
            if not merged or merged[-1]["role"] != msg["role"]: merged.append(msg)
            else:
                p, c = merged[-1]["content"], msg["content"]
                if isinstance(p, str) and isinstance(c, str): merged[-1]["content"] = p + "\n\n" + c
                else:
                    pl = p if isinstance(p, list) else [{"type": "text", "text": p}]
                    cl = c if isinstance(c, list) else [{"type": "text", "text": c}]
                    merged[-1]["content"] = pl + cl
        if merged and merged[0]["role"] == "assistant": merged.insert(0, {"role": "user", "content": "(empty)"})
        anthropic_body["messages"] = merged
    if "tools" in openai_body:
        anthropic_tools = []
        for tool in openai_body["tools"]:
            if tool.get("type") == "function":
                f = tool.get("function", {})
                anthropic_tools.append({"name": f.get("name"), "description": f.get("description", ""), "input_schema": f.get("parameters", {"type": "object", "properties": {}})})
        if anthropic_tools: anthropic_body["tools"] = anthropic_tools
    return anthropic_body

def anthropic_to_openai(anthropic_resp: dict, model: str) -> dict:
    content_text = ""
    reasoning_text = ""
    for part in anthropic_resp.get("content", []):
        if part.get("type") == "text": content_text += part.get("text", "")
        elif part.get("type") == "thinking": reasoning_text += part.get("thinking", "")
    choices = [{"index": 0, "message": {"role": "assistant", "content": content_text, "reasoning_content": reasoning_text}, "finish_reason": "stop" if anthropic_resp.get("stop_reason") == "end_turn" else anthropic_resp.get("stop_reason")}]
    usage = anthropic_resp.get("usage", {})
    return {"id": anthropic_resp.get("id", f"chatcmpl-{uuid.uuid4()}"), "object": "chat.completion", "created": int(time.time()), "model": model, "choices": choices, "usage": {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0), "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)}}

async def _stream_anthropic_to_openai(anthropic_gen, model):
    stream_id, created = f"chatcmpl-{uuid.uuid4()}", int(time.time())
    async for chunk in anthropic_gen:
        try:
            line = chunk.decode("utf-8", errors="replace")
            for l in line.split("\n"):
                if not l.startswith("data: "): continue
                data = json.loads(l[6:])
                t = data.get("type")
                if t == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text":
                        yield f"data: {json.dumps({'id': stream_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'content': delta.get('text', '')}, 'finish_reason': None}]})}\n\n".encode()
                    elif delta.get("type") == "thinking_delta":
                        yield f"data: {json.dumps({'id': stream_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'reasoning_content': delta.get('thinking', '')}, 'finish_reason': None}]})}\n\n".encode()
                elif t == "message_stop":
                    yield f"data: {json.dumps({'id': stream_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n".encode()
                    yield b"data: [DONE]\n\n"
        except Exception: continue

async def handle_openai_to_anthropic(body, config, key_manager, router, request_logger, stats_tracker):
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model, body.get("messages", []))
    anthropic_body = openai_to_anthropic(body)
    anthropic_body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": "No keys", "type": "no_keys"}}
    url, headers = f"{provider_cfg.base_url}/v1/messages", {"x-api-key": key.key.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if provider_cfg.headers: headers.update(provider_cfg.headers)
    start_time = time.time()
    if body.get("stream"):
        async def gen():
            content, thinking = [], []
            async for chunk in _stream_anthropic_to_openai(_stream_messages(provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker), original_model):
                yield chunk
                try:
                    line = chunk.decode("utf-8", errors="replace")
                    for l in line.split("\n"):
                        if l.startswith("data: ") and l[6:] != "[DONE]":
                            data = json.loads(l[6:])
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta: content.append(delta["content"])
                                if "reasoning_content" in delta: thinking.append(delta["reasoning_content"])
                except Exception: pass
            preview = _extract_preview("".join(content), "".join(thinking))
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=200, latency_ms=round((time.time()-start_time)*1000,2), response_preview=preview, streaming=True)
        return StreamingResponse(gen(), media_type="text/event-stream")
    else:
        res = await _non_stream_messages(provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker)
        if "error" in res: return res
        out = anthropic_to_openai(res, original_model)
        msg = out["choices"][0]["message"]
        preview = _extract_preview(msg.get("content", ""), msg.get("reasoning_content", ""))
        await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=200, latency_ms=round((time.time()-start_time)*1000,2), response_preview=preview)
        return out

async def handle_messages(body, config, key_manager, router, request_logger, stats_tracker):
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model, body.get("messages", []))
    body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    if provider_cfg.provider_type == "api": return await handle_anthropic_to_openai(body, config, key_manager, router, request_logger, stats_tracker)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    url, headers = f"{provider_cfg.base_url}/v1/messages", {"x-api-key": key.key.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if provider_cfg.headers: headers.update(provider_cfg.headers)
    start_time = time.time()
    if body.get("stream"):
        return StreamingResponse(_stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker), media_type="text/event-stream")
    return await _non_stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker)

async def _stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker):
    content, thinking = [], []
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    err = await resp.aread()
                    yield f"event: error\ndata: {err.decode()}\n\n".encode()
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk
                    try:
                        line = chunk.decode("utf-8", errors="replace")
                        for l in line.split("\n"):
                            if l.startswith("data: "):
                                data = json.loads(l[6:])
                                if data.get("type") == "content_block_delta":
                                    d = data.get("delta", {})
                                    if d.get("type") == "text_delta": content.append(d.get("text", ""))
                                    elif d.get("type") == "thinking_delta": thinking.append(d.get("thinking", ""))
                    except Exception: pass
            key_manager.report_success(key, 0)
            preview = _extract_preview("".join(content), "".join(thinking))
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=200, latency_ms=round((time.time()-start_time)*1000,2), response_preview=preview, streaming=True)
        except Exception as e: yield f"event: error\ndata: {str(e)}\n\n".encode()

async def _non_stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker):
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 400: return resp.json()
            key_manager.report_success(key, 0)
            res = resp.json()
            content_text, thinking_text = "", ""
            for p in res.get("content", []):
                if p.get("type") == "text": content_text += p.get("text", "")
                elif p.get("type") == "thinking": thinking_text += p.get("thinking", "")
            preview = _extract_preview(content_text, thinking_text)
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=200, latency_ms=round((time.time()-start_time)*1000,2), response_preview=preview)
            return res
        except Exception as e: return {"error": {"message": str(e)}}

async def handle_anthropic_models(config, key_manager, request_logger, stats_tracker):
    return {"object": "list", "data": []} # Simplified for stub completion

async def handle_anthropic_messages_beta(body, config, key_manager, router, request_logger, stats_tracker):
    return await handle_messages(body, config, key_manager, router, request_logger, stats_tracker)
