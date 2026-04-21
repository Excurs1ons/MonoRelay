import sys
import re

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
    content = f.read()

# Capture original_body at the very start of handle_chat_completions
content = re.sub(r'async def handle_chat_completions\(.*?\):', 
                 'async def handle_chat_completions(body: dict, config: AppConfig, key_manager: KeyManager, router: ModelRouter, request_logger: RequestLogger, stats_tracker: StatsTracker) -> StreamingResponse | dict:\n    original_body = body.copy()', 
                 content)

# Fix ALL calls to _stream_chat inside handle_chat_completions to pass original_body
# Using a more flexible regex to catch calls that might have variations in whitespace
stream_call_pattern = r'_stream_chat\(\s*(.*?),\s*request_logger,\s*start_time,\s*stats_tracker,?\s*\)'
content = re.sub(stream_call_pattern, r'_stream_chat(\1, request_logger, start_time, stats_tracker, original_body=original_body)', content)

# Also fix non-stream calls
non_stream_call_pattern = r'_non_stream_chat\(\s*(.*?),\s*request_logger,\s*start_time,\s*stats_tracker,?\s*\)'
content = re.sub(non_stream_call_pattern, r'_non_stream_chat(\1, request_logger, start_time, stats_tracker, original_body=original_body)', content)

# Fix calls that already might have been partially patched but are wrong
content = content.replace('original_body,', 'original_body=original_body,')

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
    f.write(content)

print("Fix applied to openai_format.py")
