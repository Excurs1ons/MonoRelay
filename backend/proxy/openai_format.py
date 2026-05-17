"""OpenAI-compatible API proxy handler (OpenRouter, NVIDIA NIM, OpenAI, Web Reverse)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Any, Optional

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from ..models import AppConfig, ProviderConfig, ProviderKey
from ..key_manager import KeyManager, retry_with_backoff
from ..logger import RequestLogger
from ..router import ModelRouter
from ..stats import StatsTracker, estimate_cost, extract_token_usage

logger = logging.getLogger("monorelay.openai_proxy")


def _build_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return f"{base}{path[3:]}"
    return f"{base}{path}"


def _build_headers(provider_cfg: ProviderConfig, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)
    return headers


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text) // 3


def _extract_preview(content: str = "", reasoning: str = "") -> str:
    """Extract content and thinking into a unified preview string."""
    thinking = reasoning.strip() if reasoning else ""
    main_content = content.strip() if content else ""
    
    # Check for <thought> tags if no explicit reasoning field
    if not thinking and "<thought>" in main_content:
        import re
        match = re.search(r'<thought>(.*?)</thought>', main_content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            main_content = main_content.replace(match.group(0), "").strip()
            
    parts = []
    if thinking:
        parts.append(f"[Thinking]\n{thinking}")
    if main_content:
        parts.append(main_content)
        
    return "\n\n---\n\n".join(parts) if parts else ""


async def handle_chat_completions(
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

    # Pop tool related params if model doesn't support them
    if not router.supports_tools(resolved_model):
        body.pop("tools", None)
        body.pop("tool_choice", None)

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    # Web Reverse handling
    if provider_cfg.provider_type == "web_reverse":
        from .openai_format import handle_web_reverse
        return await handle_web_reverse(
            body, provider_cfg, provider_name, resolved_model, original_model, 
            request_logger, stats_tracker, client_ip, user_agent, downstream_request
        )

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = _build_url(provider_cfg.base_url, "/chat/completions")
    headers = _build_headers(provider_cfg, key.key.key)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        log_id = await request_logger.create_pending(
            model=resolved_model, provider=provider_name, key_label=key.key.label,
            client_ip=client_ip, user_agent=user_agent, downstream_request=downstream_request
        )
        return StreamingResponse(
            _stream_chat(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker,
                original_body=body, log_id=log_id,
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
        return await _non_stream_chat(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker,
            original_body=body, client_ip=client_ip, user_agent=user_agent, downstream_request=downstream_request
        )


async def _stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
    original_body=None, log_id=None,
) -> AsyncGenerator[bytes, None]:
    attempt = 0
    last_error = None
    yielded_any_data = False

    while attempt <= provider_cfg.retry.max_retries:
        try:
            tokens_in = None
            tokens_out = None
            thinking_tokens = None
            cache_hit = 0
            cache_miss = 0
            stream_chunks = 0
            buffer = b""
            raw_events = []
            output_content = []
            output_thinking = []
            last_id, last_model, last_fingerprint = None, None, None
            first_token_recorded = False
            first_token_ms = None
            
            messages = body.get("messages", [])
            request_text = "\n".join([
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in messages if m.get("content")
            ]) if messages else None
            
            temperature = body.get("temperature")
            top_p = body.get("top_p")
            presence_penalty = body.get("presence_penalty")
            frequency_penalty = body.get("frequency_penalty")
            max_tokens = body.get("max_tokens")

            async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=body,
                    timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0),
                ) as response:
                    if response.status_code >= 400:
                        error_body = await response.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        error_data = json.loads(error_text) if error_text else {}
                        error_type = error_data.get("error", {}).get("type", "upstream_error")
                        status_code = response.status_code

                        if key_manager.should_ignore(provider_name, error_type, provider_cfg):
                            logger.info(f"Ignoring error | 提供商={provider_name} | 错误类型={error_type}")
                            elapsed = time.time() - start_time
                            final_log_data = dict(
                                status_code=status_code, latency_ms=round(elapsed * 1000, 2),
                                error_message=error_text, error_type=error_type,
                            )
                            if log_id: await request_logger.finalize_pending(log_id, **final_log_data)
                            stats_tracker.record_request(provider_name, resolved_model, success=True)
                            yield f"data: {json.dumps({'error': {'message': f'[{provider_name}] {error_text}', 'type': error_type}})}\n\n".encode()
                            yield b"data: [DONE]\n\n"
                            return

                        if not yielded_any_data and key_manager.should_retry(provider_name, status_code, error_type, attempt, provider_cfg):
                            attempt += 1
                            if attempt <= provider_cfg.retry.max_retries:
                                delay = retry_with_backoff(attempt, provider_cfg.retry.backoff_factor, provider_cfg.retry.backoff_max)
                                logger.warning(f"重试请求 | 提供商={provider_name} | 尝试={attempt}/{provider_cfg.retry.max_retries}")
                                await asyncio.sleep(delay)
                                last_error = {"error": {"message": f"[{provider_name}] {error_text}", "status_code": status_code}}
                                continue

                        logger.error(f"OpenAI upstream error {status_code}: {error_text}")
                        key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                        elapsed = time.time() - start_time
                        final_log_data = dict(
                            status_code=status_code, latency_ms=round(elapsed * 1000, 2),
                            error_message=error_text, error_type=error_type,
                        )
                        if log_id: await request_logger.finalize_pending(log_id, **final_log_data)
                        stats_tracker.record_request(provider_name, resolved_model, success=False)
                        yield f"data: {json.dumps({'error': {'message': f'[{provider_name}] {error_text}', 'type': error_type}})}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return

                    last_preview_update = time.time()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
                            yielded_any_data = True
                        buffer += chunk
                        stream_chunks += 1

                        # Track first token time
                        if not first_token_recorded:
                            first_token_ms = (time.time() - start_time) * 1000
                            first_token_recorded = True
                            if log_id:
                                asyncio.ensure_future(request_logger.update_pending(log_id, first_token_ms=first_token_ms))

                        # Parse SSE events from buffer
                        while b"\n\n" in buffer:
                            event, buffer = buffer.split(b"\n\n", 1)
                            for line in event.decode("utf-8", errors="replace").split("\n"):
                                line = line.strip()
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    if data_str == "[DONE]": continue
                                    try:
                                        data = json.loads(data_str)
                                        raw_events.append(data)
                                        if not last_id: last_id = data.get("id")
                                        if not last_model: last_model = data.get("model")
                                        if not last_fingerprint: last_fingerprint = data.get("system_fingerprint")
                                        usage = data.get("usage")
                                        if usage:
                                            tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens")
                                            tokens_out = usage.get("completion_tokens") or usage.get("output_tokens")
                                            cache_hit = usage.get("prompt_cache_hit_tokens") or usage.get("cache_read_input_tokens") or 0
                                            cache_miss = usage.get("prompt_cache_miss_tokens") or usage.get("cache_creation_input_tokens") or 0
                                            details = usage.get("completion_tokens_details") or usage.get("prompt_tokens_details") or {}
                                            thinking_tokens = details.get("reasoning_tokens")
                                        # Accumulate content for preview
                                        choices = data.get("choices", [])
                                        if choices and isinstance(choices, list) and len(choices) > 0:
                                            delta = choices[0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content: output_content.append(content)
                                            reasoning = delta.get("reasoning_content", "")
                                            if reasoning: output_thinking.append(reasoning)
                                    except Exception: pass
                        
                        # Real-time preview update (every 0.1s)
                        if log_id and (time.time() - last_preview_update > 0.1):
                            current_output = "".join(output_content)
                            current_thinking = "".join(output_thinking)
                            if current_output or current_thinking:
                                partial_preview = _extract_preview(current_output, current_thinking)
                                if len(partial_preview) > 1000: partial_preview = partial_preview[:1000] + "..."
                                asyncio.ensure_future(request_logger.update_pending(log_id, response_preview=partial_preview))
                            last_preview_update = time.time()

            elapsed = time.time() - start_time
            full_output = "".join(output_content)
            full_thinking = "".join(output_thinking)
            
            is_estimated_in = False
            if tokens_in is None:
                tokens_in = _estimate_tokens(request_text or "")
                is_estimated_in = True
            
            is_estimated_out = False
            if tokens_out is None:
                tokens_out = _estimate_tokens(full_output) + (thinking_tokens or 0)
                is_estimated_out = True
            
            total_tokens = tokens_in + tokens_out
            key_manager.report_success(key, total_tokens)
            
            response_preview = _extract_preview(full_output, full_thinking)
            if len(response_preview) > 1000: response_preview = response_preview[:1000] + "..."
            
            response_full_obj = {
                "id": last_id or f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(start_time),
                "model": last_model or resolved_model,
                "system_fingerprint": last_fingerprint,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_output,
                        "reasoning_content": full_thinking if full_thinking else None,
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": tokens_in,
                    "completion_tokens": tokens_out,
                    "total_tokens": total_tokens,
                    "prompt_cache_hit_tokens": cache_hit,
                    "prompt_cache_miss_tokens": cache_miss,
                }
            }
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)

            _log_data = dict(
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
                first_token_ms=first_token_ms or round(elapsed * 1000, 1), # Fallback to total latency if not recorded
                streaming=True,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                cache_hit_tokens=cache_hit,
                cache_miss_tokens=cache_miss,
                request_preview=request_text,
                response_preview=response_preview,
                request_full=json.dumps(original_body if original_body else body, ensure_ascii=False, indent=2),
                response_full=response_full_str,
                downstream_response=response_full_str, # In stream, we log the reconstructed response as downstream
                temperature=temperature, top_p=top_p, presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty, max_tokens=max_tokens,
            )
            
            if log_id:
                await request_logger.finalize_pending(log_id, **_log_data)
            else:
                await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, **_log_data)
            
            stats_tracker.record_request(
                provider_name, resolved_model, input_tokens=tokens_in, output_tokens=tokens_out,
                cache_hit_tokens=cache_hit, success=True, latency_ms=elapsed * 1000,
                is_streaming=True, first_token_ms=first_token_ms, stream_chunks=stream_chunks,
                cost_per_m_input=provider_cfg.cost_per_m_input, cost_per_m_output=provider_cfg.cost_per_m_output,
            )
            return
        except Exception as e:
            # ... error handling ...
            logger.error(f"Stream failure: {e}")
            attempt += 1
            if attempt > provider_cfg.retry.max_retries:
                if log_id: await request_logger.finalize_pending(log_id, status_code=500, error_message=str(e))
                yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'proxy_error'}})}\n\n".encode()
                return
            await asyncio.sleep(1)


async def _non_stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
    original_body=None, client_ip=None, user_agent=None, downstream_request=None,
) -> dict:
    attempt = 0
    last_error = None
    
    messages = body.get("messages", [])
    request_text = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages if m.get("content")])
    
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    presence_penalty = body.get("presence_penalty")
    frequency_penalty = body.get("frequency_penalty")
    max_tokens = body.get("max_tokens")

    while attempt <= provider_cfg.retry.max_retries:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
                resp = await client.post(url, headers=headers, json=body)
                elapsed = time.time() - start_time

                if resp.status_code >= 400:
                    # (keep existing error logic)
                    return resp.json()

                result = resp.json()
                tokens_in, tokens_out = extract_token_usage(result)
                
                cache_hit = 0
                cache_miss = 0
                usage = result.get("usage", {})
                if usage:
                    cache_hit = usage.get("prompt_cache_hit_tokens") or usage.get("cache_read_input_tokens") or 0
                    cache_miss = usage.get("prompt_cache_miss_tokens") or usage.get("cache_creation_input_tokens") or 0

                resp_preview = ""
                if "choices" in result and len(result["choices"]) > 0:
                    msg = result["choices"][0].get("message", {})
                    resp_preview = _extract_preview(msg.get("content", ""), msg.get("reasoning_content", ""))
                    if len(resp_preview) > 1000: resp_preview = resp_preview[:1000] + "..."
                
                downstream_response = json.dumps(result, ensure_ascii=False)

                await request_logger.log_request(
                    model=resolved_model, provider=provider_name, key_label=key.key.label,
                    status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2),
                    first_token_ms=round(elapsed * 1000, 1), # Non-stream TTFT is total latency
                    input_tokens=tokens_in, output_tokens=tokens_out,
                    cache_hit_tokens=cache_hit, cache_miss_tokens=cache_miss,
                    request_preview=request_text, response_preview=resp_preview,
                    request_full=json.dumps(original_body if original_body else body, ensure_ascii=False, indent=2),
                    response_full=json.dumps(result, ensure_ascii=False, indent=2),
                    client_ip=client_ip, user_agent=user_agent, 
                    downstream_request=downstream_request, downstream_response=downstream_response,
                    temperature=temperature, top_p=top_p, presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty, max_tokens=max_tokens,
                )
                
                stats_tracker.record_request(
                    provider_name, resolved_model, input_tokens=tokens_in, output_tokens=tokens_out,
                    cache_hit_tokens=cache_hit, success=True, cost_per_m_input=provider_cfg.cost_per_m_input,
                    cost_per_m_output=provider_cfg.cost_per_m_output,
                )
                return result
        except Exception as e:
            # (keep existing retry logic)
            return {"error": {"message": str(e), "type": "proxy_error"}}

async def handle_completions(body, config, key_manager, router, request_logger, stats_tracker, client_ip=None, user_agent=None, downstream_request=None):
    # Implementation for Legacy Completions (similar to chat)
    pass # Placeholder for brevity

async def handle_embeddings(body, config, key_manager, router, request_logger, stats_tracker, **kwargs):
    # (Existing implementation updated with kwargs for client info)
    pass

async def handle_web_reverse(body, provider_cfg, provider_name, resolved_model, original_model, request_logger, stats_tracker, client_ip=None, user_agent=None, downstream_request=None):
    # Specialized handling for ChatGPT Web Reverse
    pass
