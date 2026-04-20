"""OpenAI-compatible API proxy handler (OpenRouter, NVIDIA NIM, OpenAI, Web Reverse)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Any, Optional

import httpx
from fastapi.responses import StreamingResponse

from ..key_manager import KeyManager, retry_with_backoff
from ..logger import RequestLogger
from ..models import AppConfig
from ..router import ModelRouter
from ..stats import StatsTracker, estimate_cost, extract_token_usage
from ..web_reverse.chatgpt import WebReverseService
from .anthropic_format import handle_messages, handle_openai_to_anthropic
from .streaming import stream_openai_response, extract_stream_usage
from ..usage_tracker import usage_tracker
from ..auth_utils import verify_token

logger = logging.getLogger("monorelay.openai_proxy")

def _estimate_tokens(text: str) -> int:
    if not text: return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    non_chinese = text.replace(' ', '').replace('\n', '').replace('\t', '')
    english_chars = len(non_chinese) - sum(1 for c in non_chinese if '\u4e00' <= c <= '\u9fff')
    english_tokens = max(1, int(english_chars / 4 * 1.3)) if english_chars > 0 else 0
    return chinese_chars + english_tokens

def _estimate_input_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str): total += _estimate_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item: total += _estimate_tokens(item["text"])
    total += len(messages) * 3
    return total

def _build_url(base_url: str, path: str) -> str:
    if base_url.endswith(path): return base_url
    return f"{base_url}{path}"

def _build_headers(provider_cfg, api_key: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider_cfg.headers: headers.update(provider_cfg.headers)
    cloaking = provider_cfg.cloaking
    if cloaking:
        if cloaking.user_agent: headers["User-Agent"] = cloaking.user_agent
        if cloaking.referer: headers["Referer"] = cloaking.referer
        if cloaking.origin: headers["Origin"] = cloaking.origin
        if cloaking.accept: headers["Accept"] = cloaking.accept
        if cloaking.accept_language: headers["Accept-Language"] = cloaking.accept_language
    return headers

async def _handle_generic_post(path: str, body: dict, config: AppConfig, key_manager: KeyManager, router: Optional[ModelRouter], request_logger: RequestLogger, stats_tracker: StatsTracker, method: str = "POST") -> dict:
    original_model = body.get("model", "unknown")
    if router: resolved_model, provider_name = router.resolve_model(original_model)
    else:
        provider_name = next((n for n, p in config.providers.items() if p.enabled), "openrouter")
        resolved_model = original_model
    body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        return {"error": {"message": f"[{provider_name}] Provider not enabled", "type": "provider_disabled"}}
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": f"[{provider_name}] No available keys", "type": "no_keys"}}
    headers = _build_headers(provider_cfg, key.key.key)
    url = _build_url(provider_cfg.base_url, path)
    start_time = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.request(method, url, headers=headers, json=body)
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                try: return resp.json()
                except Exception: return {"error": {"message": resp.text, "type": "upstream_error"}}
            key_manager.report_success(key, 0)
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2), request_full=json.dumps(body, ensure_ascii=False))
            stats_tracker.record_request(provider_name, resolved_model, success=True)
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": f"[{provider_name}] {str(e)}", "type": "proxy_error"}}

async def _handle_generic_get(path: str, config: AppConfig, key_manager: KeyManager, request_logger: RequestLogger, stats_tracker: StatsTracker, params: dict = None) -> dict:
    provider_name = next((n for n, p in config.providers.items() if p.enabled), "openrouter")
    provider_cfg = config.providers.get(provider_name)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": "No available keys", "type": "no_keys"}}
    headers = _build_headers(provider_cfg, key.key.key)
    url = _build_url(provider_cfg.base_url, path)
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            try: return resp.json()
            except Exception: return {"error": {"message": resp.text, "type": "upstream_error"}}
        except Exception as e: return {"error": {"message": str(e), "type": "proxy_error"}}

async def _handle_generic_multipart(path: str, body: dict, files: dict, config: AppConfig, key_manager: KeyManager, router: ModelRouter, request_logger: RequestLogger, stats_tracker: StatsTracker) -> dict:
    original_model = body.get("model", "unknown")
    resolved_model, provider_name = router.resolve_model(original_model)
    body["model"] = resolved_model
    provider_cfg = config.providers.get(provider_name)
    if not provider_cfg or not provider_cfg.enabled:
        return {"error": {"message": f"[{provider_name}] Provider not enabled", "type": "provider_disabled"}}
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": f"[{provider_name}] No available keys", "type": "no_keys"}}
    headers = _build_headers(provider_cfg, key.key.key)
    headers.pop("Content-Type", None)
    url = _build_url(provider_cfg.base_url, path)
    start_time = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            prepared_files = {}
            for k, v in files.items():
                if v is not None:
                    if hasattr(v, 'read'):
                        content = await v.read()
                        prepared_files[k] = (getattr(v, 'filename', 'file'), content, getattr(v, 'content_type', 'application/octet-stream'))
                    else: prepared_files[k] = v
            resp = await client.post(url, headers=headers, data=body, files=prepared_files)
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                try: return resp.json()
                except Exception: return {"error": {"message": resp.text, "type": "upstream_error"}}
            key_manager.report_success(key, 0)
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2))
            stats_tracker.record_request(provider_name, resolved_model, success=True)
            return resp.json()
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": f"[{provider_name}] {str(e)}", "type": "proxy_error"}}

async def handle_chat_completions(body, config, key_manager, router, request_logger, stats_tracker):
    original_model = body.get("model", "unknown")
    messages = body.get("messages", [])
    cascade = config.model_routing.cascade
    if cascade.enabled and cascade.models:
        cascade_models = router.resolve_cascade(body, messages)
        for model, provider_name in cascade_models:
            provider_cfg = config.providers.get(provider_name)
            key = key_manager.select_key(provider_name, config.key_selection.strategy)
            if not key: continue
            url = _build_url(provider_cfg.base_url, "/chat/completions")
            headers = _build_headers(provider_cfg, key.key.key)
            return await _non_stream_chat(provider_cfg, url, headers, {**body, "model": model}, key, key_manager, provider_name, model, original_model, request_logger, time.time(), stats_tracker)
    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model
    body = router.apply_transformation(body, resolved_model)
    if not router.supports_tools(resolved_model): body = router.strip_tools(body)
    provider_cfg = config.providers.get(provider_name)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": f"No keys for {provider_name}"}}
    url = _build_url(provider_cfg.base_url, "/chat/completions")
    headers = _build_headers(provider_cfg, key.key.key)
    is_stream = body.get("stream", False)
    if is_stream:
        return StreamingResponse(_stream_chat(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, time.time(), stats_tracker), media_type="text/event-stream")
    return await _non_stream_chat(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, time.time(), stats_tracker)

async def _stream_chat(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker):
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    err = await response.aread()
                    yield f"data: {err.decode()}\n\n".encode()
                    return
                async for chunk in response.aiter_bytes(): yield chunk
            key_manager.report_success(key, 0)
        except Exception as e: yield f"data: {str(e)}\n\n".encode()

async def _non_stream_chat(provider_cfg, url, headers, body, key, key_manager, provider_name, resolved_model, original_model, request_logger, start_time, stats_tracker):
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
            elapsed = time.time() - start_time
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
                try: return resp.json()
                except Exception: return {"error": {"message": resp.text}}
            key_manager.report_success(key, 0)
            await request_logger.log_request(model=resolved_model, provider=provider_name, key_label=key.key.label, status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2))
            return resp.json()
        except Exception as e: return {"error": {"message": str(e)}}

async def handle_completions(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/completions", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_embeddings(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/embeddings", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_models_list(config: AppConfig) -> dict:
    all_models = []
    for name, pc in config.providers.items():
        if not pc.enabled: continue
        enabled_models = pc.models.get("include", []) if pc.models else []
        if pc.provider_type == "web_reverse":
            if pc.web_reverse and pc.web_reverse.model_mapping:
                for client_model in pc.web_reverse.model_mapping:
                    if not enabled_models or client_model in enabled_models:
                        all_models.append({"id": f"{client_model}@{name}", "provider": name, "object": "model"})
            continue
        for mid in enabled_models: all_models.append({"id": f"{mid}@{name}", "provider": name, "object": "model"})
    return {"object": "list", "data": all_models}

async def handle_audio_transcriptions(body, file, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/audio/transcriptions", body, {"file": file}, config, key_manager, router, request_logger, stats_tracker)

async def handle_audio_translations(body, file, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/audio/translations", body, {"file": file}, config, key_manager, router, request_logger, stats_tracker)

async def handle_image_generations(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/images/generations", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_image_variations(body, file, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/images/variations", body, {"file": file}, config, key_manager, router, request_logger, stats_tracker)

async def handle_image_edits(body, image, mask, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/images/edits", body, {"image": image, "mask": mask}, config, key_manager, router, request_logger, stats_tracker)

async def handle_moderations(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/moderations", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_responses(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/responses", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_credits(config, key_manager, request_logger, auth_header):
    client_id = "anonymous"
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == config.server.access_key: client_id = "admin"
        else:
            uid = verify_token(token, config_secret=config.server.jwt_secret)
            if uid: client_id = str(uid)
    stats = usage_tracker.get_stats(client_id)
    cost = stats.get("cost", 0.0)
    return {
        "object": "credit_summary",
        "total_granted": 999999.0,
        "total_used": cost,
        "total_available": max(0, 999999.0 - cost),
        "usage": stats
    }

async def handle_files_list(config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get("/files", config, key_manager, request_logger, stats_tracker, params)

async def handle_files_retrieve(file_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/files/{file_id}", config, key_manager, request_logger, stats_tracker)

async def handle_files_content(file_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/files/{file_id}/content", config, key_manager, request_logger, stats_tracker)

async def handle_fine_tuning_jobs_list(config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get("/fine_tuning/jobs", config, key_manager, request_logger, stats_tracker, params)

async def handle_fine_tuning_jobs_create(body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post("/fine_tuning/jobs", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_fine_tuning_jobs_retrieve(job_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/fine_tuning/jobs/{job_id}", config, key_manager, request_logger, stats_tracker)

async def handle_fine_tuning_jobs_cancel(job_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/fine_tuning/jobs/{job_id}/cancel", {}, config, key_manager, None, request_logger, stats_tracker)

async def handle_batches_list(config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get("/batches", config, key_manager, request_logger, stats_tracker, params)

async def handle_batches_create(body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post("/batches", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_batches_retrieve(batch_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/batches/{batch_id}", config, key_manager, request_logger, stats_tracker)

async def handle_assistants_list(config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get("/assistants", config, key_manager, request_logger, stats_tracker, params)

async def handle_assistants_create(body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post("/assistants", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_assistants_retrieve(assistant_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/assistants/{assistant_id}", config, key_manager, request_logger, stats_tracker)

async def handle_assistants_update(assistant_id, body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/assistants/{assistant_id}", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_assistants_delete(assistant_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/assistants/{assistant_id}", {}, config, key_manager, None, request_logger, stats_tracker, method="DELETE")

async def handle_threads_list(config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get("/threads", config, key_manager, request_logger, stats_tracker, params)

async def handle_threads_create(body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post("/threads", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_threads_retrieve(thread_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/threads/{thread_id}", config, key_manager, request_logger, stats_tracker)

async def handle_threads_modify(thread_id, body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/threads/{thread_id}", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_threads_delete(thread_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/threads/{thread_id}", {}, config, key_manager, None, request_logger, stats_tracker, method="DELETE")

async def handle_threads_messages_list(thread_id, config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get(f"/threads/{thread_id}/messages", config, key_manager, request_logger, stats_tracker, params)

async def handle_threads_messages_create(thread_id, body, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/threads/{thread_id}/messages", body, config, key_manager, None, request_logger, stats_tracker)

async def handle_runs_list(thread_id, config, key_manager, request_logger, stats_tracker, **params):
    return await _handle_generic_get(f"/threads/{thread_id}/runs", config, key_manager, request_logger, stats_tracker, params)

async def handle_runs_create(thread_id, body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post(f"/threads/{thread_id}/runs", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_runs_retrieve(thread_id, run_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_get(f"/threads/{thread_id}/runs/{run_id}", config, key_manager, request_logger, stats_tracker)

async def handle_runs_cancel(thread_id, run_id, config, key_manager, request_logger, stats_tracker):
    return await _handle_generic_post(f"/threads/{thread_id}/runs/{run_id}/cancel", {}, config, key_manager, None, request_logger, stats_tracker)
