import sys
import re

# --- openai_format.py ---
with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'r') as f:
    content = f.read()

# Update _stream_chat to capture more metadata for better reconstruction
old_vars = '            output_content = []\n            output_thinking = []\n            response_preview = None'
new_vars = '            output_content = []\n            output_thinking = []\n            response_preview = None\n            last_id, last_model, last_fingerprint = None, None, None'
content = content.replace(old_vars, new_vars)

old_parse = '                                    try:\n                                        data = json.loads(data_str)\n                                        last_chunk_data = data'
new_parse = '                                    try:\n                                        data = json.loads(data_str)\n                                        if not last_id: last_id = data.get("id")\n                                        if not last_model: last_model = data.get("model")\n                                        if not last_fingerprint: last_fingerprint = data.get("system_fingerprint")'
content = content.replace(old_parse, new_parse)

old_recon = '''            response_full_obj = {"content": full_output}
            if full_thinking:
                response_full_obj["reasoning_content"] = full_thinking
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)'''
new_recon = '''            response_full_obj = {
                "id": last_id or f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(start_time),
                "model": last_model or resolved_model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_output,
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": tokens_in,
                    "completion_tokens": tokens_out,
                    "total_tokens": (tokens_in or 0) + (tokens_out or 0)
                }
            }
            if last_fingerprint: response_full_obj["system_fingerprint"] = last_fingerprint
            if full_thinking:
                response_full_obj["choices"][0]["message"]["reasoning_content"] = full_thinking
                if thinking_tokens:
                    response_full_obj["usage"]["completion_tokens_details"] = {"reasoning_tokens": thinking_tokens}
            response_full_str = json.dumps(response_full_obj, ensure_ascii=False, indent=2)'''
content = content.replace(old_recon, new_recon)

with open('/root/ociTurner/MonoRelay/backend/proxy/openai_format.py', 'w') as f:
    f.write(content)

# --- anthropic_format.py ---
with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'r') as f:
    content = f.read()

# Similar reconstruction for Anthropic stream
old_sm3 = '            response_full_obj = {"content": full_content}\n            if full_thinking: response_full_obj["reasoning_content"] = full_thinking'
new_sm3 = '            response_full_obj = {\n                "id": f"msg_{int(time.time())}",\n                "type": "message",\n                "role": "assistant",\n                "model": resolved_model,\n                "content": [{"type": "text", "text": full_content}],\n                "usage": {"input_tokens": tokens_in or 0, "output_tokens": tokens_out or 0}\n            }\n            if full_thinking: response_full_obj["content"].insert(0, {"type": "thinking", "thinking": full_thinking})'
content = content.replace(old_sm3, new_sm3)

with open('/root/ociTurner/MonoRelay/backend/proxy/anthropic_format.py', 'w') as f:
    f.write(content)

print("Stream reconstruction logic updated.")
