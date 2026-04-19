"""Anthropic Messages API proxy handler."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncGenerator, Any

import httpx
from fastapi.responses import StreamingResponse

from ..key_manager import KeyManager
from ..logger import RequestLogger
from ..models import AppConfig
from ..router import ModelRouter
from ..stats import StatsTracker, estimate_cost, extract_anthropic_token_usage
from .streaming import extract_stream_usage
from .streaming import stream_anthropic_response

logger = logging.getLogger("monorelay.anthropic_proxy")


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
            # Map 'function' or 'tool' (not fully supported here yet) to 'user' if needed
            role_map = {"user": "user", "assistant": "assistant", "function": "user", "tool": "user"}
            anthropic_role = role_map.get(role, "user")
            
            # Simple content conversion (Anthropic supports lists too)
            anthropic_messages.append({
                "role": anthropic_role,
                "content": content
            })

    if system_parts:
        anthropic_body["system"] = "\n".join(system_parts)
    
    # Merge consecutive messages with the same role (Anthropic requirement)
    if anthropic_messages:
        merged_messages = []
        for msg in anthropic_messages:
            if not merged_messages or merged_messages[-1]["role"] != msg["role"]:
                merged_messages.append(msg)
            else:
                # Same role, merge content
                prev_content = merged_messages[-1]["content"]
                curr_content = msg["content"]
                
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged_messages[-1]["content"] = prev_content + "\n\n" + curr_content
                elif isinstance(prev_content, list) or isinstance(curr_content, list):
                    # Convert both to list if they aren't already
                    p_list = prev_content if isinstance(prev_content, list) else [{"type": "text", "text": prev_content}]
                    c_list = curr_content if isinstance(curr_content, list) else [{"type": "text", "text": curr_content}]
                    merged_messages[-1]["content"] = p_list + c_list
        
        # Ensure it starts with 'user'
        if merged_messages and merged_messages[0]["role"] == "assistant":
            merged_messages.insert(0, {"role": "user", "content": "(empty)"})
            
        anthropic_body["messages"] = merged_messages
    else:
        anthropic_body["messages"] = []

    # Tools conversion (Simplified)
    if "tools" in openai_body:
        anthropic_tools = []
        for tool in openai_body["tools"]:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                })
        if anthropic_tools:
            anthropic_body["tools"] = anthropic_tools

    return anthropic_body


def anthropic_to_openai(anthropic_resp: dict, model: str) -> dict:
    """Convert Anthropic Messages response to OpenAI Chat Completions response."""
    choices = []
    
    # Extract content
    content_text = ""
    for part in anthropic_resp.get("content", []):
        if part.get("type") == "text":
            content_text += part.get("text", "")
    
    choices.append({
        "index": 0,
        "message": {
            "role": "assistant",
            "content": content_text,
        },
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
        }
    }


async def _stream_anthropic_to_openai(
    anthropic_gen: AsyncGenerator[bytes, None],
    model: str
) -> AsyncGenerator[bytes, None]:
    """Convert Anthropic SSE stream to OpenAI SSE stream."""
    stream_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())
    
    async for chunk in anthropic_gen:
        chunk_str = chunk.decode("utf-8", errors="replace")
        for line in chunk_str.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            
            try:
                data = json.loads(line[6:])
                event_type = data.get("type")
                
                if event_type == "message_start":
                    # Optionally handle message metadata
                    pass
                elif event_type == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text":
                        text = delta.get("text", "")
                        openai_chunk = {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": text},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(openai_chunk)}\n\n".encode()
                elif event_type == "message_delta":
                    # Handle usage or finish reason if needed
                    usage = data.get("usage", {})
                    if usage:
                        openai_chunk = {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [],
                            "usage": {
                                "prompt_tokens": usage.get("input_tokens", 0),
                                "completion_tokens": usage.get("output_tokens", 0),
                                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                            }
                        }
                        # Some clients expect at least one choice or ignore chunks with usage only
                        # but we can try yielding it.
                        yield f"data: {json.dumps(openai_chunk)}\n\n".encode()
                elif event_type == "message_stop":
                    openai_chunk = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(openai_chunk)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
            except Exception:
                continue


async def handle_openai_to_anthropic(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    """Handle OpenAI-style request by converting it to Anthropic format."""
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])

    resolved_model, provider_name = router.resolve_model(original_model, messages)
    
    # Convert body to Anthropic format
    anthropic_body = openai_to_anthropic(body)
    anthropic_body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = f"{provider_cfg.base_url}/v1/messages"
    headers = {
        "x-api-key": key.key.key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        # We need to wrap the stream to convert it back to OpenAI format
        async def wrapped_gen():
            anthropic_gen = _stream_messages(
                provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker,
            )
            async for chunk in _stream_anthropic_to_openai(anthropic_gen, original_model):
                yield chunk

        return StreamingResponse(
            wrapped_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Prisma-Model": resolved_model,
                "X-Prisma-Provider": provider_name,
            },
        )
    else:
        # Non-stream: call and convert response back
        result = await _non_stream_messages(
            provider_cfg, url, headers, anthropic_body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker,
        )
        if isinstance(result, dict) and "error" in result:
            return result
        
        return anthropic_to_openai(result, original_model)


def anthropic_to_openai_request(anthropic_body: dict) -> dict:
    """Convert Anthropic Messages request to OpenAI Chat Completions request."""
    openai_body = {
        "model": anthropic_body.get("model"),
        "max_tokens": anthropic_body.get("max_tokens"),
        "stream": anthropic_body.get("stream", False),
    }

    if "temperature" in anthropic_body:
        openai_body["temperature"] = anthropic_body["temperature"]
    if "top_p" in anthropic_body:
        openai_body["top_p"] = anthropic_body["top_p"]

    # Handle system prompt
    system_prompt = anthropic_body.get("system")
    openai_messages = []
    if system_prompt:
        if isinstance(system_prompt, str):
            openai_messages.append({"role": "system", "content": system_prompt})
        elif isinstance(system_prompt, list):
            # Anthropic system can be a list of content blocks
            text_content = ""
            for block in system_prompt:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_content += block.get("text", "")
            if text_content:
                openai_messages.append({"role": "system", "content": text_content})

    # Handle messages
    for msg in anthropic_body.get("messages", []):
        role = msg.get("role")
        content = msg.get("content")
        openai_messages.append({"role": role, "content": content})

    openai_body["messages"] = openai_messages

    # Tools conversion
    if "tools" in anthropic_body:
        openai_tools = []
        for tool in anthropic_body["tools"]:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            })
        if openai_tools:
            openai_body["tools"] = openai_tools

    return openai_body


def openai_to_anthropic_response(openai_resp: dict, model: str) -> dict:
    """Convert OpenAI Chat Completions response to Anthropic Messages response."""
    choices = openai_resp.get("choices", [])
    content = []
    stop_reason = "end_turn"
    
    if choices:
        choice = choices[0]
        msg = choice.get("message", {})
        text = msg.get("content", "")
        if text:
            content.append({"type": "text", "text": text})
        
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            stop_reason = "max_tokens"
        elif finish_reason == "tool_calls":
            stop_reason = "tool_use"
        # Map other finish reasons as needed

    usage = openai_resp.get("usage", {})
    
    return {
        "id": openai_resp.get("id", f"msg_{uuid.uuid4()}"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
    }


async def _stream_openai_to_anthropic(
    openai_gen: AsyncGenerator[bytes, None]
) -> AsyncGenerator[bytes, None]:
    """Convert OpenAI SSE stream to Anthropic SSE stream."""
    msg_id = f"msg_{uuid.uuid4()}"
    
    # Send message_start
    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': '', 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n".encode()
    
    # Send content_block_start
    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n".encode()

    async for chunk in openai_gen:
        chunk_str = chunk.decode("utf-8", errors="replace")
        for line in chunk_str.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            
            data_str = line[6:]
            if data_str == "[DONE]":
                continue
                
            try:
                data = json.loads(data_str)
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}})}\n\n".encode()
                
                # Handle usage if present in chunk
                usage = data.get("usage")
                if usage:
                    # We'll send this in message_delta later
                    pass
            except Exception:
                continue

    # Send content_block_stop
    yield b"event: content_block_stop\ndata: {\"type\": \"content_block_stop\", \"index\": 0}\n\n"
    
    # Send message_delta and message_stop
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 0}})}\n\n".encode()
    yield b"event: message_stop\ndata: {\"type\": \"message_stop\"}\n\n"


async def handle_anthropic_to_openai(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    """Handle Anthropic-style request by converting it to OpenAI format."""
    original_model = body.get("model", "unknown")
    
    # Anthropic format uses 'messages' and optionally 'system'
    messages = body.get("messages", [])
    
    resolved_model, provider_name = router.resolve_model(original_model, messages)
    
    # Convert body to OpenAI format
    openai_body = anthropic_to_openai_request(body)
    openai_body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    # Build OpenAI URL
    from .openai_format import _build_url, _build_headers, _stream_chat, _non_stream_chat
    
    url = _build_url(provider_cfg.base_url, "/chat/completions")
    headers = _build_headers(provider_cfg, key.key.key)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        async def wrapped_gen():
            openai_gen = _stream_chat(
                provider_cfg, url, headers, openai_body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker,
            )
            async for chunk in _stream_openai_to_anthropic(openai_gen):
                yield chunk

        return StreamingResponse(
            wrapped_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Prisma-Model": resolved_model,
                "X-Prisma-Provider": provider_name,
            },
        )
    else:
        result = await _non_stream_chat(
            provider_cfg, url, headers, openai_body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker,
        )
        if isinstance(result, dict) and "error" in result:
            return result
        
        return openai_to_anthropic_response(result, original_model)


async def handle_messages(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])

    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model

    if not router.supports_tools(resolved_model):
        body.pop("tools", None)
        body.pop("tool_choice", None)

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    if provider_cfg.provider_type == "api":
        return await handle_anthropic_to_openai(
            body, config, key_manager, router, request_logger, stats_tracker,
        )

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = f"{provider_cfg.base_url}/v1/messages"
    headers = {
        "x-api-key": key.key.key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        return StreamingResponse(
            _stream_messages(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Prisma-Model": resolved_model,
                "X-Prisma-Provider": provider_name,
            },
        )
    else:
        return await _non_stream_messages(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker,
        )


async def _stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            tokens_in = None
            tokens_out = None
            stream_chunks = 0
            buffer = b""

            async with client.stream(
                "POST", url, headers=headers, json=body,
                timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0),
            ) as response:
                if response.status_code >= 400:
                    error_body = await response.aread()
                    error_text = error_body.decode("utf-8", errors="replace")
                    logger.error(f"Anthropic upstream error {response.status_code}: {error_text}")
                    key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                    elapsed = time.time() - start_time
                    await request_logger.log_request(
                        model=resolved_model, provider=provider_name,
                        key_label=key.key.label, status_code=response.status_code,
                        latency_ms=round(elapsed * 1000, 2), streaming=True,
                        error_message=error_text,
                    )
                    stats_tracker.record_request(provider_name, resolved_model, success=False)
                    event_data = json.dumps({"type": "error", "error": {"message": error_text, "type": "upstream_error"}})
                    yield f"event: error\ndata: {event_data}\n\n".encode()
                    return

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
                        buffer += chunk
                        stream_chunks += 1

                        # Parse SSE events for Anthropic message_stop with usage
                        while b"\n\n" in buffer:
                            event, buffer = buffer.split(b"\n\n", 1)
                            for line in event.decode("utf-8", errors="replace").split("\n"):
                                line = line.strip()
                                if line.startswith("data: "):
                                    try:
                                        data = json.loads(line[6:])
                                        if data.get("type") == "message_stop":
                                            usage = data.get("message", {}).get("usage", {})
                                            if usage:
                                                tokens_in = usage.get("input_tokens")
                                                tokens_out = usage.get("output_tokens")
                                        elif data.get("type") == "message_delta":
                                            usage = data.get("usage", {})
                                            if usage:
                                                tokens_in = usage.get("input_tokens") or tokens_in
                                                tokens_out = usage.get("output_tokens") or tokens_out
                                    except Exception:
                                        pass

            tokens_in_calc = int(tokens_in) if tokens_in is not None else 0
            tokens_out_calc = int(tokens_out) if tokens_out is not None else 0
            total_tokens = tokens_in_calc + tokens_out_calc

            key_manager.report_success(key, total_tokens)
            elapsed = time.time() - start_time
            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None

            log_parts = [f"Anthropic流式 | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None: log_parts.append(f"输入token={tokens_in}")
            log_parts.append(f"流式chunk数={stream_chunks}")
            if tokens_out is not None: log_parts.append(f"输出token={tokens_out}")
            total = (tokens_in or 0) + (tokens_out or 0)
            if tokens_in is not None or tokens_out is not None: log_parts.append(f"总token={total}")
            log_parts.append(f"耗时={round(elapsed * 1000, 2)}ms")
            logger.info(" | ".join(log_parts))

            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            )
            stats_tracker.record_request(
                provider_name, resolved_model,
                input_tokens=tokens_in, output_tokens=tokens_out, success=True,
                cost_per_m_input=provider_cfg.cost_per_m_input,
                cost_per_m_output=provider_cfg.cost_per_m_output,
            )
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            elapsed = time.time() - start_time
            logger.error(f"Anthropic流式失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=500,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                error_message=str(e),
            )
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            event_data = json.dumps({"type": "error", "error": {"message": str(e), "type": "proxy_error"}})
            yield f"event: error\ndata: {event_data}\n\n".encode()


async def _non_stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time

            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                logger.error(f"Anthropic错误{resp.status_code} | 模型={resolved_model} | 提供商={provider_name}")
                await request_logger.log_request(
                    model=resolved_model,
                    provider=provider_name,
                    key_label=key.key.label,
                    status_code=resp.status_code,
                    latency_ms=round(elapsed * 1000, 2),
                    error_message=resp.text,
                )
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                return resp.json()

            result = resp.json()
            tokens_in, tokens_out = extract_anthropic_token_usage(result)
            tokens_in_calc = int(tokens_in) if tokens_in is not None else 0
            tokens_out_calc = int(tokens_out) if tokens_out is not None else 0
            total_tokens = tokens_in_calc + tokens_out_calc
            key_manager.report_success(key, total_tokens)
            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None

            log_parts = [f"Anthropic非流式 | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None: log_parts.append(f"输入token={tokens_in}")
            if tokens_out is not None: log_parts.append(f"输出token={tokens_out}")
            total = (tokens_in or 0) + (tokens_out or 0)
            if tokens_in is not None or tokens_out is not None: log_parts.append(f"总token={total}")
            log_parts.append(f"耗时={round(elapsed * 1000, 2)}ms")
            logger.info(" | ".join(log_parts))

            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            )
            stats_tracker.record_request(
                provider_name, resolved_model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                success=True,
                cost_per_m_input=provider_cfg.cost_per_m_input,
                cost_per_m_output=provider_cfg.cost_per_m_output,
            )
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            logger.error(f"Anthropic失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            return {"error": {"message": str(e), "type": "proxy_error"}}
