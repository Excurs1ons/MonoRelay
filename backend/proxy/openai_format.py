"""OpenAI-compatible API proxy handler (OpenRouter, NVIDIA NIM, OpenAI, Web Reverse)."""
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
from ..stats import estimate_cost, extract_token_usage
from ..web_reverse.chatgpt import WebReverseService
from .streaming import stream_openai_response

logger = logging.getLogger("prisma.openai_proxy")


async def handle_chat_completions(
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
        body = router.strip_tools(body)

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    if provider_cfg.provider_type == "web_reverse":
        return await _handle_web_reverse_chat(
            body, provider_cfg, key_manager, provider_name,
            resolved_model, original_model, request_logger, config.key_selection.strategy,
        )

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = f"{provider_cfg.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key.key.key}",
        "Content-Type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        return StreamingResponse(
            _stream_chat(
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
        return await _non_stream_chat(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time,
        )


async def handle_completions(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = f"{provider_cfg.base_url}/completions"
    headers = {
        "Authorization": f"Bearer {key.key.key}",
        "Content-Type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    is_stream = body.get("stream", False)
    start_time = time.time()

    if is_stream:
        return StreamingResponse(
            _stream_completion(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        return await _non_stream_completion(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time,
        )


async def handle_embeddings(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
) -> dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    headers = {
        "Authorization": f"Bearer {key.key.key}",
        "Content-Type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    start_time = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(
                f"{provider_cfg.base_url}/embeddings",
                headers=headers,
                json=body,
            )
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                return resp.json()
            key_manager.report_success(key)
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
            )
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def _stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time,
) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            async for chunk in stream_openai_response(client, url, headers, body, provider_cfg.timeout):
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
            err = json.dumps({"error": {"message": str(e), "type": "proxy_error"}})
            yield f"data: {err}".encode() + b"\n\n"
            yield b"data: [DONE]\n\n"


async def _non_stream_chat(
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
            tokens_in, tokens_out = extract_token_usage(result)
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


async def _stream_completion(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time,
) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            async for chunk in stream_openai_response(client, url, headers, body, provider_cfg.timeout):
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
            err = json.dumps({"error": {"message": str(e), "type": "proxy_error"}})
            yield f"data: {err}".encode() + b"\n\n"
            yield b"data: [DONE]\n\n"


async def _non_stream_completion(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time,
) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                return resp.json()
            key_manager.report_success(key)
            result = resp.json()
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
            )
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def handle_models_list(config: AppConfig) -> dict:
    all_models = []
    for name, pc in config.providers.items():
        if not pc.enabled:
            continue
        async with httpx.AsyncClient() as client:
            try:
                key = pc.keys[0].key if pc.keys else None
                if not key:
                    continue
                headers = {"Authorization": f"Bearer {key}"}
                if pc.headers:
                    headers.update(pc.headers)
                resp = await client.get(f"{pc.base_url}/models", headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", data) if isinstance(data, dict) else data
                    for m in models:
                        mid = m.get("id", m) if isinstance(m, dict) else m
                        all_models.append({
                            "id": mid,
                            "provider": name,
                            "object": "model",
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch models from {name}: {e}")

    return {"object": "list", "data": all_models}


async def _handle_web_reverse_chat(
    body: dict,
    provider_cfg,
    key_manager: KeyManager,
    provider_name: str,
    resolved_model: str,
    original_model: str,
    request_logger: RequestLogger,
    key_strategy: str,
) -> StreamingResponse | dict:
    key = key_manager.select_key(provider_name, key_strategy)
    if not key:
        return {"error": {"message": f"No available keys for web_reverse provider '{provider_name}'", "type": "no_keys"}}

    access_token = key.key.key
    wr_config = provider_cfg.web_reverse
    if not wr_config:
        return {"error": {"message": f"Web reverse config missing for '{provider_name}'", "type": "no_config"}}

    service = WebReverseService(provider_name, wr_config.model_dump())
    start_time = time.time()
    is_stream = body.get("stream", False)

    try:
        result = await service.chat_completion(body, access_token, wr_config.history_disabled)

        if is_stream and isinstance(result, AsyncGenerator):
            return StreamingResponse(
                _wrap_web_reverse_stream(
                    result, key, key_manager, provider_name, resolved_model,
                    original_model, request_logger, start_time,
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
        elif isinstance(result, dict) and "error" in result:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return result
        else:
            key_manager.report_success(key)
            elapsed = time.time() - start_time
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
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
        return {"error": {"message": str(e), "type": "web_reverse_error"}}


async def _wrap_web_reverse_stream(
    stream_gen,
    key,
    key_manager: KeyManager,
    provider_name: str,
    resolved_model: str,
    original_model: str,
    request_logger: RequestLogger,
    start_time: float,
) -> AsyncGenerator[bytes, None]:
    async for chunk in stream_gen:
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
