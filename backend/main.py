"""PrismaAPIRelay - LLM API Relay Server."""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from .config import ConfigManager
from .key_manager import KeyManager
from .logger import RequestLogger
from .models import AppConfig, ProviderConfig, ProviderKey
from .router import ModelRouter
from .stats import StatsTracker
from .proxy.openai_format import (
    handle_chat_completions,
    handle_completions,
    handle_embeddings,
    handle_models_list,
)
from .proxy.anthropic_format import handle_messages
from .sync import GistSync

logger = logging.getLogger("prisma.main")


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


config_manager = ConfigManager()
key_manager = KeyManager()
request_logger = RequestLogger()
stats_tracker = StatsTracker()
model_router = ModelRouter(AppConfig())


def init_components(cfg: AppConfig):
    global model_router
    model_router = ModelRouter(cfg)

    for name in list(key_manager._entries.keys()):
        if name not in cfg.providers:
            del key_manager._entries[name]

    for name, pc in cfg.providers.items():
        if pc.enabled:
            key_manager.register_provider(name, pc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config_manager.config.server.log_level)
    logger.info("=" * 60)
    logger.info("PrismaAPIRelay starting...")
    logger.info("=" * 60)

    cfg = config_manager.config
    init_components(cfg)

    if cfg.logging.enabled:
        os.makedirs(os.path.dirname(cfg.logging.db_path) or ".", exist_ok=True)
        request_logger.db_path = cfg.logging.db_path
        request_logger.max_age_days = cfg.logging.max_age_days
        request_logger.content_preview_length = cfg.logging.content_preview_length
        await request_logger.init()

    logger.info(f"Server: {cfg.server.host}:{cfg.server.port}")
    logger.info(f"Enabled providers: {[n for n, p in cfg.providers.items() if p.enabled]}")

    import asyncio
    asyncio.create_task(config_manager.watch())

    # Register hot-reload callback
    config_manager.on_reload(lambda new, old: init_components(new))

    yield

    await request_logger.close()
    logger.info("PrismaAPIRelay shut down.")


app = FastAPI(
    title="PrismaAPIRelay",
    description="Configurable LLM API Relay Server supporting OpenRouter, NVIDIA NIM, OpenAI, and Anthropic",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/v1/") or path.startswith("/api/"):
        access_key = config_manager.config.server.access_key
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.headers.get("x-access-key", "")

        if token != access_key:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Unauthorized", "type": "auth_error"}},
            )

    response = await call_next(request)
    return response


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "Frontend not found"}, status_code=404)


@app.get("/api/info")
async def api_info():
    """Return server connection info for dashboard."""
    import socket
    try:
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    cfg = config_manager.config
    return {
        "local_ip": local_ip,
        "host": cfg.server.host,
        "port": cfg.server.port,
        "access_key": cfg.server.access_key,
        "base_url": f"http://{local_ip}:{cfg.server.port}/v1",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "providers": {
            name: {
                "enabled": pc.enabled,
                "keys": len(pc.keys),
                "base_url": pc.base_url,
            }
            for name, pc in config_manager.config.providers.items()
        },
    }


# OpenAI-compatible endpoints
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    result = await handle_chat_completions(
        body, config_manager.config, key_manager, model_router, request_logger,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    result = await handle_completions(
        body, config_manager.config, key_manager, model_router, request_logger,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    result = await handle_embeddings(
        body, config_manager.config, key_manager, model_router, request_logger,
    )
    if "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/v1/models")
async def models_list():
    return await handle_models_list(config_manager.config)


# Anthropic-compatible endpoints
@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    result = await handle_messages(
        body, config_manager.config, key_manager, model_router, request_logger,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


# Management API
@app.get("/api/stats")
async def api_stats():
    summary = stats_tracker.get_summary()
    db_stats = await request_logger.get_stats_summary()
    return {
        "in_memory": summary,
        "persistent": db_stats,
        "keys": key_manager.get_stats(),
    }


@app.get("/api/logs")
async def api_logs(limit: int = 50):
    return await request_logger.get_recent_requests(limit)


@app.get("/api/config")
async def api_get_config():
    return config_manager.config.model_dump(mode="json")


@app.put("/api/config")
async def api_update_config(request: Request):
    try:
        body = await request.json()
        new_cfg = AppConfig(**body)
        config_manager.save(new_cfg)
        init_components(new_cfg)
        return {"status": "ok", "message": "Configuration updated and reloaded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/providers")
async def api_providers():
    result = {}
    for name, pc in config_manager.config.providers.items():
        result[name] = {
            "enabled": pc.enabled,
            "provider_type": pc.provider_type,
            "base_url": pc.base_url,
            "keys": [{"key": k.key, "label": k.label, "weight": k.weight, "enabled": k.enabled} for k in pc.keys],
            "rate_limit_cooldown": pc.rate_limit_cooldown,
            "timeout": pc.timeout,
            "models": pc.models,
            "headers": pc.headers,
            "test_model": pc.test_model,
            "console_url": pc.console_url,
            "web_reverse": pc.web_reverse.model_dump() if pc.web_reverse else None,
        }
    return result


@app.post("/api/providers/{name}/test")
async def api_test_provider(name: str):
    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    if not pc.keys:
        return {"status": "error", "message": "No keys configured"}

    if pc.provider_type == "web_reverse":
        try:
            from .web_reverse.chatgpt import WebReverseService
            wr_cfg = pc.web_reverse.model_dump() if pc.web_reverse else {}
            service = WebReverseService(name, wr_cfg)
            await service.prepare(pc.keys[0].key)
            ok = bool(service.chat_token)
            return {
                "status": "ok" if ok else "error",
                "message": "ChatGPT session valid" if ok else "ChatGPT session invalid",
                "debug": {
                    "type": "web_reverse",
                    "chatgpt_base_url": wr_cfg.get("chatgpt_base_url", "https://chatgpt.com"),
                    "chat_token_obtained": bool(service.chat_token),
                    "proof_token_obtained": bool(service.proof_token),
                    "conversation_only": wr_cfg.get("conversation_only", False),
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    headers = {
        "Authorization": f"Bearer {pc.keys[0].key[:8]}..." if len(pc.keys[0].key) > 8 else pc.keys[0].key,
        "Content-Type": "application/json",
    }
    if pc.headers:
        headers["Extra-Headers"] = str(list(pc.headers.keys()))

    # Test with a minimal chat request to verify API key validity
    # /models endpoint is often public (e.g. OpenRouter), so it doesn't prove key works
    # Use a known working model per provider
    test_models = {
        "openrouter": "openai/gpt-4o-mini",
        "nvidia": "meta/llama-3.1-8b-instruct",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "deepseek": "deepseek-chat",
    }
    # Use provider's configured test_model, or fallback to defaults
    test_model = pc.test_model or test_models.get(name, "gpt-4o-mini")

    test_payload = {
        "model": test_model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
    }

    url = pc.base_url
    if pc.provider_type != "web_reverse" and not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    import time as _time
    start = _time.monotonic()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {pc.keys[0].key}",
                    "Content-Type": "application/json",
                    **(pc.headers or {}),
                },
                json=test_payload,
                timeout=15.0,
            )
        elapsed_ms = round((_time.monotonic() - start) * 1000, 1)

        # Try to parse response body
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text[:500]

        if resp.status_code < 400:
            # Extract useful info from success response
            choices = resp_body.get("choices", []) if isinstance(resp_body, dict) else []
            usage = resp_body.get("usage", {}) if isinstance(resp_body, dict) else {}
            resp_model = resp_body.get("model", test_model) if isinstance(resp_body, dict) else test_model
            finish_reason = choices[0].get("finish_reason", "") if choices else ""

            return {
                "status": "ok",
                "message": f"测试成功 — API key 有效",
                "debug": {
                    "type": "api",
                    "request": {
                        "method": "POST",
                        "url": url,
                        "model": test_model,
                        "payload": test_payload,
                    },
                    "response": {
                        "status_code": resp.status_code,
                        "model": resp_model,
                        "finish_reason": finish_reason,
                        "usage": usage,
                        "body_preview": str(resp_body)[:300] if isinstance(resp_body, str) else resp_body,
                    },
                    "timing_ms": elapsed_ms,
                }
            }
        elif resp.status_code == 401:
            return {
                "status": "error",
                "message": f"API key 无效或已过期 (HTTP 401)",
                "debug": {
                    "type": "api",
                    "request": {"method": "POST", "url": url, "model": test_model},
                    "response": {"status_code": 401, "body": resp_body},
                    "timing_ms": elapsed_ms,
                }
            }
        elif resp.status_code == 429:
            return {
                "status": "error",
                "message": f"触发限流 (HTTP 429) — key 有效但额度已用完",
                "debug": {
                    "type": "api",
                    "request": {"method": "POST", "url": url, "model": test_model},
                    "response": {"status_code": 429, "body": resp_body},
                    "timing_ms": elapsed_ms,
                }
            }
        else:
            return {
                "status": "error",
                "message": f"HTTP {resp.status_code}: {str(resp_body)[:200]}",
                "debug": {
                    "type": "api",
                    "request": {"method": "POST", "url": url, "model": test_model},
                    "response": {"status_code": resp.status_code, "body": resp_body},
                    "timing_ms": elapsed_ms,
                }
            }
    except httpx.TimeoutException:
        elapsed_ms = round((_time.monotonic() - start) * 1000, 1)
        return {
            "status": "error",
            "message": f"请求超时 ({elapsed_ms}ms)",
            "debug": {
                "type": "api",
                "request": {"method": "POST", "url": url, "model": test_model},
                "error": "Timeout",
                "timing_ms": elapsed_ms,
            }
        }
    except Exception as e:
        elapsed_ms = round((_time.monotonic() - start) * 1000, 1)
        return {
            "status": "error",
            "message": str(e),
            "debug": {
                "type": "api",
                "request": {"method": "POST", "url": url, "model": test_model},
                "error": str(e),
                "timing_ms": elapsed_ms,
            }
        }


# Provider CRUD
@app.post("/api/providers")
async def api_add_provider(request: Request):
    """Add a new provider and hot-reload."""
    try:
        body = await request.json()
        name = body.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Provider name is required")
        if name in config_manager.config.providers:
            raise HTTPException(status_code=409, detail=f"Provider '{name}' already exists")

        pc = ProviderConfig(**body.get("config", {}))
        cfg = config_manager.config.model_copy(deep=True)
        cfg.providers[name] = pc
        config_manager.save(cfg)
        init_components(cfg)
        return {"status": "ok", "message": f"Provider '{name}' added and reloaded"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/providers/{name}")
async def api_update_provider(name: str, request: Request):
    """Update an existing provider and hot-reload."""
    try:
        body = await request.json()
        cfg = config_manager.config.model_copy(deep=True)
        if name not in cfg.providers:
            raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

        update_data = body.get("config", body)
        existing = cfg.providers[name].model_dump()
        existing.update({k: v for k, v in update_data.items() if v is not None})
        cfg.providers[name] = ProviderConfig(**existing)
        config_manager.save(cfg)
        init_components(cfg)
        return {"status": "ok", "message": f"Provider '{name}' updated and reloaded"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/providers/{name}")
async def api_delete_provider(name: str):
    """Delete a provider and hot-reload."""
    cfg = config_manager.config
    if name not in cfg.providers:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    new_cfg = cfg.model_copy(deep=True)
    del new_cfg.providers[name]
    config_manager.save(new_cfg)
    init_components(new_cfg)
    return {"status": "ok", "message": f"Provider '{name}' deleted and reloaded"}


# Key CRUD
@app.post("/api/providers/{name}/keys")
async def api_add_key(name: str, request: Request):
    """Add a key to a provider and hot-reload."""
    try:
        body = await request.json()
        cfg = config_manager.config.model_copy(deep=True)
        if name not in cfg.providers:
            raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

        key_data = ProviderKey(**body)
        cfg.providers[name].keys.append(key_data)
        config_manager.save(cfg)
        init_components(cfg)
        return {"status": "ok", "message": f"Key '{key_data.label}' added to '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/providers/{name}/keys/{key_index}")
async def api_update_key(name: str, key_index: int, request: Request):
    """Update a key in a provider by index and hot-reload."""
    try:
        body = await request.json()
        cfg = config_manager.config.model_copy(deep=True)
        if name not in cfg.providers:
            raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

        provider = cfg.providers[name]
        if key_index < 0 or key_index >= len(provider.keys):
            raise HTTPException(status_code=404, detail=f"Key index {key_index} out of range")

        update_data = {k: v for k, v in body.items() if v is not None}
        existing = provider.keys[key_index].model_dump()
        existing.update(update_data)
        provider.keys[key_index] = ProviderKey(**existing)
        config_manager.save(cfg)
        init_components(cfg)
        return {"status": "ok", "message": f"Key updated for '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/providers/{name}/keys/{key_index}")
async def api_delete_key(name: str, key_index: int):
    """Delete a key from a provider by index and hot-reload."""
    cfg = config_manager.config
    if name not in cfg.providers:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    provider = cfg.providers[name]
    if key_index < 0 or key_index >= len(provider.keys):
        raise HTTPException(status_code=404, detail=f"Key index {key_index} out of range")

    new_cfg = cfg.model_copy(deep=True)
    removed = new_cfg.providers[name].keys.pop(key_index)
    if not new_cfg.providers[name].keys:
        raise HTTPException(status_code=400, detail="Cannot remove last key from provider")

    config_manager.save(new_cfg)
    init_components(new_cfg)
    return {"status": "ok", "message": f"Key '{removed.label}' removed from '{name}'"}


# Model management
@app.get("/api/providers/{name}/models/remote")
async def api_get_remote_models(name: str):
    """Fetch all available models from a provider's upstream API."""
    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    if pc.provider_type == "web_reverse":
        # Web reverse: use model_mapping keys
        models = []
        if pc.web_reverse and pc.web_reverse.model_mapping:
            for client_model, upstream_model in pc.web_reverse.model_mapping.items():
                models.append({
                    "id": client_model,
                    "upstream_id": upstream_model,
                    "provider": name,
                })
        return {"object": "list", "data": models}

    if not pc.keys:
        return {"object": "list", "data": []}

    headers = {"Authorization": f"Bearer {pc.keys[0].key}"}
    if pc.headers:
        headers.update(pc.headers)

    try:
        async with httpx.AsyncClient() as client:
            models_url = pc.base_url
            if not models_url.endswith("/models"):
                models_url = f"{pc.base_url}/models"
            resp = await client.get(models_url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                upstream_models = data.get("data", data) if isinstance(data, dict) else data
                models = []
                for m in upstream_models:
                    mid = m.get("id", m) if isinstance(m, dict) else m
                    model_info = {"id": mid, "provider": name}
                    if isinstance(m, dict):
                        for field in ("owned_by", "created", "description"):
                            if field in m:
                                model_info[field] = m[field]
                    models.append(model_info)
                return {"object": "list", "data": models}
            else:
                return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "请求超时"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/providers/{name}/models/enabled")
async def api_get_enabled_models(name: str):
    """Get currently enabled models (include list) for a provider."""
    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    model_filter = pc.models if isinstance(pc.models, dict) else {}
    return {
        "provider": name,
        "include": model_filter.get("include", []),
        "exclude": model_filter.get("exclude", []),
    }


@app.put("/api/providers/{name}/models")
async def api_update_models(name: str, request: Request):
    """Update model include/exclude lists for a provider and hot-reload."""
    try:
        body = await request.json()
        cfg = config_manager.config.model_copy(deep=True)
        if name not in cfg.providers:
            raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

        if "include" in body:
            cfg.providers[name].models["include"] = body["include"]
        if "exclude" in body:
            cfg.providers[name].models["exclude"] = body["exclude"]

        config_manager.save(cfg)
        init_components(cfg)
        return {"status": "ok", "message": f"Models updated for '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/router")
async def api_router_info():
    cfg = config_manager.config.model_routing
    return {
        "enabled": cfg.enabled,
        "mode": cfg.mode,
        "aliases": cfg.aliases,
        "provider_mapping": cfg.provider_mapping,
        "model_overrides": cfg.model_overrides,
        "complexity": cfg.complexity.model_dump() if cfg.complexity else None,
    }


# Config Sync
@app.get("/api/sync")
async def api_sync_status():
    """Return current sync configuration and status."""
    sc = config_manager.config.sync
    return {
        "enabled": sc.enabled,
        "gist_id": sc.gist_id,
        "has_token": bool(sc.gist_token),
    }


@app.post("/api/sync/setup")
async def api_sync_setup(request: Request):
    """Configure Gist sync with token and optional gist_id."""
    try:
        body = await request.json()
        token = body.get("gist_token", "").strip()
        gist_id = body.get("gist_id", "").strip()

        if not token:
            raise HTTPException(status_code=400, detail="gist_token is required")

        cfg = config_manager.config.model_copy(deep=True)
        cfg.sync.enabled = True
        cfg.sync.gist_token = token
        cfg.sync.gist_id = gist_id
        config_manager.save(cfg)
        return {"status": "ok", "message": "Gist sync configured"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sync/push")
async def api_sync_push():
    """Push current config to Gist."""
    sc = config_manager.config.sync
    if not sc.enabled or not sc.gist_token:
        raise HTTPException(status_code=400, detail="Gist sync not configured")

    sync = GistSync(sc.gist_token, sc.gist_id)
    content = yaml.dump(config_manager.config.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)
    ok = await sync.push(content)

    if ok:
        # Save updated gist_id if a new gist was created
        if sync.gist_id and sync.gist_id != sc.gist_id:
            cfg = config_manager.config.model_copy(deep=True)
            cfg.sync.gist_id = sync.gist_id
            config_manager.save(cfg)
        return {"status": "ok", "message": "Config pushed to Gist", "gist_id": sync.gist_id}
    raise HTTPException(status_code=500, detail="Failed to push config to Gist")


@app.post("/api/sync/pull")
async def api_sync_pull():
    """Pull config from Gist and apply."""
    sc = config_manager.config.sync
    if not sc.enabled or not sc.gist_token or not sc.gist_id:
        raise HTTPException(status_code=400, detail="Gist sync not configured")

    sync = GistSync(sc.gist_token, sc.gist_id)
    content = await sync.pull()
    if not content:
        raise HTTPException(status_code=500, detail="Failed to pull config from Gist")

    try:
        import yaml
        raw = yaml.safe_load(content)
        new_cfg = AppConfig(**raw)
        config_manager.save(new_cfg)
        init_components(new_cfg)
        return {"status": "ok", "message": "Config pulled and applied from Gist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse pulled config: {e}")


@app.get("/api/sync/history")
async def api_sync_history():
    """Get Gist commit history."""
    sc = config_manager.config.sync
    if not sc.enabled or not sc.gist_token or not sc.gist_id:
        return []

    sync = GistSync(sc.gist_token, sc.gist_id)
    return await sync.get_history()


def run():
    import argparse
    parser = argparse.ArgumentParser(description="PrismaAPIRelay - LLM API Relay Server")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--host", type=str, default=None, help="Host to bind")
    parser.add_argument("--port", type=int, default=None, help="Port to bind")
    parser.add_argument("--log-level", type=str, default=None, help="Log level")
    args = parser.parse_args()

    if args.config:
        global config_manager
        config_manager = ConfigManager(args.config)

    cfg = config_manager.config
    host = args.host or cfg.server.host
    port = args.port or cfg.server.port
    log_level = args.log_level or cfg.server.log_level

    setup_logging(log_level)
    logger.info(f"Starting PrismaAPIRelay on {host}:{port}")

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
