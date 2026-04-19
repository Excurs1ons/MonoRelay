"""MonoRelay - LLM API Relay Server."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ConfigManager
from .key_manager import KeyManager
from .logger import RequestLogger
from .models import AppConfig, ProviderConfig, ProviderKey, SSOConfig
from .router import ModelRouter
from .stats import StatsTracker
from .sso import create_sso_config_from_dict, SSOUser
from .sso_session import sso_session_manager
from .auth_service import AuthService
from .auth_models import UserCreate, UserLogin
from .proxy.openai_format import (
    handle_chat_completions,
    handle_completions,
    handle_embeddings,
    handle_models_list,
    handle_audio_transcriptions,
    handle_image_generations,
)
from .proxy.anthropic_format import handle_messages
from .sync import GistSync
from .sync_webdav import WebDAVSync
from .sync_storage import SyncStorage
from .cache import response_cache
from .usage_tracker import usage_tracker
from .auth_service import AuthService
from .auth_models import UserCreate, UserLogin


class VerifyRequest(BaseModel):
    probe_types: list[str] = ["text-gen", "tool-call", "streaming"]
    model: str | None = None


logger = logging.getLogger("monorelay.main")

HEALTH_CHECK_HISTORY: dict[str, list[int]] = {}
HEALTH_CHECK_MAX_HISTORY = 5


def api_response(data: Any = None, message: str = "OK", page: int = 1, page_size: int = 20, total: int = 0) -> dict:
    """Wrap admin API responses in standard envelope."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "metadata": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "timestamp": datetime.now().isoformat()
        }
    }


def error_response(message: str, code: int = 400) -> dict:
    return {"success": False, "message": message, "data": None, "metadata": None}


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
sync_storage = SyncStorage()
auth_service = AuthService(jwt_secret="")
sso_validator = None


def init_components(cfg: AppConfig):
    global model_router, auth_service, sso_validator
    from .sso import OAuthValidator, create_sso_config_from_dict, SSOConfig
    
    model_router = ModelRouter(cfg)
    auth_service.jwt_secret = cfg.server.jwt_secret or ""
    
    # Sync gist_id to storage if changed
    if cfg.sync and cfg.sync.gist_id:
        sync_storage.gist_id = cfg.sync.gist_id

    if cfg.sso and cfg.sso.enabled:
        sso_config = create_sso_config_from_dict(cfg.sso.model_dump())
        if sso_config.is_configured:
            sso_validator = OAuthValidator(sso_config)
            logger.info(f"SSO enabled with provider: {sso_config.provider}")
        else:
            logger.warning("SSO enabled but not configured properly")

    for name in list(key_manager._entries.keys()):
        if name not in cfg.providers:
            del key_manager._entries[name]

    for name, pc in cfg.providers.items():
        if pc.enabled:
            key_manager.register_provider(name, pc)
    
    logger.info(f"All components reloaded. Registered providers: {list(key_manager._entries.keys())}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config_manager.config.server.log_level)
    logger.info("=" * 60)
    logger.info("MonoRelay starting...")
    logger.info("=" * 60)

    cfg = config_manager.config
    init_components(cfg)

    os.makedirs("./data", exist_ok=True)
    await auth_service.init()

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

    global _app_start_time
    _app_start_time = time.monotonic()

    # Register hot-reload callback
    config_manager.on_reload(lambda new, old: init_components(new))

    yield

    await request_logger.close()
    await auth_service.close()
    logger.info("MonoRelay shut down.")


app = FastAPI(
    title="MonoRelay",
    description="Configurable LLM API Relay Server supporting OpenRouter, NVIDIA NIM, OpenAI, and Anthropic",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config_manager.config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/v1/") or path.startswith("/api/"):
        # Public endpoints that don't require authentication
        public_endpoints = [
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/sso/login",
            "/api/auth/sso/callback",
            "/api/auth/sso/status",
            "/api/info",
            "/api/setup/status",
            "/api/providers/",
            "/api/logs",
            "/v1/models",
        ]

        # Use exact match or prefix for some, but be careful with /api/auth/
        is_public = any(path == ep or (ep.endswith("/") and path.startswith(ep)) for ep in public_endpoints)
        
        # Get token from headers
        auth_header = request.headers.get("authorization", "")
        token = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.headers.get("x-access-key", "")

        # Try local JWT authentication (SSO users get local JWTs after OAuth callback)
        if token:
            from .auth_utils import verify_token

            jwt_secret = config_manager.config.server.jwt_secret or ""
            user_id = verify_token(token, config_secret=jwt_secret)
            if user_id:
                user = await auth_service.user_manager.get_user_by_id(user_id)
                if user and user.is_active:
                    request.state.user = user
                    request.state.client_id = user.username
                    response = await call_next(request)
                    return response

        # Fallback to access_key authentication (for backward compatibility)
        # ONLY if enabled in config
        if config_manager.config.server.access_key_enabled:
            access_key = config_manager.config.server.access_key
            if token == access_key:
                request.state.client_id = token[:16] if len(token) >= 16 else token
                response = await call_next(request)
                return response

        if is_public:
            response = await call_next(request)
            return response

        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Unauthorized", "type": "auth_error"}},
        )

    response = await call_next(request)
    return response


@app.post("/api/auth/refresh")
async def api_auth_refresh(request: Request):
    """Refresh access token using refresh token."""
    body = await request.json()
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token required")
    
    token = await auth_service.refresh_token(refresh_token)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return token


def _get_resource_path(relative_path: str) -> Path:
    """获取资源路径，兼容 PyInstaller 打包环境。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(getattr(sys, '_MEIPASS')) / relative_path  # type: ignore[arg-type]
    return Path(__file__).resolve().parent.parent / relative_path


FRONTEND_DIR = _get_resource_path("frontend")
FRONTEND_DIST = FRONTEND_DIR / "dist"


@app.get("/")
async def serve_frontend():
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        index = FRONTEND_DIR / "index.html"
    
    if index.exists():
        # Read and inject a unique build ID to force browser to see it as new
        content = index.read_text(encoding="utf-8")
        build_id = str(time.time())
        if "</body>" in content:
            content = content.replace("</body>", f"<!-- build-id: {build_id} --></body>")
        
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({"error": "Frontend not found. Run `cd frontend && npm run build` first."}, status_code=404)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    if (FRONTEND_DIST / "favicon.svg").exists():
        @app.get("/favicon.svg")
        async def serve_favicon():
            return FileResponse(FRONTEND_DIST / "favicon.svg", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/api/setup/status")
async def api_setup_status():
    """Check if initial setup is needed."""
    has_users = await auth_service.has_users()
    return {
        "initialized": has_users,
        "needs_setup": not has_users,
    }


async def verify_turnstile(token: str) -> bool:
    """Verify Cloudflare Turnstile token."""
    cfg = config_manager.config.server
    if not cfg.turnstile_enabled or not cfg.turnstile_secret_key:
        return True
    
    if not token:
        return False
        
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": cfg.turnstile_secret_key,
                    "response": token,
                },
                timeout=10.0
            )
            data = resp.json()
            return data.get("success", False)
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return False


@app.post("/api/auth/register")
async def api_auth_register(request: Request):
    """Register a new user account."""
    body = await request.json()
    
    # Verify Turnstile
    if not await verify_turnstile(body.get("turnstile_token", "")):
        raise HTTPException(status_code=400, detail="Turnstile verification failed")
        
    user_data = UserCreate(
        username=body.get("username"),
        email=body.get("email"),
        password=body.get("password")
    )

    is_first = not await auth_service.has_users()
    token = await auth_service.register(user_data, is_first_user=is_first)
    return token


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """Login with username and password."""
    body = await request.json()
    
    # Verify Turnstile
    if not await verify_turnstile(body.get("turnstile_token", "")):
        raise HTTPException(status_code=400, detail="Turnstile verification failed")
        
    login_data = UserLogin(
        username=body.get("username"),
        password=body.get("password")
    )
    token = await auth_service.login(login_data)
    return token


@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Get current user info."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # We always return the DB user model
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "sso_provider": user.sso_provider,
        "sso_id": user.sso_id
    }


@app.post("/api/auth/change-password")
async def api_auth_change_password(request: Request):
    """Change current user password."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    body = await request.json()
    old_password = body.get("old_password")
    new_password = body.get("new_password")
    
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="old_password and new_password required")
    
    # Get fresh user data from DB
    db_user = await auth_service.user_manager.get_user_by_id(user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # For users who only have SSO login, they might not have a password set yet.
    # However, our UserManager currently sets a "SSO:..." random string.
    
    # Verify old password
    authenticated = await auth_service.user_manager.authenticate_user(db_user.username, old_password)
    if not authenticated:
        raise HTTPException(status_code=400, detail="Incorrect old password")
    
    # Change password
    success = await auth_service.user_manager.change_password(user.id, new_password)
    return {"success": success}


@app.get("/api/auth/sso/login")
async def api_auth_sso_login(request: Request):
    """Initiate OAuth SSO login flow."""
    global sso_validator
    
    if not sso_validator:
        raise HTTPException(status_code=400, detail="SSO not configured")
    
    redirect_uri = request.query_params.get("redirect_uri", "")
    
    import hashlib
    import base64
    
    session = sso_session_manager.create_session(redirect_uri=redirect_uri)
    code_verifier = session.code_verifier
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
    callback_url = f"{request.base_url}api/auth/sso/callback"
    logger.info(f"Initiating SSO login: callback_url={callback_url}")
    login_url = sso_validator.get_authorization_url(
        session.state, callback_url, code_verifier, code_challenge
    )
    
    return {"login_url": login_url, "state": session.state}


@app.get("/api/auth/sso/test-popup")
async def test_popup():
    """Test page to verify popup stays open."""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Popup Test</title>
        <style>
            body { 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                height: 100vh; 
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f5f5f5;
            }
            .box {
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            .green { color: #27ae60; }
            .count { font-size: 48px; font-weight: bold; color: #667eea; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1 class="green">Popup Test</h1>
            <p>弹窗测试页面</p>
            <p>Popup is working!</p>
            <div class="count" id="countdown">5</div>
            <p>秒后自动关闭 / Auto close in 5 seconds</p>
        </div>
        <script>
            let count = 5;
            const interval = setInterval(() => {
                count--;
                document.getElementById('countdown').textContent = count;
                if (count <= 0) {
                    clearInterval(interval);
                    window.close();
                }
            }, 1000);
        </script>
    </body>
    </html>
    """)


@app.get("/api/auth/sso/callback")
async def api_auth_sso_callback(request: Request):
    """Handle OAuth SSO callback - redirect with token in URL."""
    global sso_validator
    
    if not sso_validator:
        return HTMLResponse(content=_build_callback_html(error="SSO not configured"))
    
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error_desc = request.query_params.get("error_description") or request.query_params.get("error", "")
    
    if error_desc:
        return HTMLResponse(content=_build_callback_html(error=error_desc, state=state))
    
    if not code or not state:
        return HTMLResponse(content=_build_callback_html(error="Missing code or state", state=state))
    
    session = sso_session_manager.get_session(state)
    if not session:
        return HTMLResponse(content=_build_callback_html(error="Invalid or expired state", state=state))
    
    code_verifier = session.code_verifier
    sso_session_manager.remove_session(state)
    
    callback_url = f"{request.base_url}api/auth/sso/callback"
    tokens = await sso_validator.exchange_code(code, callback_url, code_verifier)
    
    if not tokens or not tokens.get("access_token"):
        return HTMLResponse(content=_build_callback_html(error="Failed to get access token", state=state))
    
    # Get user info from OAuth provider
    sso_user = await sso_validator.get_user_info(tokens["access_token"])
    if not sso_user:
        return HTMLResponse(content=_build_callback_html(error="Failed to get user info", state=state))
    
    try:
        cfg = config_manager.config
        is_admin_configured = sso_user.username in cfg.sso.admin_usernames
        
        # Find or create user in database
        user = await auth_service.user_manager.get_user_by_sso(sso_user.provider, sso_user.provider_id)
        if not user:
            # Try find by email to link
            existing_user = await auth_service.user_manager.get_user_by_email(sso_user.email)
            if existing_user:
                # Update user with SSO info and check admin status
                update_fields = {
                    "sso_provider": sso_user.provider,
                    "sso_id": sso_user.provider_id
                }
                if is_admin_configured:
                    update_fields["is_admin"] = True
                    
                user = await auth_service.user_manager.update_user(existing_user.id, **update_fields)
                logger.info(f"Linked existing user {user.username} to SSO {sso_user.unique_id}")
            else:
                # Create new user
                is_first = not await auth_service.has_users()
                is_admin = is_first or is_admin_configured
                
                user = await auth_service.user_manager.create_sso_user(
                    provider=sso_user.provider,
                    sso_id=sso_user.provider_id,
                    username=sso_user.username,
                    email=sso_user.email,
                    is_admin=is_admin
                )
                logger.info(f"Created new SSO user: {user.username} (admin={is_admin})")
        else:
            # Existing SSO user, check if we need to upgrade to admin
            if is_admin_configured and not user.is_admin:
                user = await auth_service.user_manager.update_user(user.id, is_admin=True)
                logger.info(f"Upgraded SSO user {user.username} to admin via config")
        
        # Generate local JWT token for MonoRelay using database user_id
        from .auth_utils import create_access_token
        local_token = create_access_token(
            user_id=user.id,
            config_secret=config_manager.config.server.jwt_secret or ""
        )
        
        logger.info(f"SSO callback success for user: {user.username}")
        return HTMLResponse(content=_build_callback_html(success=True, access_token=local_token, state=state))
        
    except Exception as e:
        logger.error(f"SSO callback processing error: {e}")
        return HTMLResponse(content=_build_callback_html(error=str(e), state=state))


def _build_callback_html(
    success: bool = False,
    error: str = None,
    access_token: str = None,
    state: str = None
) -> str:
    """Build HTML for SSO callback that communicates via postMessage and localStorage."""
    if success:
        message_html = f"""
            <div class="success-icon">✓</div>
            <p style="color: #27ae60; font-weight: 600;">登录成功！</p>
            <p style="color: #888; font-size: 14px; margin-top: 10px;">Login successful!</p>
            <p style="color: #888; font-size: 13px; margin-top: 20px;">窗口即将关闭...</p>
        """
        script = f"""
        <script>
        console.log('Callback loaded - success=true');
        const token = '{access_token}';
        const state = '{state}';
        
        // 1. Try postMessage to opener
        if (window.opener) {{
            try {{
                window.opener.postMessage({{
                    type: 'SSO_CALLBACK',
                    success: true,
                    access_token: token,
                    state: state
                }}, '*');
                console.log('postMessage sent');
            }} catch(e) {{
                console.error('postMessage failed:', e);
            }}
        }}
        
        // 2. Set localStorage as fallback for storage event listener
        try {{
            localStorage.setItem('sso_token', token);
            console.log('localStorage set');
        }} catch(e) {{
            console.error('localStorage failed:', e);
        }}
        
        // 3. Fallback redirect if everything else fails
        setTimeout(() => {{
            if (window.opener && !window.opener.closed) {{
                window.close();
            }} else {{
                window.location.href = '/?sso_success=true';
            }}
        }}, 1000);
        </script>
        """
    else:
        message_html = f"""
            <div class="error-icon">✗</div>
            <p style="color: #e74c3c; font-weight: 600;">登录失败</p>
            <p style="color: #888; font-size: 14px; margin-top: 10px;">{error or 'Unknown error'}</p>
            <p style="color: #888; font-size: 13px; margin-top: 20px;">请手动关闭此窗口</p>
        """
        script = f"""
        <script>
        if (window.opener) {{
            window.opener.postMessage({{
                type: 'SSO_CALLBACK',
                success: false,
                error: '{error or "Unknown error"}',
                state: '{state or ''}'
            }}, '*');
        }}
        </script>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SSO Callback</title>
        <style>
            body {{ 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                height: 100vh; 
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
            }}
            .status {{
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }}
            .spinner {{
                width: 40px;
                height: 40px;
                border: 3px solid #e0e0e0;
                border-top-color: #6c5ce7;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            .success-icon {{
                font-size: 48px;
                color: #27ae60;
                margin-bottom: 10px;
            }}
            .error-icon {{
                font-size: 48px;
                color: #e74c3c;
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="status">
            {message_html}
        </div>
        {script}
    </body>
    </html>
    """


@app.get("/api/auth/sso/status")
async def api_auth_sso_status():
    """Check SSO configuration status."""
    cfg = config_manager.config
    if not cfg.sso or not cfg.sso.enabled:
        return {"enabled": False, "provider": None, "configured": False}
    
    provider = cfg.sso.provider or "github"
    configured = bool(
        (provider == "prismaauth" and cfg.sso.prismaauth_url and cfg.sso.client_id and cfg.sso.client_secret) or
        (provider == "github" and cfg.sso.github_client_id and cfg.sso.github_client_secret) or
        (provider == "google" and cfg.sso.google_client_id and cfg.sso.google_client_secret)
    )
    
    return {
        "enabled": True,
        "provider": provider,
        "configured": configured,
        "sso_only": cfg.sso.sso_only,
    }


@app.post("/api/auth/sso/logout")
async def api_auth_sso_logout(request: Request):
    """Logout from SSO."""
    cfg = config_manager.config
    if not cfg.sso or not cfg.sso.enabled:
        raise HTTPException(status_code=400, detail="SSO is not enabled")

    body = await request.json()
    id_token = body.get("id_token")

    logout_url = f"{cfg.sso.keycloak_url}/realms/{cfg.sso.realm}/protocol/openid-connect/logout"
    if id_token:
        logout_url = f"{logout_url}?id_token_hint={id_token}"

    if cfg.sso.post_logout_uri:
        logout_url = f"{logout_url}&post_logout_redirect_uri={cfg.sso.post_logout_uri}"

    return {"logout_url": logout_url}


@app.get("/api/users")
async def api_list_users(request: Request):
    """List all users (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = await auth_service.user_manager.list_users()
    return {"users": [u.model_dump() for u in users]}


@app.put("/api/users/{user_id}")
async def api_update_user(user_id: int, request: Request):
    """Update user info (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    body = await request.json()
    # Don't allow updating sensitive fields like id or password_hash here
    allowed_updates = {k: v for k, v in body.items() if k in {"is_active", "is_admin", "email"}}
    updated = await auth_service.user_manager.update_user(user_id, **allowed_updates)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@app.delete("/api/users/{user_id}")
async def api_delete_user(user_id: int, request: Request):
    """Delete user (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
    success = await auth_service.user_manager.delete_user(user_id)
    return {"success": success}


@app.post("/api/admin/clear-data")
async def api_admin_clear_data(request: Request):
    """Clear all local data and reset system (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    logger.warning(f"SYSTEM RESET INITIATED BY {user.username}")
    
    try:
        import os
        import shutil
        from pathlib import Path
        
        data_dir = Path("./data")
        config_file = Path("./config.yml")
        
        # 1. Close database connections first
        await auth_service.user_manager.close()
        
        # 2. Delete data directory contents
        if data_dir.exists():
            shutil.rmtree(data_dir)
            data_dir.mkdir(exist_ok=True)
            logger.info("Data directory cleared")
            
        # 3. Reset config file to example if exists
        if config_file.exists():
            example = Path("./config.yml.example")
            if example.exists():
                shutil.copy(example, config_file)
            else:
                config_file.unlink()
            logger.info("Config file reset")
            
        # 4. Schedule self-termination
        import signal
        os.kill(os.getpid(), signal.SIGINT)
        
        return {"status": "ok", "message": "System reset initiated"}
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info")
async def api_info():
    """Return server connection info for dashboard."""
    import socket
    
    cfg = config_manager.config
    public_host = getattr(cfg.server, 'public_host', None) or ""
    
    if public_host:
        local_ip = public_host
    else:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"

    return {
        "local_ip": local_ip,
        "host": cfg.server.host,
        "port": cfg.server.port,
        "access_key": cfg.server.access_key,
        "access_key_enabled": cfg.server.access_key_enabled,
        "base_url": f"http://{local_ip}/v1",
    }


@app.get("/health")
async def health(turnstile_token: str = ""):
    # Verify Turnstile if enabled (for key-based access or just general protection)
    if not await verify_turnstile(turnstile_token):
         raise HTTPException(status_code=400, detail="Turnstile verification failed")
         
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


# Per-client usage tracking
@app.get("/api/usage/stats")
async def api_usage_stats(client_id: str | None = None):
    return api_response(data=usage_tracker.get_stats(client_id))


@app.post("/api/usage/clear")
async def api_usage_clear(client_id: str | None = None):
    """Clear usage stats, optionally for a specific client."""
    usage_tracker.clear(client_id)
    return {"status": "ok", "message": f"Usage stats cleared{' for: ' + client_id if client_id else ''}"}


# Response cache management
@app.get("/api/cache/stats")
async def api_cache_stats():
    """Get response cache statistics."""
    return response_cache.stats()


@app.post("/api/cache/clear")
async def api_cache_clear(model: str | None = None):
    """Clear response cache, optionally for a specific model only."""
    response_cache.invalidate(model)
    return {"status": "ok", "message": f"Cache cleared{' for model: ' + model if model else ''}"}


@app.post("/api/cache/enable")
async def api_cache_enable(enabled: bool = True, ttl_seconds: int = 300, max_size: int = 1000):
    """Enable/disable response cache and configure parameters."""
    if enabled:
        response_cache._max_size = max_size
        response_cache._ttl_seconds = ttl_seconds
    return {"status": "ok", "enabled": enabled, "ttl_seconds": response_cache._ttl_seconds, "max_size": response_cache._max_size}


# OpenAI-compatible endpoints
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    result = await handle_chat_completions(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    result = await handle_completions(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    result = await handle_embeddings(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/v1/models")
async def models_list():
    return await handle_models_list(config_manager.config)


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    file: UploadFile,
    model: str = Form(...),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str | None = Form(None),
    temperature: float | None = Form(None),
):
    form_data = {"model": model}
    if language:
        form_data["language"] = language
    if prompt:
        form_data["prompt"] = prompt
    if response_format:
        form_data["response_format"] = response_format
    if temperature is not None:
        form_data["temperature"] = temperature
    result = await handle_audio_transcriptions(
        form_data, file, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/v1/images/generations")
async def images_generations(request: Request):
    body = await request.json()
    result = await handle_image_generations(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


# Anthropic-compatible endpoints
@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    result = await handle_messages(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=503, content=result)
    return result


# Management API
@app.get("/api/stats")
async def api_stats():
    summary = stats_tracker.get_summary()
    db_stats = await request_logger.get_stats_summary()
    return api_response(data={
        "in_memory": summary,
        "persistent": db_stats,
        "keys": key_manager.get_stats(),
        "models": stats_tracker.get_model_details(),
    })


@app.get("/api/logs")
async def api_logs(page: int = 1, page_size: int = 20, limit: int = 50):
    if limit < page_size:
        page_size = limit
    logs = await request_logger.get_recent_requests(limit)
    total = len(logs)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = logs[start:end]
    return api_response(data=paginated, page=page, page_size=page_size, total=total)


@app.get("/api/stats/file")
async def api_stats_file():
    """返回 stats.json 原始内容。"""
    path = stats_tracker.db_path
    if not path.exists():
        return {"content": "{}"}
    return {"content": path.read_text(encoding="utf-8")}


# ========== Analytics Endpoints ==========

@app.get("/api/analytics/overview")
async def api_analytics_overview(
    start_date: str | None = None,
    end_date: str | None = None,
):
    """返回成本和用量摘要，支持日期范围过滤。"""
    from datetime import datetime, timedelta
    
    # Default to last 7 days
    today = datetime.now()
    default_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    default_end = today.strftime("%Y-%m-%d")
    
    start = start_date or default_start
    end = end_date or default_end
    
    # Convert to timestamps for DB query
    start_ts = datetime.strptime(start, "%Y-%m-%d").timestamp()
    end_ts = datetime.strptime(end, "%Y-%m-%d").timestamp() + 86400  # End of day
    
    # Query request logger for date-filtered stats
    db_stats = {}
    if request_logger._db:
        cursor = await request_logger._db.execute(
            """
            SELECT
                COUNT(*) as total_requests,
                COALESCE(SUM(estimated_cost), 0) as total_cost,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output,
                provider,
                model
            FROM requests
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY provider, model
            """,
            (start_ts, end_ts)
        )
        rows = await cursor.fetchall()
        db_stats = [dict(row) for row in rows]
    
    # Aggregate by provider
    by_provider: dict[str, dict] = {}
    # Aggregate by model
    by_model: dict[str, dict] = {}
    total_requests = 0
    total_cost = 0.0
    total_input = 0
    total_output = 0
    
    for row in db_stats:
        prov = row.get("provider", "unknown")
        model = row.get("model", "unknown")
        req_count = row.get("total_requests", 0) or 0
        cost = float(row.get("total_cost", 0) or 0)
        inp = int(row.get("total_input", 0) or 0)
        out = int(row.get("total_output", 0) or 0)
        
        total_requests += req_count
        total_cost += cost
        total_input += inp
        total_output += out
        
        if prov not in by_provider:
            by_provider[prov] = {"requests": 0, "cost": 0.0}
        by_provider[prov]["requests"] += req_count
        by_provider[prov]["cost"] += cost
        
        if model not in by_model:
            by_model[model] = {"requests": 0, "cost": 0.0, "tokens": 0}
        by_model[model]["requests"] += req_count
        by_model[model]["cost"] += cost
        by_model[model]["tokens"] += inp + out
    
    return api_response(data={
        "period": {"start": start, "end": end},
        "total_requests": total_requests,
        "total_cost": round(total_cost, 2),
        "total_tokens": {"input": total_input, "output": total_output},
        "by_provider": by_provider,
        "by_model": by_model,
    })


@app.get("/api/analytics/slow-queries")
async def api_analytics_slow_queries(
    threshold_ms: int = 5000,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
):
    """返回超过延迟阈值的慢查询。"""
    from datetime import datetime, timedelta
    
    # Default to last 7 days
    today = datetime.now()
    default_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    default_end = today.strftime("%Y-%m-%d")
    
    start = start_date or default_start
    end = end_date or default_end
    
    start_ts = datetime.strptime(start, "%Y-%m-%d").timestamp()
    end_ts = datetime.strptime(end, "%Y-%m-%d").timestamp() + 86400
    
    slow_queries = []
    total = 0
    
    if request_logger._db:
        cursor = await request_logger._db.execute(
            """
            SELECT 
                timestamp, model, provider, latency_ms, 
                COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0) as tokens
            FROM requests
            WHERE timestamp >= ? AND timestamp < ? AND latency_ms > ?
            ORDER BY latency_ms DESC
            LIMIT ?
            """,
            (start_ts, end_ts, threshold_ms, limit)
        )
        rows = await cursor.fetchall()
        
        for row in rows:
            ts = datetime.fromtimestamp(row[0])
            slow_queries.append({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "model": row[1],
                "provider": row[2],
                "latency_ms": round(row[3], 1) if row[3] else 0,
                "tokens": row[4] or 0,
            })
        
        # Get total count
        cursor = await request_logger._db.execute(
            "SELECT COUNT(*) FROM requests WHERE timestamp >= ? AND timestamp < ? AND latency_ms > ?",
            (start_ts, end_ts, threshold_ms)
        )
        total = (await cursor.fetchone())[0] or 0
    
    return api_response(data={
        "threshold_ms": threshold_ms,
        "slow_queries": slow_queries,
        "total": total,
    })


@app.get("/api/analytics/cost-distribution")
async def api_analytics_cost_distribution(
    start_date: str | None = None,
    end_date: str | None = None,
):
    """返回成本分布：按提供商和按模型。"""
    from datetime import datetime, timedelta
    
    # Default to last 7 days
    today = datetime.now()
    default_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    default_end = today.strftime("%Y-%m-%d")
    
    start = start_date or default_start
    end = end_date or default_end
    
    start_ts = datetime.strptime(start, "%Y-%m-%d").timestamp()
    end_ts = datetime.strptime(end, "%Y-%m-%d").timestamp() + 86400
    
    provider_costs: dict[str, float] = {}
    model_costs: dict[str, float] = {}
    total_cost = 0.0
    
    if request_logger._db:
        cursor = await request_logger._db.execute(
            """
            SELECT provider, model, COALESCE(SUM(estimated_cost), 0) as cost
            FROM requests
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY provider, model
            """,
            (start_ts, end_ts)
        )
        rows = await cursor.fetchall()
        
        for row in rows:
            prov = row[0] or "unknown"
            model = row[1] or "unknown"
            cost = float(row[2] or 0)
            
            total_cost += cost
            provider_costs[prov] = provider_costs.get(prov, 0) + cost
            model_costs[model] = model_costs.get(model, 0) + cost
    
    # Build provider breakdown
    by_provider = []
    for prov, cost in sorted(provider_costs.items(), key=lambda x: x[1], reverse=True):
        pct = round((cost / total_cost * 100), 1) if total_cost > 0 else 0
        by_provider.append({"provider": prov, "cost": round(cost, 2), "percentage": pct})
    
    # Build model breakdown
    by_model = []
    for model, cost in sorted(model_costs.items(), key=lambda x: x[1], reverse=True):
        pct = round((cost / total_cost * 100), 1) if total_cost > 0 else 0
        by_model.append({"model": model, "cost": round(cost, 2), "percentage": pct})
    
    return api_response(data={
        "total_cost": round(total_cost, 2),
        "by_provider": by_provider,
        "by_model": by_model,
    })


# ========== End Analytics ==========


@app.put("/api/stats/file")
async def api_update_stats_file(request: Request):
    """更新 stats.json 内容。"""
    body = await request.json()
    content = body.get("content", "{}")
    path = stats_tracker.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    stats_tracker._load()
    return {"status": "ok", "message": "统计数据已更新"}


@app.get("/api/config/full")
async def api_get_full_config(request: Request):
    """Get full configuration object (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Return everything except sensitive secrets if possible
    cfg = config_manager.config.model_copy(deep=True)
    return cfg


@app.put("/api/config/full")
async def api_update_full_config(request: Request):
    """Update full configuration object (admin only)."""
    user = getattr(request.state, "user", None)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    body = await request.json()
    try:
        # Validate against Pydantic model
        new_cfg = AppConfig(**body)
        
        # Save to file
        config_manager.save(new_cfg)
        
        # Immediate component reload
        init_components(new_cfg)
        
        return {"status": "ok", "message": "Settings updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}")


@app.get("/api/config")
async def api_get_config():
    """返回原始配置文件内容（保留注释）。"""
    path = config_manager.config_path
    if path.exists():
        content = path.read_text(encoding="utf-8")
        # 简单脱敏：如果包含 gist_token，将其替换
        # 注意：正常情况下 config.yml 不存 token，token 在 sync.json
        return {"content": content}
    return {"content": ""}


@app.put("/api/config")
async def api_update_config(request: Request):
    try:
        body = await request.json()
        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="Content required")

        import yaml
        # 1. 验证 YAML 语法
        try:
            raw = yaml.safe_load(content)
            # 2. 验证模型结构
            new_cfg = AppConfig(**raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"YAML 或配置格式错误: {e}")

        # 3. 直接写入原始文本（保留注释）
        config_manager.config_path.write_text(content, encoding="utf-8")
        
        # 4. 热重载内存中的配置
        config_manager.reload()
        init_components(config_manager.config)

        # Auto-push to Gist if sync is enabled
        sc = config_manager.config.sync
        if sc.enabled and sync_storage.has_token:
            # ... (rest of push logic)
            import asyncio
            import yaml
            from .sync import GistSync
            content = yaml.dump(new_cfg.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)
            stats_content = None
            if stats_tracker.db_path.exists():
                try:
                    stats_content = stats_tracker.db_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            sync = GistSync(sync_storage.gist_token, sc.gist_id)
            asyncio.create_task(_push_to_gist(sync, content, stats_content, new_cfg))

        return {"status": "ok", "message": "Configuration updated and reloaded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _push_to_gist(sync, content, stats_content, cfg):
    """保存配置后自动推送完整内容到 Gist 的后台任务。"""
    import logging
    logger = logging.getLogger("monorelay.sync")
    logger.info(f"后台推送: token_len={len(sync._token)}, gist_id={sync.gist_id}")
    try:
        ok = await sync.push(content, stats_content)
        if ok and sync.gist_id and sync.gist_id != cfg.sync.gist_id:
            new_cfg = cfg.model_copy(deep=True)
            new_cfg.sync.gist_id = sync.gist_id
            config_manager.save(new_cfg)
    except Exception as e:
        logger.warning(f"自动同步推送失败: {e}")


@app.get("/api/providers")
async def api_providers(page: int = 1, page_size: int = 20):
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
    
    providers_list = list(result.items())
    total = len(providers_list)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = dict(providers_list[start:end])
    
    return api_response(data=paginated, page=page, page_size=page_size, total=total)


@app.post("/api/providers/{name}/test")
async def api_test_provider(name: str, request: Request):
    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    if not pc.keys:
        return {"status": "error", "message": "No keys configured"}

    body = {}
    try:
        body = await request.json()
    except:
        pass
    test_model = body.get("model", pc.test_model)
    
    if not test_model:
        return {"status": "error", "message": "No test model specified"}

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
                },
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # API type - test with the specified model
    url = pc.base_url
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {pc.keys[0].key}",
        "Content-Type": "application/json",
    }
    if pc.headers:
        headers.update(pc.headers)
    
    try:
        # Strip provider suffix if present
        if "@" in test_model:
            test_model = test_model.rsplit("@", 1)[0]
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json={
                "model": test_model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }, timeout=30.0)
            if resp.status_code == 200:
                return {"status": "ok", "message": f"连接成功: {test_model}"}
            else:
                return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "请求超时"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/providers/{name}/verify")
async def api_verify_provider(name: str, request: VerifyRequest):

    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    if not pc.keys:
        raise HTTPException(status_code=400, detail="No keys configured")

    if pc.provider_type == "web_reverse":
        raise HTTPException(status_code=400, detail="web_reverse provider type not supported for verify")

    test_models = {
        "openrouter": "openai/gpt-4o-mini",
        "nvidia": "meta/llama-3.1-8b-instruct",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "deepseek": "deepseek-chat",
    }
    test_model = request.model or pc.test_model or test_models.get(name, "gpt-4o-mini")

    url = pc.base_url
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {pc.keys[0].key}",
        "Content-Type": "application/json",
    }
    if pc.headers:
        headers.update(pc.headers)

    async def probe_text_gen() -> dict[str, Any]:
        start = time.monotonic()
        payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            if resp.status_code >= 400:
                return {
                    "status": "fail",
                    "latency_ms": latency_ms,
                    "error": f"HTTP {resp.status_code}",
                    "summary": f"Request failed with HTTP {resp.status_code}",
                }

            body = resp.json()
            choices = body.get("choices", [])
            if choices and choices[0].get("message", {}).get("content"):
                return {
                    "status": "pass",
                    "latency_ms": latency_ms,
                    "error": None,
                    "summary": "Text generation works",
                }
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "error": "No content in response",
                "summary": "Empty response content",
            }
        except httpx.TimeoutException:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "error": "Timeout",
                "summary": "Request timed out",
            }
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "error": type(e).__name__,
                "summary": f"Error: {type(e).__name__}",
            }

    async def probe_tool_call() -> dict[str, Any]:
        start = time.monotonic()

        payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "description": "A simple calculator",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "expression": {"type": "string", "description": "Math expression"}
                            },
                            "required": ["expression"],
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "calculator"}},
            "max_tokens": 50,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            try:
                body = resp.json()
            except Exception:
                body = {}

            if resp.status_code >= 400:
                if resp.status_code in (400, 403):
                    error_msg = body.get("error", {}).get("message", "")
                    if "tool" in error_msg.lower() or "function" in error_msg.lower():
                        return {
                            "status": "unsupported",
                            "latency_ms": latency_ms,
                            "error": "tools_not_supported",
                            "summary": "Tool calling not supported by this provider",
                        }
                return {
                    "status": "fail",
                    "latency_ms": latency_ms,
                    "error": f"HTTP {resp.status_code}",
                    "summary": f"Request failed with HTTP {resp.status_code}",
                }

            choices = body.get("choices", [])
            first_choice = choices[0] if choices else {}
            message = first_choice.get("message", {})
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                return {
                    "status": "pass",
                    "latency_ms": latency_ms,
                    "error": None,
                    "summary": "Tool calling works",
                }
            if first_choice.get("finish_reason") == "tool_calls":
                return {
                    "status": "pass",
                    "latency_ms": latency_ms,
                    "error": None,
                    "summary": "Tool calling works",
                }
            return {
                "status": "unsupported",
                "latency_ms": latency_ms,
                "error": "no_tool_calls",
                "summary": "Tool calling returned no tool calls",
            }
        except httpx.TimeoutException:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "error": "Timeout",
                "summary": "Request timed out",
            }
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "error": type(e).__name__,
                "summary": f"Error: {type(e).__name__}",
            }

    async def probe_streaming() -> dict[str, Any]:
        start = time.monotonic()
        first_token_ms = None

        payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "Count from 1 to 5"}],
            "max_tokens": 30,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, headers=headers, json=payload, timeout=15.0) as resp:
                    if resp.status_code >= 400:
                        latency_ms = round((time.monotonic() - start) * 1000, 1)
                        return {
                            "status": "fail",
                            "latency_ms": latency_ms,
                            "first_token_ms": None,
                            "error": f"HTTP {resp.status_code}",
                            "summary": f"Request failed with HTTP {resp.status_code}",
                        }

                    async for chunk in resp.aiter_bytes():
                        if first_token_ms is None and chunk:
                            first_token_ms = round((time.monotonic() - start) * 1000, 1)
                        if b"[DONE]" in chunk or b"data: [DONE]" in chunk:
                            break

            latency_ms = round((time.monotonic() - start) * 1000, 1)

            if first_token_ms is not None:
                return {
                    "status": "pass",
                    "latency_ms": latency_ms,
                    "first_token_ms": first_token_ms,
                    "error": None,
                    "summary": "Streaming works",
                }
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "first_token_ms": None,
                "error": "No tokens received",
                "summary": "No streaming data received",
            }
        except httpx.TimeoutException:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "first_token_ms": None,
                "error": "Timeout",
                "summary": "Request timed out",
            }
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "first_token_ms": None,
                "error": type(e).__name__,
                "summary": f"Error: {type(e).__name__}",
            }

    probe_map = {
        "text-gen": probe_text_gen,
        "tool-call": probe_tool_call,
        "streaming": probe_streaming,
    }

    results = {}
    tasks = []
    probe_names = []

    for probe_type in request.probe_types:
        if probe_type in probe_map:
            tasks.append(probe_map[probe_type]())
            probe_names.append(probe_type)
        else:
            results[probe_type] = {
                "status": "fail",
                "latency_ms": 0,
                "error": "unknown_probe_type",
                "summary": f"Unknown probe type: {probe_type}",
            }

    if tasks:
        probe_results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(probe_names, probe_results):
            if isinstance(result, Exception):
                results[name] = {
                    "status": "fail",
                    "latency_ms": 0,
                    "error": type(result).__name__,
                    "summary": f"Error: {type(result).__name__}",
                }
            else:
                results[name] = result

    overall_status = "pass"
    for result in results.values():
        if result.get("status") == "fail":
            overall_status = "fail"
            break
        elif result.get("status") == "unsupported" and overall_status != "fail":
            overall_status = "partial"

    return {
        "provider": name,
        "model": test_model,
        "probes": results,
        "overall_status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Batch health check - inspired by all-api-hub
@app.post("/api/health-check")
async def api_health_check():
    results: dict[str, Any] = {}

    def calculate_latency_trend(history: list[int]) -> str:
        if len(history) < 2:
            return "stable"
        recent = history[-2:]
        diff = recent[1] - recent[0]
        if diff > 100:
            return "up"
        elif diff < -100:
            return "down"
        return "stable"

    def detect_issues(key_results: list[dict[str, Any]], avg_latency: float | None) -> list[str]:
        issues = []
        statuses = [k.get("status") for k in key_results]
        enabled_statuses = [s for s in statuses if s != "disabled"]

        if not enabled_statuses:
            return issues

        all_rate_limited = all(s == "rate_limited" for s in enabled_statuses)
        all_error = all(s == "error" for s in enabled_statuses)
        all_timeout = all(s == "timeout" for s in enabled_statuses)

        if all_rate_limited:
            issues.append("rate_limited_issue")
        if all_error:
            issues.append("provider_error")
        if all_timeout:
            issues.append("timeout_issue")
        if avg_latency is not None and avg_latency > 5000:
            issues.append("latency_issue")

        return issues

    for name, pc in config_manager.config.providers.items():
        if not pc.enabled or not pc.keys:
            results[name] = {"enabled": pc.enabled, "status": "skipped", "message": "Provider disabled or no keys"}
            continue

        key_results = []
        provider_latencies = []

        for idx, pk in enumerate(pc.keys):
            if not pk.enabled:
                key_results.append({"index": idx, "label": pk.label, "status": "disabled"})
                continue

            if pc.provider_type == "web_reverse":
                try:
                    from .web_reverse.chatgpt import WebReverseService
                    wr_cfg = pc.web_reverse.model_dump() if pc.web_reverse else {}
                    service = WebReverseService(name, wr_cfg)
                    await service.prepare(pk.key)
                    ok = bool(service.chat_token)
                    key_results.append({
                        "index": idx, "label": pk.label,
                        "status": "ok" if ok else "error",
                        "message": "ChatGPT session valid" if ok else "ChatGPT session invalid",
                    })
                except Exception as e:
                    key_results.append({"index": idx, "label": pk.label, "status": "error", "message": str(e)})
            else:
                test_models = {
                    "openrouter": "openai/gpt-4o-mini",
                    "nvidia": "meta/llama-3.1-8b-instruct",
                    "openai": "gpt-4o-mini",
                    "anthropic": "claude-3-haiku-20240307",
                    "deepseek": "deepseek-chat",
                    "groq": "llama-3.1-8b-instant",
                }
                test_model = pc.test_model or test_models.get(name, "gpt-4o-mini")
                test_url = pc.base_url
                if not test_url.endswith("/chat/completions"):
                    test_url = f"{test_url}/chat/completions"
                test_headers = {
                    "Authorization": f"Bearer {pk.key}",
                    "Content-Type": "application/json",
                    **(pc.headers or {}),
                }
                try:
                    start = time.monotonic()
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            test_url,
                            headers=test_headers,
                            json={"model": test_model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1},
                            timeout=15.0,
                        )
                    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
                    provider_latencies.append(elapsed_ms)
                    status = "ok" if resp.status_code < 400 else ("rate_limited" if resp.status_code == 429 else "error")
                    key_results.append({
                        "index": idx, "label": pk.label, "status": status,
                        "latency_ms": elapsed_ms, "http_status": resp.status_code,
                    })
                except httpx.TimeoutException:
                    key_results.append({"index": idx, "label": pk.label, "status": "timeout"})
                except Exception as e:
                    key_results.append({"index": idx, "label": pk.label, "status": "error", "message": str(e)})

        ok_count = sum(1 for k in key_results if k["status"] == "ok")
        current_latency = provider_latencies[0] if provider_latencies else None

        if current_latency is not None:
            history = HEALTH_CHECK_HISTORY.get(name, [])
            history.append(int(current_latency))
            if len(history) > HEALTH_CHECK_MAX_HISTORY:
                history = history[-HEALTH_CHECK_MAX_HISTORY:]
            HEALTH_CHECK_HISTORY[name] = history

        history = HEALTH_CHECK_HISTORY.get(name, [])
        avg_latency = round(sum(history) / len(history), 1) if history else None
        trend = calculate_latency_trend(history) if history else "stable"
        issues = detect_issues(key_results, avg_latency)

        results[name] = {
            "enabled": pc.enabled,
            "total_keys": len(pc.keys),
            "healthy_keys": ok_count,
            "status": "healthy" if ok_count > 0 else "degraded",
            "issues": issues,
            "latency": {
                "current_ms": current_latency,
                "avg_ms": avg_latency,
                "trend": trend,
                "history": history,
            },
            "keys": key_results,
        }

    total_healthy = sum(1 for r in results.values() if r.get("status") == "healthy")
    total_degraded = sum(1 for r in results.values() if r.get("status") == "degraded")
    issues_detected = []
    for name, r in results.items():
        if r.get("issues"):
            for issue in r["issues"]:
                issues_detected.append(f"{name}: {issue}")

    return {
        "providers": results,
        "summary": {
            "total": len(results),
            "healthy": total_healthy,
            "degraded": total_degraded,
            "issues_detected": issues_detected,
        },
    }


# API Key export - inspired by all-api-hub one-click export
@app.get("/api/export/keys/{provider_name}")
async def api_export_keys(provider_name: str, format: str = "openai"):
    """Export provider keys in various client formats."""
    pc = config_manager.config.providers.get(provider_name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    enabled_keys = [k for k in pc.keys if k.enabled]
    if not enabled_keys:
        return {"format": format, "provider": provider_name, "content": "", "message": "No enabled keys"}

    base_url = pc.base_url
    if pc.provider_type != "web_reverse" and not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/")

    cfg = config_manager.config
    public_host = getattr(cfg.server, 'public_host', None) or ""
    
    if public_host:
        local_ip = public_host
    else:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"
    server_base_url = f"http://{local_ip}/v1"

    exports = []
    for pk in enabled_keys:
        if format == "openai":
            exports.append(f"OPENAI_API_KEY={pk.key}\nOPENAI_BASE_URL={base_url}")
        elif format == "anthropic":
            exports.append(f"ANTHROPIC_API_KEY={pk.key}\nANTHROPIC_BASE_URL={base_url}")
        elif format == "claude-code":
            exports.append(f"# {pk.label}\nexport ANTHROPIC_BASE_URL='{base_url}'\nexport ANTHROPIC_API_KEY='{pk.key}'")
        elif format == "claude-code-router":
            exports.append(f"# Claude Code Router config\nexport ANTHROPIC_BASE_URL='{server_base_url}'\nexport ANTHROPIC_API_KEY='{pk.key}'")
        elif format == "cherrystudio":
            exports.append(f"# {provider_name} - {pk.label}\nAPI: {base_url}\nKey: {pk.key}")
        elif format == "cherrystudio-deep-link":
            import base64
            deep_link_data = {
                "provider": provider_name,
                "name": "MonoRelay",
                "api_key": pk.key,
                "base_url": server_base_url,
            }
            encoded = base64.b64encode(json.dumps(deep_link_data).encode()).decode()
            exports.append(f"cherrystudio://providers/api-keys?v=1&data={encoded}")
        elif format == "vercel-ai-sdk":
            import json as json_module
            sdk_config = {
                "providers": [{
                    "provider": provider_name,
                    "baseURL": server_base_url,
                    "apiKey": pk.key,
                    "models": {
                        "default": ["gpt-4o-mini", "gpt-4o"],
                        "fetchWith": ["gpt-4o-mini", "gpt-4o"],
                    },
                }]
            }
            exports.append(json_module.dumps(sdk_config, indent=2))
        elif format == "llama.cpp":
            import json as json_module
            llama_config = {
                "model_alias": "monorelay",
                "api_key": pk.key,
                "base_url": server_base_url,
            }
            exports.append(json_module.dumps(llama_config, indent=2))
        elif format == "curl":
            exports.append(f"curl {base_url}/v1/chat/completions -H 'Authorization: Bearer {pk.key}' -H 'Content-Type: application/json' -d '{{\"model\":\"gpt-4o-mini\",\"messages\":[{{\"role\":\"user\",\"content\":\"Hi\"}}]}}'")
        elif format == "env":
            exports.append(f"MONORELAY_{provider_name.upper()}_KEY={pk.key}")
        else:
            exports.append(f"{pk.label}: {pk.key[:8]}...")

    return {
        "format": format, "provider": provider_name,
        "content": "\n\n".join(exports),
        "key_count": len(enabled_keys),
    }


# Enhanced stats API with per-provider analytics
@app.get("/api/stats/enhanced")
async def api_enhanced_stats():
    summary = stats_tracker.get_summary()
    model_details = stats_tracker.get_model_details()

    provider_breakdown = {}
    for name, pc in config_manager.config.providers.items():
        if not pc.enabled:
            continue
        prov_stats = summary.get("by_provider", {}).get(name, {})
        key_stats = key_manager.get_stats().get(name, {})
        provider_breakdown[name] = {
            "enabled": pc.enabled,
            "total_requests": prov_stats.get("requests", 0),
            "total_errors": prov_stats.get("errors", 0),
            "keys": {
                "total": len(pc.keys),
                "enabled": sum(1 for k in pc.keys if k.enabled),
                "details": key_stats.get("keys", []),
            },
            "cost_per_m_input": pc.cost_per_m_input,
            "cost_per_m_output": pc.cost_per_m_output,
        }

    key_health = []
    for name, pc in config_manager.config.providers.items():
        for idx, pk in enumerate(pc.keys):
            key_stats = key_manager.get_stats().get(name, {}).get("keys", [])
            ks = key_stats[idx] if idx < len(key_stats) else {}
            key_health.append({
                "provider": name, "label": pk.label, "enabled": pk.enabled,
                "total_requests": ks.get("total_requests", 0),
                "total_failures": ks.get("total_failures", 0),
                "is_available": ks.get("is_available", pk.enabled),
                "cooldown_until": ks.get("cooldown_until"),
                "quota_limit": pk.quota_limit,
                "quota_used": pk.quota_used,
                "rate_limit_rps": pk.rate_limit_rps,
                "expires_at": pk.expires_at,
            })

    return api_response(data={
        "summary": summary,
        "provider_breakdown": provider_breakdown,
        "model_details": model_details,
        "key_health": key_health,
    })


# Model pricing comparison endpoint
@app.get("/api/models/pricing")
async def api_model_pricing():
    """Return model pricing information from provider configurations."""
    pricing = []
    seen_models: dict[str, dict] = {}

    for name, pc in config_manager.config.providers.items():
        if not pc.enabled:
            continue
        include_list = pc.models.get("include", []) if pc.models else []
        if not include_list:
            continue

        for model_id in include_list:
            if model_id not in seen_models:
                seen_models[model_id] = {
                    "model": model_id,
                    "input_per_1m": pc.cost_per_m_input,
                    "output_per_1m": pc.cost_per_m_output,
                    "available_on": [name],
                }
            else:
                seen_models[model_id]["available_on"].append(name)

    pricing = list(seen_models.values())
    pricing.sort(key=lambda x: x["input_per_1m"] + x["output_per_1m"])
    return {"models": pricing, "currency": "USD"}


# Key import endpoint - inspired by all-api-hub one-click import
@app.post("/api/providers/{name}/keys/import")
async def api_import_keys(name: str, request: Request):
    """Import keys from various formats: raw text (one per line), JSON array, or CSV."""
    body = await request.json()
    content = body.get("content", "")
    fmt = body.get("format", "raw")

    pc = config_manager.config.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    new_keys = []
    if fmt == "json":
        import json as _json
        try:
            items = _json.loads(content)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        new_keys.append({"key": item.strip(), "label": f"imported-{len(new_keys)+1}"})
                    elif isinstance(item, dict):
                        new_keys.append({
                            "key": item.get("key", item.get("api_key", "")),
                            "label": item.get("label", item.get("name", f"imported-{len(new_keys)+1}")),
                            "weight": int(item.get("weight", 1)),
                        })
            elif isinstance(items, dict):
                for k, v in items.items():
                    new_keys.append({"key": str(v), "label": k})
        except _json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")
    elif fmt == "csv":
        for line in content.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                new_keys.append({"key": parts[0], "label": parts[1]})
            elif len(parts) == 1 and parts[0]:
                new_keys.append({"key": parts[0], "label": f"imported-{len(new_keys)+1}"})
    else:
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    parts = line.split("=", 1)
                    new_keys.append({"key": parts[1].strip().strip("'\""), "label": parts[0].strip()})
                else:
                    new_keys.append({"key": line, "label": f"imported-{len(new_keys)+1}"})

    existing_labels = {k.label for k in pc.keys}
    added = 0
    for nk in new_keys:
        if nk["key"] not in [k.key for k in pc.keys]:
            label = nk["label"]
            if label in existing_labels:
                label = f"{label}-{len(pc.keys)+1}"
            from .models import ProviderKey
            pc.keys.append(ProviderKey(key=nk["key"], label=label, weight=nk.get("weight", 1)))
            existing_labels.add(label)
            added += 1

    if added > 0:
        cfg = config_manager.config.model_copy(deep=True)
        cfg.providers[name] = pc
        config_manager.save(cfg)
        init_components(cfg)

    return {"status": "ok", "added": added, "total": len(pc.keys), "skipped": len(new_keys) - added}


# Request log filtering - inspired by all-api-hub usage analysis
@app.get("/api/logs/filtered")
async def api_logs_filtered(
    provider: str | None = None,
    model: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    page: int = 1,
    page_size: int = 20,
):
    filters = {}
    if provider:
        filters["provider"] = provider
    if model:
        filters["model"] = model
    if status:
        filters["status"] = status
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    logs = await request_logger.get_recent_requests(limit * 5)
    entries = logs if isinstance(logs, list) else logs.get("entries", [])

    filtered = []
    for entry in entries:
        if provider and entry.get("provider") != provider:
            continue
        if model and model.lower() not in entry.get("model", "").lower():
            continue
        if status:
            entry_status = "success" if entry.get("status_code", 500) < 400 else "error"
            if entry_status != status:
                continue
        if date_from:
            entry_time = entry.get("timestamp", "")
            if entry_time and entry_time < date_from:
                continue
        if date_to:
            entry_time = entry.get("timestamp", "")
            if entry_time and entry_time > date_to:
                continue
        filtered.append(entry)
        if len(filtered) >= limit:
            break

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = filtered[start:end]

    return api_response(
        data={
            "entries": paginated,
            "filters_applied": {k: v for k, v in {"provider": provider, "model": model, "status": status}.items() if v},
        },
        page=page,
        page_size=page_size,
        total=total,
    )


# System info endpoint
@app.get("/api/system/info")
async def api_system_info():
    """Return system information: version, uptime, memory usage, Python version."""
    import os as _os
    import platform

    try:
        import psutil
        process = psutil.Process(_os.getpid())
        memory = process.memory_info()
        mem_info = {
            "rss_mb": round(memory.rss / 1024 / 1024, 1),
            "vms_mb": round(memory.vms / 1024 / 1024, 1),
            "percent": round(process.memory_percent(), 1),
        }
    except ImportError:
        mem_info = {"note": "psutil not installed, install with: pip install psutil"}

    uptime = time.time() - _app_start_time
    return {
        "version": "1.0.0",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "uptime_seconds": round(uptime, 1),
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "pid": _os.getpid(),
        "memory": mem_info,
        "providers_loaded": len(config_manager.config.providers),
        "providers_enabled": sum(1 for p in config_manager.config.providers.values() if p.enabled),
        "total_keys": sum(len(p.keys) for p in config_manager.config.providers.values()),
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
def clear_remote_models_cache(name: str):
    """Clear cached remote models for a provider."""
    cfg = config_manager.config
    if name in cfg.providers and cfg.providers[name].remote_models_cache:
        new_cfg = cfg.model_copy(deep=True)
        new_cfg.providers[name].remote_models_cache = []
        config_manager.save(new_cfg)


@app.get("/api/providers/{name}/models/remote")
async def api_get_remote_models(name: str):
    """Fetch all available models from a provider's upstream API, with caching."""
    cfg = config_manager.config
    pc = cfg.providers.get(name)
    if not pc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    # 优先返回缓存
    if pc.remote_models_cache:
        return {"object": "list", "data": pc.remote_models_cache}

    if pc.provider_type == "web_reverse":
        models = []
        if pc.web_reverse and pc.web_reverse.model_mapping:
            for client_model, upstream_model in pc.web_reverse.model_mapping.items():
                models.append({
                    "id": client_model,
                    "upstream_id": upstream_model,
                    "provider": name,
                })
        if models:
            new_cfg = cfg.model_copy(deep=True)
            new_cfg.providers[name].remote_models_cache = models
            config_manager.save(new_cfg)
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
                
                # 保存到配置
                new_cfg = cfg.model_copy(deep=True)
                new_cfg.providers[name].remote_models_cache = models
                config_manager.save(new_cfg)
                
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

        pc = cfg.providers[name]
        
        remote_model_ids = []
        if pc.provider_type == "web_reverse" and pc.web_reverse and pc.web_reverse.model_mapping:
            remote_model_ids = list(pc.web_reverse.model_mapping.keys())
        elif pc.remote_models_cache:
            remote_model_ids = [m.get("id") for m in pc.remote_models_cache]
        
        if "include" in body:
            if remote_model_ids:
                valid_include = [m for m in body["include"] if m in remote_model_ids]
                pc.models["include"] = valid_include
            else:
                pc.models["include"] = body["include"]
        if "exclude" in body:
            pc.models["exclude"] = body["exclude"]

        cfg.providers[name].remote_models_cache = []
        
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


# 配置同步
@app.get("/api/sync")
async def api_sync_status():
    """返回当前同步配置和状态。"""
    sc = config_manager.config.sync
    token = sync_storage.gist_token
    return {
        "enabled": sc.enabled,
        "gist_id": sc.gist_id,
        "has_token": bool(token),
        "token_full": token,
    }


@app.post("/api/sync/find-gist")
async def api_sync_find_gist(request: Request):
    """通过 Token 查找 MonoRelay Configuration Gist。"""
    try:
        body = await request.json()
        token = (body.get("gist_token", "") or "").strip()
        # 清理 Token
        token = "".join(token.split())
        if not token:
            raise HTTPException(status_code=400, detail="gist_token 不能为空")

        sync = GistSync(token)
        gist_id = await sync.find_gist_by_description()
        
        # find_gist_by_description 返回 None 可能是因为 401 或者真的没找到
        # 我们需要区分这两种情况
        if gist_id:
            return {"gist_id": gist_id, "found": True}
        
        # 如果没找到，尝试获取一次列表来验证 Token 是否有效
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/gists?per_page=1",
                headers=sync._headers,
                timeout=10.0,
            )
            if resp.status_code == 401:
                return {"gist_id": "", "found": False, "error": "Token 无效 (401)，请检查 Token 是否正确"}
            elif resp.status_code == 403:
                return {"gist_id": "", "found": False, "error": "Token 有效但无 Gist 权限 (403)"}
            else:
                # 200 但没找到，说明确实没有
                return {"gist_id": "", "found": False}
                
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sync/setup")
async def api_sync_setup(request: Request):
    """配置 Gist 同步，支持 Token 和可选的 gist_id。"""
    try:
        body = await request.json()
        token = body.get("gist_token", "")
        gist_id = body.get("gist_id", "").strip()

        if not token:
            raise HTTPException(status_code=400, detail="gist_token 不能为空")

        # 彻底清理 Token：移除所有空白字符（包括换行、空格等）
        token = "".join(token.split())
        
        # 保存 token 到本地存储
        sync_storage.gist_token = token
        
        cfg = config_manager.config.model_copy(deep=True)
        cfg.sync.enabled = True

        from .sync import GistSync
        import logging
        logger = logging.getLogger("monorelay.sync")
        
        sync = GistSync(token, gist_id)
        logger.info(f"同步配置: token_len={len(token)}, gist_id={gist_id or '空'}")

        # 未提供 gist_id 时自动查找已有 Gist
        if not gist_id:
            found_id = await sync.find_gist_by_description()
            if found_id:
                cfg.sync.gist_id = found_id
                sync = GistSync(token, found_id)
                logger.info(f"找到已有 Gist: {found_id}")
            else:
                # 找不到已有 Gist，创建新的
                logger.info("未找到已有 Gist，创建新的...")
                ok = await sync.push("{}")
                if not ok:
                    raise HTTPException(status_code=500, detail="创建 Gist 失败")
                cfg.sync.gist_id = sync.gist_id
                logger.info(f"Gist 创建成功: {sync.gist_id}")

        # 保存配置（含 gist_id）
        config_manager.save(cfg)
        logger.info(f"配置已保存，准备推送完整内容")

        # 同步推送完整内容（不再使用后台任务，避免竞态）
        import yaml
        content = yaml.dump(cfg.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)
        stats_content = None
        if stats_tracker.db_path.exists():
            try:
                stats_content = stats_tracker.db_path.read_text(encoding="utf-8")
            except Exception:
                pass
        
        logger.info(f"开始推送: gist_id={sync.gist_id}, content_len={len(content)}")
        ok, version = await sync.push(content, stats_content)
        
        if not ok:
            logger.error(f"推送失败，但配置已保存。可稍后手动点击'推送'按钮重试")
            return {"status": "ok", "message": "Gist 同步已配置，但推送完整内容失败，请稍后手动推送", "gist_id": sync.gist_id}
        
        sync_storage.last_sync_version = version
        logger.info(f"推送成功: {sync.gist_id}, version: {version}")
        return {"status": "ok", "message": "Gist 同步已配置", "gist_id": sync.gist_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sync/push")
async def api_sync_push():
    """推送当前原始配置和统计到 Gist。"""
    sc = config_manager.config.sync
    import logging
    logger = logging.getLogger("monorelay.sync")
    token = sync_storage.gist_token
    if not sc.enabled or not token:
        raise HTTPException(status_code=400, detail="Gist 同步未配置")

    # 读取原始文本（保留注释）
    content = ""
    if config_manager.config_path.exists():
        content = config_manager.config_path.read_text(encoding="utf-8")
    
    if not content:
        import yaml
        content = yaml.dump(config_manager.config.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)

    # 附带统计数据
    stats_content = None
    stats_path = stats_tracker.db_path
    if stats_path.exists():
        try:
            stats_content = stats_path.read_text(encoding="utf-8")
        except Exception:
            pass

    sync = GistSync(token, sc.gist_id)
    ok, version = await sync.push(content, stats_content)
    
    if ok:
        sync_storage.last_sync_version = version
        if sync.gist_id and sync.gist_id != sc.gist_id:
            cfg = config_manager.config.model_copy(deep=True)
            cfg.sync.gist_id = sync.gist_id
            config_manager.save(cfg)
        return {"status": "ok", "message": "原始配置和统计已推送到 Gist", "gist_id": sync.gist_id, "version": version}
    raise HTTPException(status_code=500, detail="推送到 Gist 失败")


@app.post("/api/sync/pull")
async def api_sync_pull(request: Request):
    """从 Gist 拉取原始文本并应用，支持版本对比。"""
    sc = config_manager.config.sync
    body = await request.json()
    token = body.get("gist_token", "").strip() or sync_storage.gist_token
    force = body.get("force", False)  # 支持强制拉取

    if not token:
        raise HTTPException(status_code=400, detail="未配置 Gist Token")
    if not sc.gist_id:
        raise HTTPException(status_code=400, detail="未配置 Gist ID")

    sync_storage.gist_token = token
    sync = GistSync(token, sc.gist_id)
    data = await sync.pull()
    if not data:
        raise HTTPException(status_code=500, detail="从 Gist 拉取失败")

    new_version = data.get("version", "")
    last_version = sync_storage.last_sync_version
    
    # 如果版本一致且未强制拉取，直接返回
    if new_version == last_version and not force and last_version != "":
        return {"status": "ok", "message": "本地已是 Gist 的最新版本", "changes": False, "version": new_version}

    results = []
    changes_made = False
    try:
        if "config" in data:
            current_content = ""
            if config_manager.config_path.exists():
                current_content = config_manager.config_path.read_text(encoding="utf-8")
            
            new_content = data["config"]
            if force or current_content.replace("\r\n", "\n").strip() != new_content.replace("\r\n", "\n").strip():
                config_manager.config_path.write_text(new_content, encoding="utf-8")
                config_manager.reload()
                init_components(config_manager.config)
                results.append("配置")
                changes_made = True

        if "stats" in data:
            stats_path = stats_tracker.db_path
            current_stats = ""
            if stats_path.exists():
                current_stats = stats_path.read_text(encoding="utf-8")
            
            new_stats = data["stats"]
            if force or current_stats.strip() != new_stats.strip():
                stats_path.parent.mkdir(parents=True, exist_ok=True)
                stats_path.write_text(new_stats, encoding="utf-8")
                stats_tracker._load()
                results.append("统计数据")
                changes_made = True

        if changes_made:
            sync_storage.last_sync_version = new_version
            msg = f"已从 Gist 拉取：{ '、'.join(results) }"
            return {"status": "ok", "message": msg, "changes": True, "version": new_version}
        
        # 即使 changes_made 为 False (因为内容刚好一致)，也更新本地版本号
        sync_storage.last_sync_version = new_version
        return {"status": "ok", "message": "Gist 内容与本地完全一致，版本号已同步。", "changes": False, "version": new_version}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用拉取的数据失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用拉取的数据失败: {e}")


@app.get("/api/sync/gist-info")
async def api_sync_gist_info(request: Request):
    """获取 Gist 元数据。"""
    sc = config_manager.config.sync
    token = sync_storage.gist_token
    if not token or not sc.gist_id:
        return {"status": "error", "message": "Not configured"}
    
    from .sync import GistSync
    sync = GistSync(token, sc.gist_id)
    info = await sync.get_info()
    if info:
        return {"status": "ok", "info": info}
    return {"status": "error", "message": "Failed to fetch gist info"}


@app.post("/api/sync/verify-token")
async def api_sync_verify_token(request: Request):
    """验证 GitHub Token 是否有效及权限。"""
    try:
        body = await request.json()
        token = body.get("gist_token", "").strip()
        
        # 如果请求体中没有 Token，则使用已配置的 Token
        if not token:
            token = sync_storage.gist_token
            
        if not token:
            return {"valid": False, "error": "未提供 Token 且未配置 Token"}

        # 清理 Token
        token = "".join(token.split())
        
        from .sync import GistSync
        sync = GistSync(token)
        
        # 先尝试查找配置 Gist
        gist_id = await sync.find_gist_by_description()
        
        if gist_id:
            return {"valid": True, "gist_access": True, "message": f"Token 有效，找到配置 Gist: {gist_id}"}
        
        # 没找到，验证 Token 本身是否有效
        import httpx
        import logging
        logger = logging.getLogger("monorelay.sync")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/gists?per_page=1",
                headers=sync._headers,
                timeout=10.0,
            )
            
            if resp.status_code == 401:
                logger.warning(f"Token 验证失败 (401): {resp.text[:200]}")
                return {"valid": False, "error": f"Token 无效 (401)。请检查：\n1. Token 是否完整复制（无多余空格/换行）\n2. 是否已过期或被撤销\n3. 权限是否包含 Gist Read/Write"}
            elif resp.status_code == 403:
                return {"valid": True, "gist_access": False, "error": "Token 有效但无 Gist 访问权限 (403)，请确保勾选 Gist → Read and write"}
            elif resp.status_code == 200:
                return {"valid": True, "gist_access": True, "message": "Token 有效，但未找到配置 Gist（首次配置时会自动创建）"}
            else:
                return {"valid": False, "error": f"验证失败 ({resp.status_code}): {resp.text[:200]}"}
    except HTTPException:
        raise
    except Exception as e:
        return {"valid": False, "error": f"验证失败: {str(e)}"}


@app.get("/api/sync/history")
async def api_sync_history():
    """获取 Gist 提交历史。"""
    sc = config_manager.config.sync
    token = sync_storage.gist_token
    if not sc.enabled or not token or not sc.gist_id:
        return []

    sync = GistSync(token, sc.gist_id)
    return await sync.get_history()


# WebDAV backup endpoints - inspired by all-api-hub WebDAV backup
@app.post("/api/backup/webdav/test")
async def api_webdav_test(request: Request):
    """Test WebDAV connection."""
    body = await request.json()
    url = body.get("url", "")
    username = body.get("username", "")
    password = body.get("password", "")
    if not url:
        raise HTTPException(status_code=400, detail="WebDAV URL is required")

    wd = WebDAVSync(url, username, password)
    return await wd.test_connection()


@app.post("/api/backup/webdav/push")
async def api_webdav_push(request: Request):
    """Push config and stats to WebDAV."""
    body = await request.json()
    url = body.get("url", "")
    username = body.get("username", "")
    password = body.get("password", "")
    path = body.get("path", "monorelay")

    if not url:
        raise HTTPException(status_code=400, detail="WebDAV URL is required")

    wd = WebDAVSync(url, username, password)
    config_path = config_manager.config_path
    results = []
    try:
        content = config_path.read_text(encoding="utf-8") if config_path and config_path.exists() else ""
        if content:
            ok = await wd.push(f"{path}/config.yml", content)
            results.append({"file": f"{path}/config.yml", "ok": ok})
        stats_path = stats_tracker.db_path
        if stats_path.exists():
            content = stats_path.read_text(encoding="utf-8")
            ok = await wd.push(f"{path}/stats.json", content)
            results.append({"file": f"{path}/stats.json", "ok": ok})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WebDAV push failed: {e}")

    return {"status": "ok", "results": results}


@app.post("/api/backup/webdav/pull")
async def api_webdav_pull(request: Request):
    """Pull config and stats from WebDAV."""
    body = await request.json()
    url = body.get("url", "")
    username = body.get("username", "")
    password = body.get("password", "")
    path = body.get("path", "monorelay")

    if not url:
        raise HTTPException(status_code=400, detail="WebDAV URL is required")

    wd = WebDAVSync(url, username, password)
    results = {}
    try:
        config_content = await wd.pull(f"{path}/config.yml")
        if config_content:
            import yaml
            raw = yaml.safe_load(config_content)
            new_cfg = AppConfig(**raw)
            config_manager.save(new_cfg)
            init_components(new_cfg)
            results["config"] = {"ok": True, "applied": True}

        stats_content = await wd.pull(f"{path}/stats.json")
        if stats_content:
            stats_path = stats_tracker.db_path
            stats_path.parent.mkdir(parents=True, exist_ok=True)
            stats_path.write_text(stats_content, encoding="utf-8")
            stats_tracker._load()
            results["stats"] = {"ok": True, "applied": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WebDAV pull failed: {e}")

    return {"status": "ok", "results": results}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("v1/") or full_path.startswith("api/") or full_path == "health":
        raise HTTPException(status_code=404)
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404)


def run():
    import argparse
    parser = argparse.ArgumentParser(description="MonoRelay - LLM API Relay Server")
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
    logger.info(f"Starting MonoRelay on {host}:{port}")

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
