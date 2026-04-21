import sys
import re

file_path = '/root/ociTurner/MonoRelay/backend/main.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Update Middleware to support User API Keys
old_middleware = """@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path in [
        "/",
        "/api/auth/login",
        "/api/auth/register",
        "/api/info",
        "/api/stats",
        "/api/stats/enhanced",
        "/api/models/pricing",
        "/api/auth/has_users",
        "/api/sso/github/login",
        "/api/sso/github/callback",
        "/api/sso/google/login",
        "/api/sso/google/callback",
        "/api/sso/prismaauth/login",
        "/api/sso/prismaauth/callback",
    ] or path.startswith("/static") or path.startswith("/assets"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return JSONResponse(status_code=401, content={"detail": "Missing Authorization header"})

    token = auth_header.replace("Bearer ", "")
    
    # 1. Global Access Key Check
    if config_manager.config.server.access_key_enabled and token == config_manager.config.server.access_key:
        return await call_next(request)

    # 2. JWT Check
    user_id = verify_token(token, config_secret=config_manager.config.server.jwt_secret)
    if user_id:
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Invalid Authorization header"})"""

new_middleware = """@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    # Public endpoints
    if path in ["/", "/api/auth/login", "/api/auth/register", "/api/info", "/api/auth/has_users"] or path.startswith(("/static", "/assets", "/api/sso")):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return JSONResponse(status_code=401, content={"detail": "Missing Authorization header"})

    token = auth_header.replace("Bearer ", "")
    
    # 1. Global Admin Key Check
    if config_manager.config.server.access_key_enabled and token == config_manager.config.server.access_key:
        request.state.user_id = 0  # 0 represents system admin
        request.state.is_admin = True
        return await call_next(request)

    # 2. User API Key Check (sk-prisma-...)
    if token.startswith("sk-prisma-"):
        api_key = await user_manager.get_api_key_by_token(token)
        if api_key and api_key.enabled:
            request.state.user_id = api_key.user_id
            request.state.is_admin = False
            return await call_next(request)

    # 3. JWT Check (for Dashboard/Console)
    u_id = verify_token(token, config_secret=config_manager.config.server.jwt_secret)
    if u_id:
        user = await user_manager.get_user_by_id(u_id)
        if user:
            request.state.user_id = user.id
            request.state.is_admin = user.role == "admin"
            return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Invalid token"})"""

content = content.replace(old_middleware, new_middleware)

# 2. Update /v1 calls to pass user_id from request.state
content = re.sub(r'result = await handle_(\w+)\(\s*(.*?),\s*request_logger, stats_tracker\s*\)',
                 r'result = await handle_\1(\2, request_logger, stats_tracker, user_id=getattr(request.state, "user_id", None))',
                 content)

# Special cases with upload files
content = content.replace('result = await handle_audio_transcriptions(\n        form_data, file,',
                        'result = await handle_audio_transcriptions(\n        form_data, file, config_manager.config, key_manager, model_router, request_logger, stats_tracker, user_id=getattr(request.state, "user_id", None)')

with open(file_path, 'w') as f:
    f.write(content)
