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
from ..stats import estimate_cost, extract_anthropic_token_usage
from .streaming import stream_anthropic_response

logger = logging.getLogger("prisma.anthropic_proxy")


async def handle_messages(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
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
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
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
                resolved_model, original_model, request_logger, start_time,
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
            resolved_model, original_model, request_logger, start_time,
        )


async def _stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time,
) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            async for chunk in stream_anthropic_response(client, url, headers, body, provider_cfg.timeout):
                yield chunk

            key_manager.report_success(key)
            elapsed = time.time() - start_time
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
            )
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            elapsed = time.time() - start_time
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=500,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                error_message=str(e),
            )
            event_data = json.dumps({"type": "error", "error": {"message": str(e), "type": "proxy_error"}})
            yield f"event: error\ndata: {event_data}\n\n".encode()


async def _non_stream_messages(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time,
) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time

            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                await request_logger.log_request(
                    model=resolved_model,
                    provider=provider_name,
                    key_label=key.key.label,
                    status_code=resp.status_code,
                    latency_ms=round(elapsed * 1000, 2),
                    error_message=resp.text,
                )
                return resp.json()

            key_manager.report_success(key)
            result = resp.json()
            tokens_in, tokens_out = extract_anthropic_token_usage(result)
            cost = estimate_cost(resolved_model, tokens_in or 0, tokens_out or 0) if tokens_in and tokens_out else None

            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                estimated_cost=cost,
            )
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            elapsed = time.time() - start_time
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=500,
                latency_ms=round(elapsed * 1000, 2),
                error_message=str(e),
            )
            return {"error": {"message": str(e), "type": "proxy_error"}}
