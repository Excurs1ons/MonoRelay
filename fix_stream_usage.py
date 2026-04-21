import sys
import re

file_path = '/root/ociTurner/MonoRelay/backend/proxy/openai_format.py'
with open(file_path, 'r') as f:
    content = f.read()

# Refine _stream_chat to better prioritize upstream usage data
old_loop = '''                                    try:
                                        data = json.loads(data_str)
                                        if not last_id: last_id = data.get("id")
                                        if not last_model: last_model = data.get("model")
                                        if not last_fingerprint: last_fingerprint = data.get("system_fingerprint")
                                        last_chunk_data = data
                                        usage = data.get("usage")
                                        if usage:
                                            tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens")
                                            tokens_out = usage.get("completion_tokens") or usage.get("output_tokens")
                                            details = usage.get("completion_tokens_details", {}) or usage.get("prompt_tokens_details", {})
                                            thinking_tokens = details.get("reasoning_tokens")'''

new_loop = '''                                    try:
                                        data = json.loads(data_str)
                                        if not last_id: last_id = data.get("id")
                                        if not last_model: last_model = data.get("model")
                                        if not last_fingerprint: last_fingerprint = data.get("system_fingerprint")
                                        last_chunk_data = data
                                        usage = data.get("usage")
                                        if usage:
                                            # If upstream provides usage, trust it absolutely
                                            u_in = usage.get("prompt_tokens") or usage.get("input_tokens")
                                            u_out = usage.get("completion_tokens") or usage.get("output_tokens")
                                            if u_in is not None: tokens_in = u_in
                                            if u_out is not None: tokens_out = u_out
                                            details = usage.get("completion_tokens_details", {}) or usage.get("prompt_tokens_details", {})
                                            u_think = details.get("reasoning_tokens")
                                            if u_think is not None: thinking_tokens = u_think'''
content = content.replace(old_loop, new_loop)

# Add content-based estimation fallback for tokens_out if upstream didn't provide it
old_calc = '''            tokens_in = int(tokens_in) if tokens_in is not None else None
            tokens_out = int(tokens_out) if tokens_out is not None else None'''
new_calc = '''            # Fallback estimation if upstream usage was missing
            is_estimated_in = False
            if tokens_in is None:
                tokens_in = _estimate_input_tokens(body.get("messages", []))
                is_estimated_in = True
                
            is_estimated_out = False
            if tokens_out is None:
                tokens_out = _estimate_tokens(full_output) + _estimate_tokens(full_thinking)
                is_estimated_out = True
                
            tokens_in = int(tokens_in) if tokens_in is not None else 0
            tokens_out = int(tokens_out) if tokens_out is not None else 0'''
content = content.replace(old_calc, new_calc)

with open(file_path, 'w') as f:
    f.write(content)

print("Stream usage logic refined.")
