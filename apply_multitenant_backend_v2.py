import sys
import re

def patch_main():
    with open('/root/ociTurner/MonoRelay/backend/main.py', 'r') as f:
        content = f.read()

    # 1. Replace auth_middleware
    old_middleware = re.search(r'@app.middleware\("http"\)\nasync def auth_middleware.*?return JSONResponse\(status_code=401, content=\{"detail": "Invalid Authorization header"\}\)', content, re.DOTALL)
    new_middleware = """@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path in ["/", "/api/auth/login", "/api/auth/register", "/api/info", "/api/auth/has_users"] or path.startswith(("/static", "/assets", "/api/sso")):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return JSONResponse(status_code=401, content={"detail": "Missing Authorization header"})

    token = auth_header.replace("Bearer ", "")
    
    if config_manager.config.server.access_key_enabled and token == config_manager.config.server.access_key:
        request.state.user_id = 0
        request.state.is_admin = True
        return await call_next(request)

    if token.startswith("sk-prisma-"):
        api_key = await user_manager.get_api_key_by_token(token)
        if api_key and api_key.enabled:
            request.state.user_id = api_key.user_id
            request.state.is_admin = False
            return await call_next(request)

    u_id = verify_token(token, config_secret=config_manager.config.server.jwt_secret)
    if u_id:
        user = await user_manager.get_user_by_id(u_id)
        if user:
            request.state.user_id = user.id
            request.state.is_admin = user.role == "admin"
            return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Invalid token"})"""
    if old_middleware:
        content = content[:old_middleware.start()] + new_middleware + content[old_middleware.end():]

    # 2. Add endpoints at the end
    endpoints = """

# --- Multi-tenant API Endpoints ---
@app.get("/api/user/keys")
async def api_user_keys(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None: raise HTTPException(status_code=401)
    keys = await user_manager.get_user_api_keys(user_id)
    return api_response(data=keys)

@app.post("/api/user/keys")
async def api_user_key_create(request: Request, body: dict):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None: raise HTTPException(status_code=401)
    label = body.get("label", "default")
    key = await user_manager.create_api_key(user_id, label)
    return api_response(data=key)

@app.get("/api/user/stats")
async def api_user_stats(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None: raise HTTPException(status_code=401)
    user = await user_manager.get_user_by_id(user_id)
    from .usage_tracker import usage_tracker
    stats = usage_tracker.get_stats(str(user_id))
    return api_response(data={
        "balance": user.balance,
        "quota_used": user.balance - stats.get("cost", 0),
        "total_requests": stats.get("total_requests", 0),
        "total_cost": stats.get("cost", 0),
        "requests_by_model": stats.get("requests_by_model", {})
    })

@app.get("/api/user/logs")
async def api_user_logs(request: Request, limit: int = 50):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None: raise HTTPException(status_code=401)
    logs = await request_logger.get_recent_requests(limit, user_id=user_id)
    return api_response(data=logs)

@app.get("/api/admin/users")
async def api_admin_users(request: Request):
    if not getattr(request.state, "is_admin", False): raise HTTPException(status_code=403)
    cursor = await user_manager._db.execute("SELECT id, username, email, role, balance, created_at FROM users")
    rows = await cursor.fetchall()
    return api_response(data=[dict(r) for r in rows])

@app.post("/api/admin/users/{user_id}/balance")
async def api_admin_user_balance(user_id: int, body: dict, request: Request):
    if not getattr(request.state, "is_admin", False): raise HTTPException(status_code=403)
    adjustment = body.get("adjustment", 0.0)
    await user_manager._db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (adjustment, user_id))
    await user_manager._db.commit()
    return api_response(message="余额已更新")

@app.delete("/api/admin/users/{user_id}")
async def api_admin_user_delete(user_id: int, request: Request):
    if not getattr(request.state, "is_admin", False): raise HTTPException(status_code=403)
    if user_id == 0: raise HTTPException(status_code=400, detail="Cannot delete system admin")
    await user_manager._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await user_manager._db.commit()
    return api_response(message="用户已删除")

@app.get("/api/admin/redemption-codes")
async def api_admin_codes(request: Request):
    if not getattr(request.state, "is_admin", False): raise HTTPException(status_code=403)
    cursor = await user_manager._db.execute("SELECT * FROM redemption_codes ORDER BY id DESC")
    rows = await cursor.fetchall()
    return api_response(data=[dict(r) for r in rows])

@app.post("/api/admin/redemption-codes")
async def api_admin_codes_create(request: Request, body: dict):
    if not getattr(request.state, "is_admin", False): raise HTTPException(status_code=403)
    amount = body.get("amount", 0.0)
    count = body.get("count", 1)
    prefix = body.get("prefix", "PRISMA-")
    codes = await user_manager.generate_codes(amount, count, prefix)
    return api_response(data=codes)

@app.post("/api/user/redeem")
async def api_user_redeem(request: Request, body: dict):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None: raise HTTPException(status_code=401)
    code = body.get("code", "").strip()
    if not code: raise HTTPException(status_code=400, detail="Missing code")
    amount = await user_manager.redeem_code(user_id, code)
    if amount is None:
        raise HTTPException(status_code=400, detail="Invalid or already used redemption code")
    return api_response(message=f"成功兑换 ${amount:.2f}", data={"amount": amount})
"""
    if "api_admin_users" not in content:
        content += endpoints

    # 3. Add user_id to handle_chat_completions call
    content = content.replace(
'''    result = await handle_chat_completions(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker,
    )''',
'''    result = await handle_chat_completions(
        body, config_manager.config, key_manager, model_router, request_logger, stats_tracker, user_id=getattr(request.state, "user_id", None)
    )'''
    )

    with open('/root/ociTurner/MonoRelay/backend/main.py', 'w') as f:
        f.write(content)

def patch_openai():
    with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
        content = f.read()

    # 1. Add user_id to handle_chat_completions signature
    content = content.replace(
'''async def handle_chat_completions(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
) -> StreamingResponse | dict:''',
'''async def handle_chat_completions(
    body: dict,
    config: AppConfig,
    key_manager: KeyManager,
    router: ModelRouter,
    request_logger: RequestLogger,
    stats_tracker: StatsTracker,
    user_id: int = None,
) -> StreamingResponse | dict:'''
    )

    # 2. Add user_id to stream functions
    content = content.replace(
'''def _stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None,
) -> AsyncGenerator[bytes, None]:''',
'''def _stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None, user_id=None,
) -> AsyncGenerator[bytes, None]:'''
    )

    content = content.replace(
'''def _non_stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None,
) -> dict:''',
'''def _non_stream_chat(
    provider_cfg, url, headers, body, key, key_manager, provider_name,
    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None, user_id=None,
) -> dict:'''
    )

    # 3. Add user_id to calls inside handle_chat_completions
    content = content.replace(
'''            _stream_chat(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,
            ),''',
'''            _stream_chat(
                provider_cfg, url, headers, body, key, key_manager, provider_name,
                resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body, user_id=user_id,
            ),'''
    )

    content = content.replace(
'''        return await _non_stream_chat(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,
        )''',
'''        return await _non_stream_chat(
            provider_cfg, url, headers, body, key, key_manager, provider_name,
            resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body, user_id=user_id,
        )'''
    )

    # Cascade calls inside _handle_cascade_chat (if any) or handle_chat_completions
    content = content.replace(
'''                _stream_chat(
                    provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                    model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,
                ),''',
'''                _stream_chat(
                    provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                    model, original_model, request_logger, start_time, stats_tracker, original_body=original_body, user_id=user_id,
                ),'''
    )
    content = content.replace(
'''                return await _non_stream_chat(
                    provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                    model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,
                )''',
'''                return await _non_stream_chat(
                    provider_cfg, url, headers, request_body, key, key_manager, provider_name,
                    model, original_model, request_logger, start_time, stats_tracker, original_body=original_body, user_id=user_id,
                )'''
    )

    # 4. Add billing helpers
    helpers = '''
async def _check_user_balance(user_id: int, config: AppConfig) -> bool:
    if not config.billing.enabled or user_id == 0 or user_id is None: return True
    from ..main import user_manager
    user = await user_manager.get_user_by_id(user_id)
    if not user: return False
    if config.billing.enforce_balance and user.balance <= 0: return False
    return True

def _calculate_credits(provider_cfg, model: str, input_tokens: int, output_tokens: int) -> float:
    rate = provider_cfg.model_rates.get(model)
    rate_in = rate.input if rate else provider_cfg.cost_per_m_input
    rate_out = rate.output if rate else provider_cfg.cost_per_m_output
    return (input_tokens * rate_in + output_tokens * rate_out) / 1000000
'''
    if 'def _calculate_credits' not in content:
        content = content.replace('def _extract_preview', helpers + '\ndef _extract_preview')

    # 5. Add balance check in handle_chat_completions
    content = content.replace('original_body = body.copy()', 'original_body = body.copy()\n    if not await _check_user_balance(user_id, config): return {"error": {"message": "Insufficient balance", "type": "insufficient_balance"}}')

    # 6. Add billing deduction in success logs
    stream_success = '''            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)

            await request_logger.log_request('''
    stream_success_new = '''            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)

            if config.billing.enabled and user_id and user_id != 0:
                cost = _calculate_credits(provider_cfg, resolved_model, tokens_in or 0, tokens_out or 0)
                from ..main import user_manager
                await user_manager.update_balance(user_id, -cost)

            await request_logger.log_request('''
    content = content.replace(stream_success, stream_success_new)

    non_stream_success = '''                response_preview = resp_preview if resp_preview else None

                await request_logger.log_request('''
    non_stream_success_new = '''                response_preview = resp_preview if resp_preview else None

                if config.billing.enabled and user_id and user_id != 0:
                    cost = _calculate_credits(provider_cfg, resolved_model, tokens_in or 0, tokens_out or 0)
                    from ..main import user_manager
                    await user_manager.update_balance(user_id, -cost)

                await request_logger.log_request('''
    content = content.replace(non_stream_success, non_stream_success_new)

    # 7. Add user_id=user_id to ALL log_request calls in stream_chat and non_stream_chat
    content = re.sub(r'await request_logger\.log_request\(\s*model=', 'await request_logger.log_request(\n                user_id=user_id, model=', content)

    with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
        f.write(content)

patch_main()
patch_openai()
print("Pristine patching complete.")
