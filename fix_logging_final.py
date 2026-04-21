import sys
import re

file_path = '/root/ociTurner/MonoRelay/backend/proxy/openai_format.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Update function signatures to make original_body mandatory for core proxy functions
# And keep it optional for generic helpers but passed correctly
sigs = [
    ('_stream_chat', 'original_body'),
    ('_non_stream_chat', 'original_body'),
    ('_stream_completion', 'original_body'),
    ('_non_stream_completion', 'original_body'),
]

for func, param in sigs:
    # Remove the =None default value
    content = content.replace(f'def {func}(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body=None,',
                             f'def {func}(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body,')

# 2. Fix the "original_body if 'original_body' in locals() else body" logic to just "original_body"
# since we are making it mandatory in those scopes.
content = content.replace("original_body if 'original_body' in locals() else body", "original_body")

# 3. Ensure handle_completions and handle_embeddings also capture and pass original_body
content = content.replace('async def handle_completions(body, config, key_manager, router, request_logger, stats_tracker):',
                        'async def handle_completions(body, config, key_manager, router, request_logger, stats_tracker):\n    original_body = body.copy()')
content = content.replace('async def handle_embeddings(body, config, key_manager, router, request_logger, stats_tracker):',
                        'async def handle_embeddings(body, config, key_manager, router, request_logger, stats_tracker):\n    original_body = body.copy()')

# 4. Update calls to pass original_body
# Embeddings call
content = content.replace('return await _handle_generic_post("/embeddings", body, config, key_manager, router, request_logger, stats_tracker)',
                        'return await _handle_generic_post("/embeddings", body, config, key_manager, router, request_logger, stats_tracker, original_body=original_body)')
# Completions call
content = content.replace('return await _non_stream_completion(\n                provider_cfg, url, headers, request_body, key, key_manager, provider_name,\n                model, original_model, request_logger, start_time, stats_tracker,\n            )',
                        'return await _non_stream_completion(\n                provider_cfg, url, headers, request_body, key, key_manager, provider_name,\n                model, original_model, request_logger, start_time, stats_tracker, original_body=original_body,\n            )')

# 5. Fix _handle_generic_post to accept and use original_body
content = content.replace('async def _handle_generic_post(path: str, body: dict, config: AppConfig, key_manager: KeyManager, router: Optional[ModelRouter], request_logger: RequestLogger, stats_tracker: StatsTracker, method: str = "POST") -> dict:',
                        'async def _handle_generic_post(path: str, body: dict, config: AppConfig, key_manager: KeyManager, router: Optional[ModelRouter], request_logger: RequestLogger, stats_tracker: StatsTracker, method: str = "POST", original_body: dict = None) -> dict:')
content = content.replace('request_full=json.dumps(body, ensure_ascii=False, indent=2),',
                        'request_full=json.dumps(original_body if original_body else body, ensure_ascii=False, indent=2),')

# 6. Final cleanup of any duplicate original_body assignments in calls
content = content.replace('original_body=original_body=original_body', 'original_body=original_body')

with open(file_path, 'w') as f:
    f.write(content)

print("Final logging fix applied.")
