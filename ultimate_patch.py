import sys
import re

# --- openai_format.py ---
with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
    content = f.read()

# 1. Add _extract_preview and Fix main.py imports
# (Already done in previous steps, but let's be sure)

# 2. Update signatures and calls in handle_chat_completions
content = content.replace('def _stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker,',
                        'def _stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None,')
content = content.replace('def _non_stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker,',
                        'def _non_stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None,')

# Update handle_chat_completions to capture original_body and pass it
content = re.sub(r'async def handle_chat_completions\(.*?\):', 
                 'async def handle_chat_completions(body: dict, config: AppConfig, key_manager: KeyManager, router: ModelRouter, request_logger: RequestLogger, stats_tracker: StatsTracker) -> StreamingResponse | dict:\n    original_body = body.copy()', 
                 content)

content = content.replace('return StreamingResponse(\n                _stream_chat(\n                    provider_cfg, url, headers, body, key, key_manager, provider_name,\n                    resolved_model, original_model, request_logger, start_time, stats_tracker,',
                        'return StreamingResponse(\n                _stream_chat(\n                    provider_cfg, url, headers, body, key, key_manager, provider_name,\n                    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,')

content = content.replace('return await _non_stream_chat(\n            provider_cfg, url, headers, body, key, key_manager, provider_name,\n            resolved_model, original_model, request_logger, start_time, stats_tracker,',
                        'return await _non_stream_chat(\n            provider_cfg, url, headers, body, key, key_manager, provider_name,\n            resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,')

# Update log_request calls in _stream_chat and _non_stream_chat
content = content.replace('request_full=json.dumps(body, ensure_ascii=False) if body else None,',
                        'request_full=json.dumps(original_body if original_body else body, ensure_ascii=False, indent=2),')

# Prettify response_full
content = content.replace('response_full=json.dumps(result, ensure_ascii=False) if result else None,',
                        'response_full=json.dumps(result, ensure_ascii=False, indent=2) if result else None,')
content = content.replace('response_full=response_full_str,',
                        'response_full=response_full_str,') # response_full_str is already prettified in previous patch

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
    f.write(content)

print("Ultimate patch applied.")
