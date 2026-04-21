import sys
import re

file_path = '/root/ociTurner/MonoRelay/backend/proxy/openai_format.py'
with open(file_path, 'r') as f:
    content = f.read()

# 1. Add balance check logic helper
balance_check_func = '''
async def _check_user_balance(user_id, config: AppConfig):
    if not config.billing.enabled or user_id == 0: return True
    from ..main import user_manager
    user = await user_manager.get_user_by_id(user_id)
    if not user: return False
    if config.billing.enforce_balance and user.balance <= 0: return False
    return True

def _calculate_credits(provider_cfg: ProviderConfig, model: str, input_tokens: int, output_tokens: int) -> float:
    rate = provider_cfg.model_rates.get(model)
    rate_in = rate.input if rate else provider_cfg.cost_per_m_input
    rate_out = rate.output if rate else provider_cfg.cost_per_m_output
    return (input_tokens * rate_in + output_tokens * rate_out) / 1000000
'''
content = content.replace('logger = logging.getLogger("monorelay.openai_proxy")', 'logger = logging.getLogger("monorelay.openai_proxy")' + balance_check_func)

# 2. Inject pre-check into handle_chat_completions
content = content.replace('original_body = body.copy()', 
                        'original_body = body.copy()\n    if not await _check_user_balance(user_id, config): return {"error": {"message": "Insufficient balance", "type": "insufficient_balance"}}')

# 3. Update _stream_chat to deduct balance on success
old_stream_log = '            await request_logger.log_request('
new_stream_log = '''            # Billing: deduct credits
            if config.billing.enabled and user_id and user_id != 0:
                cost = _calculate_credits(provider_cfg, resolved_model, tokens_in or 0, tokens_out or 0)
                from ..main import user_manager
                await user_manager.update_balance(user_id, -cost)
            
            await request_logger.log_request('''
content = content.replace(old_stream_log, new_stream_log)

# 4. Update _non_stream_chat to deduct balance on success
old_non_stream_log = '            await request_logger.log_request('
new_non_stream_log = '''            # Billing: deduct credits
            if config.billing.enabled and user_id and user_id != 0:
                cost = _calculate_credits(provider_cfg, resolved_model, tokens_in or 0, tokens_out or 0)
                from ..main import user_manager
                await user_manager.update_balance(user_id, -cost)
            
            await request_logger.log_request('''
content = content.replace(old_non_stream_log, new_non_stream_log)

with open(file_path, 'w') as f:
    f.write(content)
print("Billing patch applied.")
