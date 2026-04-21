import sys
import re

# 1. Patch openai_format.py
with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
    content = f.read()

# Capture original_body in handle_chat_completions
old_handle = '''    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model

    body = router.apply_transformation(body, resolved_model)'''
new_handle = '''    original_body = body.copy()
    resolved_model, provider_name = router.resolve_model(original_model, messages)
    body["model"] = resolved_model

    body = router.apply_transformation(body, resolved_model)'''
content = content.replace(old_handle, new_handle)

# Use original_body for logging
content = content.replace('request_full=json.dumps(body, ensure_ascii=False) if body else None', 
                         'request_full=json.dumps(original_body if "original_body" in locals() else body, ensure_ascii=False, indent=2)')

# Prettify other JSON dumps
content = content.replace('response_full_str = json.dumps(response_full_obj, ensure_ascii=False)',
                         'response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)')
content = content.replace('response_full=json.dumps(result, ensure_ascii=False) if result else None',
                         'response_full=json.dumps(result, ensure_ascii=False, indent=2) if result else None')

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
    f.write(content)

# 2. Patch anthropic_format.py
with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'r') as f:
    content = f.read()

# Prettify
content = content.replace('request_full=json.dumps(body, ensure_ascii=False) if body else None',
                         'request_full=json.dumps(body, ensure_ascii=False, indent=2)')
content = content.replace('response_full=json.dumps(result, ensure_ascii=False) if result else None',
                         'response_full=json.dumps(result, ensure_ascii=False, indent=2) if result else None')
content = content.replace('response_full_str = json.dumps(response_full_obj, ensure_ascii=False)',
                         'response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)')
content = content.replace('response_full=json.dumps(out, ensure_ascii=False)',
                         'response_full=json.dumps(out, ensure_ascii=False, indent=2)')

with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'w') as f:
    f.write(content)

print("Patch applied.")
