"""Anthropic Messages API proxy handler."""
from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator

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
                                    except Exception:
                                        pass

            key_manager.report_success(key)
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

            key_manager.report_success(key)
            result = resp.json()
            tokens_in, tokens_out = extract_anthropic_token_usage(result)
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
            )
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            logger.error(f"Anthropic失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            return {"error": {"message": str(e), "type": "proxy_error"}}
