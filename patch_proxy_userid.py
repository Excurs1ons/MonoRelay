import sys
import re

def patch_file(path):
    with open(path, 'r') as f:
        content = f.read()
    
    # Add user_id to main handle functions
    content = re.sub(r'async def handle_(\w+)\(\s*body, config, key_manager, router, request_logger, stats_tracker',
                     r'async def handle_\1(body, config, key_manager, router, request_logger, stats_tracker, user_id=None', content)
    
    # Specialized signatures
    content = content.replace('async def handle_models_list(config: AppConfig) -> dict:', 
                            'async def handle_models_list(config: AppConfig, user_id: Optional[int] = None) -> dict:')
    content = content.replace('async def handle_credits(config, key_manager, request_logger, auth_header):',
                            'async def handle_credits(config, key_manager, request_logger, auth_header, user_id=None):')
    
    # Update _stream_chat and _non_stream_chat
    content = content.replace('def _stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body,',
                             'def _stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body, user_id=None,')
    content = content.replace('def _non_stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body,',
                             'def _non_stream_chat(\n    provider_cfg, url, headers, body, key, key_manager, provider_name,\n    resolved_model, original_model, request_logger, start_time, stats_tracker, original_body, user_id=None,')

    # Add user_id to log_request calls
    content = content.replace('await request_logger.log_request(\n                model=', 'await request_logger.log_request(\n                user_id=user_id, model=')
    content = content.replace('await request_logger.log_request(\n                    model=', 'await request_logger.log_request(\n                    user_id=user_id, model=')
    content = content.replace('await request_logger.log_request(\n                            model=', 'await request_logger.log_request(\n                            user_id=user_id, model=')

    with open(path, 'w') as f:
        f.write(content)

patch_file('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py')
# anthropic_format.py uses slightly different patterns but same logic
