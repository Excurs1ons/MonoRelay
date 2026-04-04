"""PrismaAPIRelay - LLM API Relay Server."""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from .config import ConfigManager
from .key_manager import KeyManager
from .logger import RequestLogger
from .models import AppConfig
from .router import ModelRouter
from .stats import StatsTracker
from .proxy.openai_format import (
    handle_chat_completions,
    handle_completions,
    handle_embeddings,
    handle_models_list,
)
from .proxy.anthropic_format import handle_messages

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
            "keys": [{"label": k.label, "weight": k.weight} for k in pc.keys],
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
            return {"status": "ok" if ok else "error", "message": "ChatGPT session valid" if ok else "ChatGPT session invalid"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    headers = {
        "Authorization": f"Bearer {pc.keys[0].key}",
        "Content-Type": "application/json",
    }
    if pc.headers:
        headers.update(pc.headers)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{pc.base_url}/models", headers=headers, timeout=10.0)
        ok = resp.status_code < 400
        return {"status": "ok" if ok else "error", "message": "Connection successful" if ok else "Connection failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
