import sys
import re

# 1. Patch openai_format.py
with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
    content = f.read()

preview_code = '''
def _extract_preview(content: str = "", reasoning: str = "") -> str:
    """Extract content and thinking into a unified preview string."""
    thinking = reasoning.strip() if reasoning else ""
    main_content = content.strip() if content else ""
    if not thinking and "<thought>" in main_content:
        import re
        match = re.search(r'<thought>(.*?)</thought>', main_content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            main_content = main_content.replace(match.group(0), "").strip()
    parts = []
    if thinking: parts.append(f"[Thinking]\\n{thinking}")
    if main_content: parts.append(main_content)
    return "\\n\\n---\\n\\n".join(parts) if parts else ""
'''
content = content.replace('logger = logging.getLogger("monorelay.openai_proxy")', 'logger = logging.getLogger("monorelay.openai_proxy")\n' + preview_code)

old_stream_vars = '''            output_content = []
            response_preview = None'''
new_stream_vars = '''            output_content = []
            output_thinking = []
            response_preview = None'''
content = content.replace(old_stream_vars, new_stream_vars)

old_stream_parse = '''                                            if content:
                                                output_content.append(content)'''
new_stream_parse = '''                                            if content:
                                                output_content.append(content)
                                            reasoning = delta.get("reasoning_content", "")
                                            if reasoning:
                                                output_thinking.append(reasoning)'''
content = content.replace(old_stream_parse, new_stream_parse)

old_stream_log = '''            full_output = "".join(output_content)
            if full_output:
                response_preview = full_output[:500] if len(full_output) > 500 else full_output'''
new_stream_log = '''            full_output = "".join(output_content)
            full_thinking = "".join(output_thinking)
            response_preview = _extract_preview(full_output, full_thinking)
            if len(response_preview) > 1000:
                response_preview = response_preview[:1000] + "..."
            response_full_obj = {"content": full_output}
            if full_thinking:
                response_full_obj["reasoning_content"] = full_thinking
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False)'''
content = content.replace(old_stream_log, new_stream_log)

old_stream_log_call = '''                response_full=full_output if full_output else None,'''
new_stream_log_call = '''                response_full=response_full_str,'''
content = content.replace(old_stream_log_call, new_stream_log_call)

old_non_stream_log = '''                result = resp.json()
                tokens_in, tokens_out = extract_token_usage(result)'''
new_non_stream_log = '''                result = resp.json()
                tokens_in, tokens_out = extract_token_usage(result)
                resp_preview = ""
                if "choices" in result and len(result["choices"]) > 0:
                    msg = result["choices"][0].get("message", {})
                    resp_preview = _extract_preview(msg.get("content", ""), msg.get("reasoning_content", ""))
                    if len(resp_preview) > 1000:
                        resp_preview = resp_preview[:1000] + "..."
                response_preview = resp_preview if resp_preview else None'''
content = content.replace(old_non_stream_log, new_non_stream_log)

old_non_stream_log_call = '''                    response_preview=json.dumps(result) if result else None,'''
new_non_stream_log_call = '''                    response_preview=response_preview,'''
content = content.replace(old_non_stream_log_call, new_non_stream_log_call)

stub_pattern = r'async def handle_image_variations\(.*'
match = re.search(stub_pattern, content, re.DOTALL)
if match:
    content = content[:match.start()]

generic_handlers = '''
# --- Generic Handlers & Missing Endpoints ---
async def _handle_generic_get(path: str, config: AppConfig, key_manager: KeyManager, request_logger: RequestLogger, stats_tracker: StatsTracker, params: dict = None) -> dict:
    provider_name = next((n for n, p in config.providers.items() if p.enabled), "openrouter")
    provider_cfg = config.providers.get(provider_name)
    key = key_manager.select_key(provider_name, config.key_selection.strategy)
    if not key: return {"error": {"message": "No available keys", "type": "no_keys"}}
    headers = _build_headers(provider_cfg, key.key.key)
    url = _build_url(provider_cfg.base_url, path)
    start_time = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            elapsed = time.time() - start_time
            try: 
                result = resp.json()
            except Exception: 
                result = {"error": {"message": resp.text, "type": "upstream_error"}}
            await request_logger.log_request(
                model=path, provider=provider_name, key_label=key.key.label,
                status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2),
                request_full=json.dumps(params, ensure_ascii=False) if params else None,
                response_full=json.dumps(result, ensure_ascii=False) if result else None
            )
            return result
        except Exception as e:
            return {"error": {"message": str(e), "type": "proxy_error"}}

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
            try: result = resp.json()
            except Exception: result = {"error": {"message": resp.text, "type": "upstream_error"}}
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            else:
                key_manager.report_success(key, 0)
            await request_logger.log_request(
                model=resolved_model, provider=provider_name, key_label=key.key.label,
                status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2),
                request_full=json.dumps(body, ensure_ascii=False) if body else None,
                response_full=json.dumps(result, ensure_ascii=False) if result else None
            )
            stats_tracker.record_request(provider_name, resolved_model, success=(resp.status_code < 400))
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": f"[{provider_name}] {str(e)}", "type": "proxy_error"}}

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
            try: result = resp.json()
            except Exception: result = {"error": {"message": resp.text, "type": "upstream_error"}}
            if resp.status_code >= 400:
                key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            else:
                key_manager.report_success(key, 0)
            await request_logger.log_request(
                model=resolved_model, provider=provider_name, key_label=key.key.label,
                status_code=resp.status_code, latency_ms=round(elapsed * 1000, 2),
                request_full=json.dumps(body, ensure_ascii=False) if body else None,
                response_full=json.dumps(result, ensure_ascii=False) if result else None
            )
            stats_tracker.record_request(provider_name, resolved_model, success=(resp.status_code < 400))
            return result
        except Exception as e:
            key_manager.report_failure(provider_name, key, provider_cfg.rate_limit_cooldown)
            return {"error": {"message": f"[{provider_name}] {str(e)}", "type": "proxy_error"}}

async def handle_image_variations(body, file, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/images/variations", body, {"file": file}, config, key_manager, router, request_logger, stats_tracker)

async def handle_image_edits(body, image, mask, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_multipart("/images/edits", body, {"image": image, "mask": mask}, config, key_manager, router, request_logger, stats_tracker)

async def handle_moderations(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/moderations", body, config, key_manager, router, request_logger, stats_tracker)

async def handle_responses(body, config, key_manager, router, request_logger, stats_tracker):
    return await _handle_generic_post("/responses", body, config, key_manager, router, request_logger, stats_tracker)

from ..usage_tracker import usage_tracker
from ..auth_utils import verify_token

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
    return {"object": "credit_summary", "total_granted": 999999.0, "total_used": cost, "total_available": max(0, 999999.0 - cost), "usage": stats}

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
'''
content = content + generic_handlers

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
    f.write(content)

# 2. Patch anthropic_format.py
with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'r') as f:
    content = f.read()

content = content.replace('logger = logging.getLogger("monorelay.anthropic_proxy")', 'logger = logging.getLogger("monorelay.anthropic_proxy")\n' + preview_code)

old_anto = '''    for part in anthropic_resp.get("content", []):
        if part.get("type") == "text":
            content_text += part.get("text", "")
    
    choices.append({'''
new_anto = '''    reasoning_text = ""
    for part in anthropic_resp.get("content", []):
        if part.get("type") == "text":
            content_text += part.get("text", "")
        elif part.get("type") == "thinking":
            reasoning_text += part.get("thinking", "")
    
    choices.append({'''
content = content.replace(old_anto, new_anto)

old_anto2 = '''        "message": {
            "role": "assistant",
            "content": content_text,
        },'''
new_anto2 = '''        "message": {
            "role": "assistant",
            "content": content_text,
            "reasoning_content": reasoning_text,
        },'''
content = content.replace(old_anto2, new_anto2)

old_s_anto = '''                    if delta.get("type") == "text":
                        text = delta.get("text", "")
                        openai_chunk = {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": text},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(openai_chunk)}\\n\\n".encode()'''
new_s_anto = '''                    if delta.get("type") == "text":
                        text = delta.get("text", "")
                        openai_chunk = {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(openai_chunk)}\\n\\n".encode()
                    elif delta.get("type") == "thinking_delta":
                        thinking = delta.get("thinking", "")
                        openai_chunk = {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"reasoning_content": thinking}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(openai_chunk)}\\n\\n".encode()'''
content = content.replace(old_s_anto, new_s_anto)

old_sm = '''            tokens_in = None
            tokens_out = None
            stream_chunks = 0
            buffer = b""

            async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:'''
new_sm = '''            tokens_in = None
            tokens_out = None
            stream_chunks = 0
            buffer = b""
            output_content = []
            output_thinking = []

            async with httpx.AsyncClient(timeout=httpx.Timeout(provider_cfg.timeout, connect=10.0)) as client:'''
content = content.replace(old_sm, new_sm)

old_sm2 = '''                                        if data.get("type") == "message_stop":'''
new_sm2 = '''                                        if data.get("type") == "content_block_delta":
                                            d = data.get("delta", {})
                                            if d.get("type") == "text_delta": output_content.append(d.get("text", ""))
                                            elif d.get("type") == "thinking_delta": output_thinking.append(d.get("thinking", ""))
                                        elif data.get("type") == "message_stop":'''
content = content.replace(old_sm2, new_sm2)

old_sm3 = '''            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                request_full=json.dumps(body, ensure_ascii=False) if body else None,
            )'''
new_sm3 = '''            full_content = "".join(output_content)
            full_thinking = "".join(output_thinking)
            resp_preview = _extract_preview(full_content, full_thinking)
            if len(resp_preview) > 1000: resp_preview = resp_preview[:1000] + "..."
            
            response_full_obj = {"content": full_content}
            if full_thinking: response_full_obj["reasoning_content"] = full_thinking
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False)

            await request_logger.log_request(
                model=resolved_model,
                provider=provider_name,
                key_label=key.key.label,
                status_code=200,
                latency_ms=round(elapsed * 1000, 2),
                streaming=True,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                response_preview=resp_preview,
                request_full=json.dumps(body, ensure_ascii=False) if body else None,
                response_full=response_full_str,
            )'''
content = content.replace(old_sm3, new_sm3)

old_nsm = '''                result = resp.json()
                tokens_in, tokens_out = extract_anthropic_token_usage(result)'''
new_nsm = '''                result = resp.json()
                tokens_in, tokens_out = extract_anthropic_token_usage(result)
                content_text, thinking_text = "", ""
                for p in result.get("content", []):
                    if p.get("type") == "text": content_text += p.get("text", "")
                    elif p.get("type") == "thinking": thinking_text += p.get("thinking", "")
                resp_preview = _extract_preview(content_text, thinking_text)
                if len(resp_preview) > 1000: resp_preview = resp_preview[:1000] + "..."'''
content = content.replace(old_nsm, new_nsm)

old_nsm_call = '''                request_full=json.dumps(body, ensure_ascii=False) if body else None,
                response_full=json.dumps(result, ensure_ascii=False) if result else None,'''
new_nsm_call = '''                request_full=json.dumps(body, ensure_ascii=False) if body else None,
                response_full=json.dumps(result, ensure_ascii=False) if result else None,
                response_preview=resp_preview,'''
content = content.replace(old_nsm_call, new_nsm_call)

with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'w') as f:
    f.write(content)

print("Patch applied successfully.")
