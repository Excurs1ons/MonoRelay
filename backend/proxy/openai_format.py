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
from ..stats import StatsTracker, estimate_cost, extract_token_usage
from ..web_reverse.chatgpt import WebReverseService
from .anthropic_format import handle_messages, handle_openai_to_anthropic
from .streaming import stream_openai_response, extract_stream_usage

logger = logging.getLogger("monorelay.openai_proxy")


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Rules:
    - Chinese characters: 1 char ≈ 1 token
    - English words: 1 word ≈ 1.3 tokens (average)
    - Punctuation/spaces: counted as part of words
    """
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    non_chinese = text.replace(' ', '').replace('\n', '').replace('\t', '')
    # Remove Chinese chars from non_chinese count
    english_chars = len(non_chinese) - sum(1 for c in non_chinese if '\u4e00' <= c <= '\u9fff')
    # Estimate: Chinese = 1 token/char, English = ~1.3 tokens/word (avg 4 chars/word)
    english_tokens = max(1, int(english_chars / 4 * 1.3)) if english_chars > 0 else 0
    return chinese_chars + english_tokens


def _estimate_input_tokens(messages: list) -> int:
    """Estimate input tokens from messages list."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += _estimate_tokens(item["text"])
    # Add overhead for message structure (~3 tokens per message)
    total += len(messages) * 3
    return total


def _build_url(base_url: str, path: str) -> str:
    """Build full URL from base_url and endpoint path.

    If base_url already ends with the path (or a longer path containing it),
    use base_url directly. Otherwise append the path.

    Examples:
        _build_url("https://api.example.com/v1", "/chat/completions")
        -> "https://api.example.com/v1/chat/completions"

        _build_url("https://api.example.com/v1/chat/completions", "/chat/completions")
        -> "https://api.example.com/v1/chat/completions"
    """
    if base_url.endswith(path):
        return base_url
    return f"{base_url}{path}"


def _build_headers(provider_cfg, api_key: str) -> dict[str, str]:
    """Build base headers dict for upstream requests with cloaking support."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider_cfg.headers:
        headers.update(provider_cfg.headers)

    cloaking = provider_cfg.cloaking
    if cloaking:
        cloaking_applied = []
        if cloaking.user_agent:
            headers["User-Agent"] = cloaking.user_agent
            cloaking_applied.append("User-Agent")
        if cloaking.referer:
            headers["Referer"] = cloaking.referer
            cloaking_applied.append("Referer")
        if cloaking.origin:
            headers["Origin"] = cloaking.origin
            cloaking_applied.append("Origin")
        if cloaking.accept:
            headers["Accept"] = cloaking.accept
            cloaking_applied.append("Accept")
        if cloaking.accept_language:
            headers["Accept-Language"] = cloaking.accept_language
            cloaking_applied.append("Accept-Language")
        if cloaking_applied:
            logger.info(f"Cloaking已启用 | 应用头部: {', '.join(cloaking_applied)}")
            if cloaking.tls_fingerprint_profile:
                logger.info(f"TLS指纹配置: {cloaking.tls_fingerprint_profile}")

    return headers


async def _handle_cascade_chat(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
    original_model: str,
    messages: list,
) -> StreamingResponse | dict:
    cascade = config.model_routing.cascade
    max_retries = cascade.max_retries
    cascade_models = router.resolve_cascade(body, messages)

    if not cascade_models:
        return {"error": {"message": "Cascade enabled but no models configured", "type": "cascade_error"}}

    last_error = None
    for attempt, (model, provider_name) in enumerate(cascade_models):
        if attempt >= max_retries:
            break

        provider_cfg = config.providers.get(provider_name)
        if not provider_cfg or not provider_cfg.enabled:
            last_error = f"Provider '{provider_name}' not enabled"
            continue

        request_body = body.copy()
        request_body["model"] = model
        if not router.supports_tools(model):
            request_body = router.strip_tools(request_body)

        key = key_manager.select_key(provider_name, config.key_selection.strategy)
        if not key:
            last_error = f"No available keys for '{provider_name}'"
            continue

        url = _build_url(provider_cfg.base_url, "/chat/completions")
        headers = _build_headers(provider_cfg, key.key.key)

        is_stream = request_body.get("stream", False)
        start_time = time.time()

        logger.info(f"Cascade尝试 {attempt+1}/{len(cascade_models)} | 模型={model} | 提供商={provider_name}")

        if is_stream:
            return StreamingResponse(
                _stream_chat(
                    provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                    model, original_model, request_logger, start_time, stats_tracker,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Prisma-Model": model,
                    "X-Prisma-Provider": provider_name,
                    "X-Prisma-Cascade": f"{attempt+1}/{len(cascade_models)}",
                },
            )
        else:
            result = await _non_stream_chat(
                provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                model, original_model, request_logger, start_time, stats_tracker,
            )
            if isinstance(result, dict) and "error" in result:
                last_error = result["error"].get("message", "unknown")
                logger.warning(f"Cascade {attempt+1} 失败: {last_error}")
                continue
            return result

    stats_tracker.record_request(cascade_models[0][1], original_model, success=False)
    return {"error": {"message": f"Cascade failed after {len(cascade_models)} attempts: {last_error}", "type": "cascade_error"}}


async def handle_chat_completions(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])

    cascade = config.model_routing.cascade
    if cascade.enabled and cascade.models:
        return await _handle_cascade_chat(
            body, config, key_manager, router, request_logger, stats_tracker,
            original_model, messages,
        )

    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model

    body = router.apply_transformation(body, resolved_model)

    if not router.supports_tools(resolved_model):
        body = router.strip_tools(body)

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    if provider_cfg.provider_type == "web_reverse":
        return await _handle_web_reverse_chat(
            body, provider_cfg, key_manager, provider_name,
            resolved_model, original_model, request_logger, config.key_selection.strategy,
            stats_tracker,
        )

    if provider_cfg.provider_type == "anthropic":
        return await handle_openai_to_anthropic(
            body, config, key_manager, router, request_logger, stats_tracker,
        )

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = _build_url(provider_cfg.base_url, "/chat/completions")
    headers = _build_headers(provider_cfg, key.key.key)

    is_stream = body.get("stream", False)
    start_time = time.time()

    mode = "流式" if is_stream else "非流式"
    logger.info(f"请求发送 | {mode} | 模型={resolved_model} | 提供商={provider_name} | URL={url}")

    if is_stream:
        return StreamingResponse(
            _stream_chat(
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
        return await _non_stream_chat(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker,
        )


async def handle_completions(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    url = _build_url(provider_cfg.base_url, "/completions")
    headers = _build_headers(provider_cfg, key.key.key)

    is_stream = body.get("stream", False)
    start_time = time.time()

    logger.info(f"Completion请求发送 | 模型={resolved_model} | 提供商={provider_name} | URL={url}")

    if is_stream:
        return StreamingResponse(
            _stream_completion(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker,
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
            resolved_model, original_model, request_logger, start_time, stats_tracker,
        )


async def handle_embeddings(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    # Extract text content
    input_text = body.get("input", "")
    if isinstance(input_text, list):
        input_text = "\n".join([str(i) for i in input_text])
    request_text = str(input_text) if input_text else None
    
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    headers = _build_headers(provider_cfg, key.key.key)

    start_time = time.time()
    logger.info(f"Embeddings请求发送 | 模型={resolved_model} | 提供商={provider_name}")
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(
                _build_url(provider_cfg.base_url, "/embeddings"),
                headers=headers,
                json=body,
            )
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                logger.error(f"Embeddings错误{resp.status_code} | 模型={resolved_model} | 提供商={provider_name}")
                return resp.json()
            key_manager.report_success(key, 0)
            logger.info(f"Embeddings | 模型={resolved_model} | 提供商={provider_name} | 耗时={round(elapsed * 1000, 2)}ms")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
            )
            stats_tracker.record_request(provider_name, resolved_model, success=True)
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            logger.error(f"Embeddings失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def _stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
) -> AsyncGenerator[bytes, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            tokens_in = None
            tokens_out = None
            thinking_tokens = None
            stream_chunks = 0
            buffer = b""
            last_chunk_data = None
            first_token_ms = None
            first_token_recorded = False
            output_content = []
            response_preview = None
            
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

            async with client.stream(
                "POST", url, headers=headers, json=body,
                timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0),
            ) as response:
                if response.status_code >= 400:
                    error_body = await response.aread()
                    error_text = error_body.decode("utf-8", errors="replace")
                    logger.error(f"Upstream error {response.status_code}: {error_text}")
                    key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                    elapsed = time.time() - start_time
                    await request_logger.log_request(
                        model=resolved_model, provider=provider_name,
                        key_label=key.key.label, status_code=response.status_code,
                        latency_ms=round(elapsed * 1000, 2), streaming=True,
                        error_message=error_text,
                    )
                    stats_tracker.record_request(provider_name, resolved_model, success=False, latency_ms=elapsed * 1000)
                    err = json.dumps({"error": {"message": error_text, "status_code": response.status_code}})
                    yield f"data: {err}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
                        buffer += chunk
                        stream_chunks += 1

                        # Track first token time
                        if not first_token_recorded:
                            first_token_ms = (time.time() - start_time) * 1000
                            first_token_recorded = True

                        # Parse SSE events from buffer
                        while b"\n\n" in buffer:
                            event, buffer = buffer.split(b"\n\n", 1)
                            for line in event.decode("utf-8", errors="replace").split("\n"):
                                line = line.strip()
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    if data_str == "[DONE]":
                                        continue
                                    try:
                                        data = json.loads(data_str)
                                        last_chunk_data = data
                                        usage = data.get("usage")
                                        if usage:
                                            tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens")
                                            tokens_out = usage.get("completion_tokens") or usage.get("output_tokens")
                                            details = usage.get("completion_tokens_details", {}) or usage.get("prompt_tokens_details", {})
                                            thinking_tokens = details.get("reasoning_tokens")
                                        # Accumulate content for output estimation
                                        choices = data.get("choices", [])
                                        if choices and isinstance(choices, list) and len(choices) > 0:
                                            delta = choices[0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                output_content.append(content)
                                    except Exception:
                                        pass

            # Estimate missing tokens independently
            is_estimated_in = False
            is_estimated_out = False

            if tokens_in is None:
                messages = body.get("messages", [])
                # Extract text content from messages
                request_text = "\n".join([
                    f"{m.get('role', 'user')}: {m.get('content', '')}"
                    for m in messages if m.get("content")
                ])
                tokens_in = _estimate_input_tokens(messages)
                is_estimated_in = True

            if tokens_out is None:
                full_output = "".join(output_content)
                if full_output:
                    tokens_out = _estimate_tokens(full_output)
                    is_estimated_out = True

            is_estimated = is_estimated_in or is_estimated_out

            tokens_in_calc = int(tokens_in) if tokens_in is not None else 0
            tokens_out_calc = int(tokens_out) if tokens_out is not None else 0
            thinking_tokens = int(thinking_tokens) if thinking_tokens is not None else None
            total_tokens = tokens_in_calc + tokens_out_calc

            key_manager.report_success(key, total_tokens)
            elapsed = time.time() - start_time
            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None

            full_output = "".join(output_content)
            if full_output:
                response_preview = full_output[:500] if len(full_output) > 500 else full_output

            # Detailed logging
            log_parts = [f"流式输出完成 | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None:
                label = "输入token(估算)" if is_estimated_in else "输入token"
                log_parts.append(f"{label}={tokens_in}")
            if thinking_tokens is not None:
                log_parts.append(f"思考token={thinking_tokens}")
            log_parts.append(f"流式chunk数={stream_chunks}")
            if tokens_out is not None:
                label = "输出token(估算)" if is_estimated_out else "输出token"
                log_parts.append(f"{label}={tokens_out}")
            total = (tokens_in or 0) + (tokens_out or 0)
            if tokens_in is not None or tokens_out is not None:
                log_parts.append(f"总token={total}")
            if first_token_ms is not None:
                log_parts.append(f"首字延迟={round(first_token_ms)}ms")
            if tokens_out and elapsed > 0:
                speed = tokens_out / elapsed
                log_parts.append(f"输出速度={round(speed, 1)} t/s")
            log_parts.append(f"耗时={round(elapsed * 1000, 2)}ms")
            logger.info(" | ".join(log_parts))

            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=response.status_code,
                latency_ms=round(elapsed * 1000, 2),
                first_token_ms=first_token_ms,
                streaming=True,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                request_preview=request_text if request_text else None,
                response_preview=response_preview if response_preview else None,
                temperature=temperature,
                top_p=top_p,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                max_tokens=max_tokens,
            )
            stats_tracker.record_request(
                provider_name, resolved_model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                success=True,
                is_estimated=is_estimated_in or is_estimated_out,
                latency_ms=elapsed * 1000,
                is_streaming=True,
                first_token_ms=first_token_ms,
                stream_chunks=stream_chunks,
                cost_per_m_input=provider_cfg.cost_per_m_input,
                cost_per_m_output=provider_cfg.cost_per_m_output,
            )
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            elapsed = time.time() - start_time
            logger.error(f"流式请求失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=500,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                error_message=str(e),
                request_preview=request_text if request_text else None,
                temperature=temperature,
                top_p=top_p,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                max_tokens=max_tokens,
            )
            stats_tracker.record_request(provider_name, resolved_model, success=False, latency_ms=elapsed * 1000)
            err = json.dumps({"error": {"message": str(e), "type": "proxy_error"}})
            yield f"data: {err}".encode() + b"\n\n"
            yield b"data: [DONE]\n\n"


async def _non_stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
) -> dict:
    from ..cache import response_cache
    
    messages = body.get("messages", [])
    request_text = "\n".join([
        f"{m.get('role', 'user')}: {m.get('content', '')}"
        for m in messages if m.get("content")
    ])
    
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    presence_penalty = body.get("presence_penalty")
    frequency_penalty = body.get("frequency_penalty")
    max_tokens = body.get("max_tokens")
    
    cached = response_cache.get(body, resolved_model)
    if cached is not None:
        logger.info(f"Cache hit | 模型={resolved_model}")
        stats_tracker.record_request(provider_name, resolved_model, success=True)
        return cached

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
                    request_preview=request_text if request_text else None,
                    temperature=temperature,
                    top_p=top_p,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                    max_tokens=max_tokens,
                )
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                return resp.json()

            result = resp.json()
            tokens_in, tokens_out = extract_token_usage(result)

            # Extract thinking tokens if available
            thinking_tokens = None
            usage = result.get("usage", {})
            if usage:
                details = usage.get("completion_tokens_details", {}) or usage.get("prompt_tokens_details", {})
                thinking_tokens = details.get("reasoning_tokens")

            tokens_in = int(tokens_in) if tokens_in is not None else 0
            tokens_out = int(tokens_out) if tokens_out is not None else 0
            thinking_tokens = int(thinking_tokens) if thinking_tokens is not None else None
            total_tokens = tokens_in + tokens_out

            key_manager.report_success(key, total_tokens)

            # Detailed logging
            log_parts = [f"非流式请求 | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None:
                log_parts.append(f"输入token={tokens_in}")
            if thinking_tokens is not None:
                log_parts.append(f"思考token={thinking_tokens}")
            if tokens_out is not None:
                log_parts.append(f"输出token={tokens_out}")
            total = (tokens_in or 0) + (tokens_out or 0)
            if tokens_in is not None or tokens_out is not None:
                log_parts.append(f"总token={total}")
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
                request_preview=request_text if request_text else None,
                response_preview=json.dumps(result) if result else None,
                temperature=temperature,
                top_p=top_p,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                max_tokens=max_tokens,
            )
            stats_tracker.record_request(
                provider_name, resolved_model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                success=True,
                cost_per_m_input=provider_cfg.cost_per_m_input,
                cost_per_m_output=provider_cfg.cost_per_m_output,
            )
            from ..usage_tracker import usage_tracker
            usage_tracker.record(None, success=True, tokens_in=tokens_in or 0, tokens_out=tokens_out or 0)
            response_cache.set(body, resolved_model, result)
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            elapsed = time.time() - start_time
            logger.error(f"非流式请求失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=500,
                latency_ms=round(elapsed * 1000, 2),
                error_message=str(e),
            )
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def _stream_completion(
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
                    logger.error(f"Completion upstream error {response.status_code}: {error_text}")
                    key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                    elapsed = time.time() - start_time
                    await request_logger.log_request(
                        model=resolved_model, provider=provider_name,
                        key_label=key.key.label, status_code=response.status_code,
                        latency_ms=round(elapsed * 1000, 2), streaming=True,
                        error_message=error_text,
                    )
                    stats_tracker.record_request(provider_name, resolved_model, success=False)
                    err = json.dumps({"error": {"message": error_text, "status_code": response.status_code}})
                    yield f"data: {err}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
                        buffer += chunk
                        stream_chunks += 1

                        while b"\n\n" in buffer:
                            event, buffer = buffer.split(b"\n\n", 1)
                            for line in event.decode("utf-8", errors="replace").split("\n"):
                                line = line.strip()
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    if data_str == "[DONE]":
                                        continue
                                    try:
                                        data = json.loads(data_str)
                                        usage = data.get("usage")
                                        if usage:
                                            tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens")
                                            tokens_out = usage.get("completion_tokens") or usage.get("output_tokens")
                                    except Exception:
                                        pass

            tokens_in_calc = int(tokens_in) if tokens_in is not None else 0
            tokens_out_calc = int(tokens_out) if tokens_out is not None else 0
            total_tokens = tokens_in_calc + tokens_out_calc

            key_manager.report_success(key, total_tokens)
            elapsed = time.time() - start_time
            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None

            log_parts = [f"流式Completion | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None: log_parts.append(f"输入token={tokens_in}")
            log_parts.append(f"流式chunk数={stream_chunks}")
            if tokens_out is not None: log_parts.append(f"输出token={tokens_out}")
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
            logger.error(f"流式Completion失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
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
            err = json.dumps({"error": {"message": str(e), "type": "proxy_error"}})
            yield f"data: {err}".encode() + b"\n\n"
            yield b"data: [DONE]\n\n"


async def _non_stream_completion(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker,
) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                logger.error(f"Completion错误{resp.status_code} | 模型={resolved_model} | 提供商={provider_name}")
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                return resp.json()
            result = resp.json()
            tokens_in, tokens_out = extract_token_usage(result)
            tokens_in_calc = int(tokens_in) if tokens_in is not None else 0
            tokens_out_calc = int(tokens_out) if tokens_out is not None else 0
            total_tokens = tokens_in_calc + tokens_out_calc

            key_manager.report_success(key, total_tokens)
            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None

            log_parts = [f"非流式Completion | 模型={resolved_model} | 提供商={provider_name}"]
            if tokens_in is not None: log_parts.append(f"输入token={tokens_in}")
            if tokens_out is not None: log_parts.append(f"输出token={tokens_out}")
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
                input_tokens=tokens_in, output_tokens=tokens_out, success=True,
            )
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            logger.error(f"Completion失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def handle_models_list(config: AppConfig) -> dict:
    """Return only explicitly enabled models from all providers."""
    all_models = []
    for name, pc in config.providers.items():
        if not pc.enabled:
            continue

        enabled_models = pc.models.get("include", []) if pc.models else []
        if not enabled_models:
            continue

        if pc.provider_type == "web_reverse":
            if pc.web_reverse and pc.web_reverse.model_mapping:
                for client_model in pc.web_reverse.model_mapping:
                    if client_model in enabled_models:
                        all_models.append({
                            "id": f"{client_model}@{name}",
                            "provider": name,
                            "object": "model",
                        })
            continue

        for mid in enabled_models:
            all_models.append({
                "id": f"{mid}@{name}",
                "provider": name,
                "object": "model",
            })

    logger.info(f"模型列表查询 | 返回{len(all_models)}个模型 | 提供商数={len([n for n, p in config.providers.items() if p.enabled])}")
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
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:
    key = key_manager.select_key(provider_name, key_strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for web_reverse provider '{provider_name}'", "type": "no_keys"}}

    access_token = key.key.key
    wr_config = provider_cfg.web_reverse
    if not wr_config:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
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
                    original_model, request_logger, start_time, stats_tracker,
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
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            return result
        else:
            key_manager.report_success(key, 0)
            elapsed = time.time() - start_time
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
                request_preview=request_text,
            )
            stats_tracker.record_request(provider_name, resolved_model, success=True)
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
        stats_tracker.record_request(provider_name, resolved_model, success=False)
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
    stats_tracker: StatsTracker,
) -> AsyncGenerator[bytes, None]:
    async for chunk in stream_gen:
        yield chunk
    key_manager.report_success(key, 0)
    elapsed = time.time() - start_time
    await request_logger.log_request(
        model=resolved_model,
        provider=provider_name,
        key_label=key.key.label,
        status_code=200,
        latency_ms=round(elapsed * 1000, 2),
        streaming=True,
    )
    stats_tracker.record_request(provider_name, resolved_model, success=True)


async def handle_audio_transcriptions(
    body: dict,
    file,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    headers = _build_headers(provider_cfg, key.key.key)
    headers.pop("Content-Type", None)

    start_time = time.time()
    logger.info(f"Audio Transcription请求 | 模型={resolved_model} | 提供商={provider_name}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            file_content = await file.read()
            files = {
                "file": (file.filename or "audio", file_content, file.content_type or "application/octet-stream"),
            }
            resp = await client.post(
                _build_url(provider_cfg.base_url, "/audio/transcriptions"),
                headers=headers,
                data=body,
                files=files,
            )
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                logger.error(f"Audio Transcription错误{resp.status_code} | 模型={resolved_model} | 提供商={provider_name}")
                return resp.json()
            key_manager.report_success(key, 0)
            logger.info(f"Audio Transcription | 模型={resolved_model} | 提供商={provider_name} | 耗时={round(elapsed * 1000, 2)}ms")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
            )
            stats_tracker.record_request(provider_name, resolved_model, success=True)
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            logger.error(f"Audio Transcription失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            return {"error": {"message": str(e), "type": "proxy_error"}}


async def handle_image_generations(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model

    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"Provider '{provider_name}' is not enabled", "type": "provider_disabled"}}

    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key:
        stats_tracker.record_request(provider_name, resolved_model, success=False)
        return {"error": {"message": f"No available keys for provider '{provider_name}'", "type": "no_keys"}}

    headers = _build_headers(provider_cfg, key.key.key)

    start_time = time.time()
    logger.info(f"Image Generation请求 | 模型={resolved_model} | 提供商={provider_name}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(
                _build_url(provider_cfg.base_url, "/images/generations"),
                headers=headers,
                json=body,
            )
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                stats_tracker.record_request(provider_name, resolved_model, success=False)
                logger.error(f"Image Generation错误{resp.status_code} | 模型={resolved_model} | 提供商={provider_name}")
                return resp.json()
            key_manager.report_success(key, 0)
            logger.info(f"Image Generation | 模型={resolved_model} | 提供商={provider_name} | 耗时={round(elapsed * 1000, 2)}ms")
            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=resp.status_code,
                latency_ms=round(elapsed * 1000, 2),
            )
            stats_tracker.record_request(provider_name, resolved_model, success=True)
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            stats_tracker.record_request(provider_name, resolved_model, success=False)
            logger.error(f"Image Generation失败 | 模型={resolved_model} | 提供商={provider_name} | 错误={e}")
            return {"error": {"message": str(e), "type": "proxy_error"}}
