"""Anthropic Messages API proxy handler."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
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
        import re
        match = re.search(r'<thought>(.*?)</thought>', main_content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            main_content = main_content.replace(match.group(0), "").strip()
    parts = []
    if thinking: parts.append(f"[Thinking]\n{thinking}")
    if main_content: parts.append(main_content)
    return "\n\n---\n\n".join(parts) if parts else ""



def openai_to_anthropic(openai_body: dict) -> dict:
    """Convert OpenAI Chat Completions request to Anthropic Messages request."""
    anthropic_body = {
        "model": openai_body.get("model"),
        "max_tokens": openai_body.get("max_tokens", 4096),
    }

    if "temperature" in openai_body:
        anthropic_body["temperature"] = openai_body["temperature"]
    if "top_p" in openai_body:
        anthropic_body["top_p"] = openai_body["top_p"]
    if "stream" in openai_body:
        anthropic_body["stream"] = openai_body["stream"]

    # Handle messages and system prompt
    openai_messages = openai_body.get("messages", [])
    anthropic_messages = []
    system_parts = []

    for msg in openai_messages:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        system_parts.append(part.get("text", ""))
        else:
            # Anthropic only supports 'user' and 'assistant' roles
            role_map = {"user": "user", "assistant": "assistant", "function": "user", "tool": "user"}
            anthropic_role = role_map.get(role, "user")
            
            anthropic_messages.append({
                "role": anthropic_role,
                "content": content
            })

    if system_parts:
        anthropic_body["system"] = "\n".join(system_parts)
    
    if anthropic_messages:
        merged_messages = []
        for msg in anthropic_messages:
            if not merged_messages or merged_messages[-1]["role"] != msg["role"]:
                merged_messages.append(msg)
            else:
                prev_content = merged_messages[-1]["content"]
                curr_content = msg["content"]
                
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged_messages[-1]["content"] = prev_content + "\n" + curr_content
                elif isinstance(prev_content, list) or isinstance(curr_content, list):
                    p_list = prev_content if isinstance(prev_content, list) else [{"type": "text", "text": prev_content}]
                    c_list = curr_content if isinstance(curr_content, list) else [{"type": "text", "text": curr_content}]
                    merged_messages[-1]["content"] = p_list + c_list
        
        if merged_messages and merged_messages[0]["role"] == "assistant":
            merged_messages.insert(0, {"role": "user", "content": "(empty)"})
            
        anthropic_body["messages"] = merged_messages
    else:
        anthropic_body["messages"] = []

    return anthropic_body


def anthropic_to_openai(anthropic_resp: dict, model: str) -> dict:
    """Convert Anthropic Messages response to OpenAI Chat Completions response."""
    choices = []
    content_text = ""
    reasoning_text = ""
    for part in anthropic_resp.get("content", []):
        if part.get("type") == "text": content_text += part.get("text", "")
        elif part.get("type") == "thinking": reasoning_text += part.get("thinking", "")
    
    choices.append({
        "index": 0,
        "message": {"role": "assistant", "content": content_text, "reasoning_content": reasoning_text},
        "finish_reason": "stop" if anthropic_resp.get("stop_reason") == "end_turn" else anthropic_resp.get("stop_reason"),
    })

    usage = anthropic_resp.get("usage", {})
    return {
        "id": anthropic_resp.get("id", f"chatcmpl-{uuid.uuid4()}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            "prompt_cache_hit_tokens": usage.get("cache_read_input_tokens", 0),
            "prompt_cache_miss_tokens": usage.get("cache_creation_input_tokens", 0),
        }
    }


async def handle_anthropic_to_openai(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
    client_ip: str | None = None,
    user_agent: str | None = None,
    downstream_request: str | None = None,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])
    resolved_model, provider_name = router.resolve_model(original_model, messages)
    anthropic_body = openai_to_anthropic(body)
    anthropic_body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled: return {"error": {"message": "Provider disabled"}}
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": "No keys"}}
    url = f"{provider_cfg.base_url}/v1/messages"
    headers = {"x-api-key": key.key.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if provider_cfg.headers: headers.update(provider_cfg.headers)
    start_time = time.time()
    if body.get("stream"):
        from .openai_format import _stream_chat, _stream_anthropic_to_openai
        async def wrapped_gen():
            openai_gen = _stream_chat(provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=body, config=config)
            async for chunk in _stream_anthropic_to_openai(openai_gen, original_model): yield chunk
        return StreamingResponse(wrapped_gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
    else:
        from .openai_format import _non_stream_chat
        result = await _non_stream_chat(provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=body, client_ip=client_ip, user_agent=user_agent, downstream_request=downstream_request)
        return anthropic_to_openai(result, original_model)


async def handle_messages(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
    client_ip: str | None = None,
    user_agent: str | None = None,
    downstream_request: str | None = None,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])
    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled: return {"error": {"message": f"Provider disabled"}}
    if provider_cfg.provider_type == "api": return await handle_anthropic_to_openai(body, config, key_manager, router, request_logger, stats_tracker, client_ip, user_agent, downstream_request)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": "No available keys"}}
    url = f"{provider_cfg.base_url}/v1/messages"
    headers = {"x-api-key": key.key.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if provider_cfg.headers: headers.update(provider_cfg.headers)
    start_time = time.time()
    if body.get("stream"):
        log_id = await request_logger.create_pending(model=resolved_model, provider=provider_name, key_label=key.key.label, client_ip=client_ip, user_agent=user_agent, downstream_request=downstream_request, streaming=True)
        return StreamingResponse(_stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker, log_id=log_id, config=config), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
    else:
        return await _non_stream_messages(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker, client_ip, user_agent, downstream_request)


async def _stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
    log_id=None, config=None,
) -> AsyncGenerator[bytes, None]:
    attempt = 0
    while attempt <= provider_cfg.retry.max_retries:
        try:
            tokens_in, tokens_out, cache_hit, cache_miss = None, None, 0, 0
            stream_chunks, buffer = 0, b""
            output_content, output_thinking = [], []
            first_token_recorded, first_token_ms = False, None
            async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
                async with client.stream("POST", url, headers=headers, json=body, timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as response:
                    if response.status_code >= 400:
                        error_body = await response.aread()
                        yield f"event: error\ndata: {json.dumps({'error': {'message': error_body.decode()}})}\n\n".encode()
                        return
                    last_preview_update = time.time()
                    ttft_timeout = getattr(config.server, "ttft_timeout", 300) if config else 300
                    try:
                        response_iter = response.aiter_bytes()
                        try: first_chunk = await asyncio.wait_for(anext(response_iter), timeout=float(ttft_timeout))
                        except StopAsyncIteration: first_chunk = None
                        if first_chunk:
                            yield first_chunk
                            buffer += first_chunk
                            stream_chunks += 1
                            first_token_ms = (time.time() - start_time) * 1000
                            first_token_recorded = True
                            if log_id: asyncio.ensure_future(request_logger.update_pending(log_id, first_token_ms=first_token_ms))
                        async for chunk in response_iter:
                            if chunk:
                                yield chunk
                                buffer += chunk
                            stream_chunks += 1
                            while b"\n\n" in buffer:
                                event, buffer = buffer.split(b"\n\n", 1)
                                for line in event.decode("utf-8", errors="replace").split("\n"):
                                    if line.startswith("data: "):
                                        try:
                                            data = json.loads(line[6:])
                                            if data.get("type") == "content_block_delta":
                                                d = data.get("delta", {})
                                                if d.get("type") == "text_delta": output_content.append(d.get("text", ""))
                                                elif d.get("type") == "thinking_delta": output_thinking.append(d.get("thinking", ""))
                                            elif data.get("type") == "message_start":
                                                u = data.get("message", {}).get("usage", {})
                                                if u: tokens_in, cache_hit = u.get("input_tokens") or tokens_in, u.get("cache_read_input_tokens") or cache_hit
                                            elif data.get("type") == "message_stop":
                                                u = data.get("message", {}).get("usage", {})
                                                if u: tokens_out, cache_hit, cache_miss = u.get("output_tokens") or tokens_out, u.get("cache_read_input_tokens") or cache_hit, u.get("cache_creation_input_tokens") or cache_miss
                                        except Exception: pass
                            if log_id and (time.time() - last_preview_update > 0.1):
                                preview = _extract_preview("".join(output_content), "".join(output_thinking))
                                if preview: asyncio.ensure_future(request_logger.update_pending(log_id, response_preview=preview[:1000]))
                                last_preview_update = time.time()
                    except asyncio.TimeoutError:
                        error_msg = f"First token timeout after {ttft_timeout}s"
                        if log_id: await request_logger.finalize_pending(log_id, status_code=504, error_message=error_msg)
                        yield f"event: error\ndata: {json.dumps({'error': {'message': error_msg}})}\n\n".encode()
                        return
            elapsed = time.time() - start_time
            full_content, full_thinking = "".join(output_content), "".join(output_thinking)
            response_full_obj = {"type": "message", "role": "assistant", "model": resolved_model, "content": [{"type": "text", "text": full_content}], "usage": {"input_tokens": tokens_in or 0, "output_tokens": tokens_out or 0, "cache_read_input_tokens": cache_hit}}
            if full_thinking: response_full_obj["content"].insert(0, {"type": "thinking", "thinking": full_thinking})
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)
            _log_data = dict(status_code=200, latency_ms=round(elapsed * 1000, 2), first_token_ms=first_token_ms or round(elapsed * 1000, 1), streaming=True, input_tokens=tokens_in, output_tokens=tokens_out, cache_hit_tokens=cache_hit, cache_miss_tokens=cache_miss, response_preview=_extract_preview(full_content, full_thinking)[:1000], request_full=json.dumps(body, ensure_ascii=False, indent=2), response_full=response_full_str, downstream_response=response_full_str)
            if log_id: await request_logger.finalize_pending(log_id, **_log_data)
            stats_tracker.record_request(provider_name, resolved_model, input_tokens=tokens_in, output_tokens=tokens_out, cache_hit_tokens=cache_hit, success=True)
            return
        except Exception as e:
            attempt += 1
            if attempt > provider_cfg.retry.max_retries:
                if log_id: await request_logger.finalize_pending(log_id, status_code=500, error_message=str(e))
                return
            await asyncio.sleep(1)


async def _non_stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
    client_ip=None, user_agent=None, downstream_request=None,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time
            if resp.status_code >= 400: return resp.json()
            result = resp.json()
            tokens_in, tokens_out = extract_anthropic_token_usage(result)
            usage = result.get("usage", {})
            cache_hit, cache_miss = usage.get("cache_read_input_tokens") or 0, usage.get("cache_creation_input_tokens") or 0
            content_text = "".join([p.get("text", "") for p in result.get("content", []) if p.get("type") == "text"])
            thinking_text = "".join([p.get("thinking", "") for p in result.get("content", []) if p.get("type") == "thinking"])
            log_data = dict(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2), first_token_ms=round(elapsed * 1000, 1), input_tokens=tokens_in, output_tokens=tokens_out, cache_hit_tokens=cache_hit, cache_miss_tokens=cache_miss, response_preview=_extract_preview(content_text, thinking_text)[:1000], request_full=json.dumps(body, ensure_ascii=False, indent=2), response_full=json.dumps(result, ensure_ascii=False, indent=2), client_ip=client_ip, user_agent=user_agent, downstream_request=downstream_request, downstream_response=json.dumps(result, ensure_ascii=False))
            await request_logger.log_request(**log_data)
            return result
    except Exception as e: return {"error": {"message": str(e)}}

# Other handlers stubs
async def handle_anthropic_models(*args, **kwargs): pass
async def handle_anthropic_messages_beta(*args, **kwargs): pass
