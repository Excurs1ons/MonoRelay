"""Format conversion and web reverse service for ChatGPT web interface."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncGenerator

import httpx

from .pow import get_config, get_answer_token, get_requirements_token, fetch_dpl

logger = logging.getLogger("monorelay.web_reverse")

MODEL_MAP = {
    "gpt-3.5-turbo": "text-davinci-002-render-sha",
    "gpt-3.5-turbo-0125": "text-davinci-002-render-sha",
    "gpt-3.5-turbo-16k": "text-davinci-002-render-sha",
    "gpt-4": "gpt-4",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4",
    "gpt-4-32k": "gpt-4",
    "o1-mini": "o1-mini",
    "o1": "o1",
    "o1-preview": "o1-preview",
    "o3-mini": "o3-mini",
    "o3-mini-high": "o3-mini-high",
}

WEB_SUFFIXES = ("-high", "-low", "-medium")


def resolve_web_model(model: str, custom_mapping: dict | None = None) -> str:
    mapping = {**MODEL_MAP, **(custom_mapping or {})}
    for suffix in WEB_SUFFIXES:
        if model.endswith(suffix):
            base = model[: -len(suffix)]
            if base in mapping:
                return mapping[base] + suffix
    return mapping.get(model, "text-davinci-002-render-sha")


def openai_messages_to_web(messages: list[dict]) -> tuple[list[dict], int]:
    web_messages = []
    total_tokens = 0
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append({"content_type": "text", "parts": [item["text"]]})
                elif item.get("type") == "image_url":
                    url = item["image_url"].get("url", "")
                    parts.append({
                        "content_type": "multimodal_text",
                        "parts": [{"asset_pointer": url, "content_type": "image"}],
                    })
            web_msg = {"id": str(uuid.uuid4()), "author": {"role": role}, "content": parts[0] if len(parts) == 1 else {"content_type": "multimodal_text", "parts": parts}}
        else:
            web_msg = {
                "id": str(uuid.uuid4()),
                "author": {"role": role},
                "content": {"content_type": "text", "parts": [content] if content else [""]},
            }
        if role == "system":
            web_msg["metadata"] = {"default_system_prompt": content}
            continue
        web_messages.append(web_msg)
        if isinstance(content, str):
            total_tokens += len(content) // 4
    return web_messages, total_tokens


def _extract_text_from_web(web_msg: dict) -> str:
    content = web_msg.get("content", {})
    parts = content.get("parts", [])
    return "".join(str(p) for p in parts) if parts else ""


class WebReverseService:
    def __init__(self, provider_name: str, config: dict):
        self.provider_name = provider_name
        self.host_url = config.get("chatgpt_base_url", "https://chatgpt.com")
        self.access_token = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        self.timeout = 120
        self.proxy_url = config.get("proxy_url", "")
        self.pow_difficulty = config.get("pow_difficulty", "00003a")
        self.conversation_only = config.get("conversation_only", False)
        self.chat_token = ""
        self.proof_token = ""
        self.arkose_token = None
        self.turnstile_token = None
        self.base_headers: dict = {}

    def _build_base_headers(self):
        self.base_headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": self.host_url,
            "referer": f"{self.host_url}/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "User-Agent": self.user_agent,
        }
        if self.access_token:
            self.base_headers["authorization"] = f"Bearer {self.access_token}"

    async def prepare(self, access_token: str | None = None):
        self.access_token = access_token
        self._build_base_headers()

        proxy = self.proxy_url if self.proxy_url else None
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10, connect=5.0),
            headers={"User-Agent": self.user_agent},
            proxy=proxy,
        ) as client:
            if not self.conversation_only:
                await fetch_dpl(self.host_url, self.base_headers, client)
                config = get_config(self.user_agent)
                req_token = get_requirements_token(config)

                base_url = self.host_url + ("/backend-api" if self.access_token else "/backend-anon")
                url = f"{base_url}/sentinel/chat-requirements"
                r = await client.post(url, headers=self.base_headers, json={"p": req_token}, timeout=10)
                if r.status_code == 200:
                    resp = r.json()
                    self.chat_token = resp.get("token", "")

                    pow_info = resp.get("proofofwork", {})
                    if pow_info.get("required"):
                        seed = pow_info.get("seed", "")
                        diff = pow_info.get("difficulty", "00003a")
                        if diff <= self.pow_difficulty:
                            self.proof_token, _ = get_answer_token(seed, diff, config)
                        else:
                            self.proof_token = "gAAAAABwQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"
                    else:
                        self.proof_token = ""
                else:
                    logger.error(f"Chat requirements failed: {r.status_code} {r.text}")
                    self.chat_token = ""
                    self.proof_token = ""

    async def chat_completion(
        self,
        body: dict,
        access_token: str,
        history_disabled: bool = True,
    ) -> dict | AsyncGenerator[bytes, None]:
        await self.prepare(access_token)

        original_model = body.get("model", "gpt-3.5-turbo")
        messages = body.get("messages", [])
        max_tokens = body.get("max_tokens", 4096)
        is_stream = body.get("stream", False)

        web_model = resolve_web_model(original_model)
        web_messages, prompt_tokens = openai_messages_to_web(messages)

        parent_id = str(uuid.uuid4())
        chat_request = {
            "action": "next",
            "messages": web_messages,
            "model": web_model,
            "parent_message_id": parent_id,
            "history_and_training_disabled": history_disabled,
            "force_use_sse": True,
            "conversation_mode": {"kind": "primary_assistant"},
            "suggestions": [],
            "system_hints": [],
            "timezone_offset_min": -480,
            "client_contextual_info": {
                "is_dark_mode": True,
                "time_since_loaded": 100,
                "page_height": 800,
                "page_width": 1400,
                "pixel_ratio": 2,
                "screen_height": 1080,
                "screen_width": 1920,
            },
        }

        headers = self.base_headers.copy()
        headers["accept"] = "text/event-stream"
        if self.chat_token:
            headers["openai-sentinel-chat-requirements-token"] = self.chat_token
        if self.proof_token:
            headers["openai-sentinel-proof-token"] = self.proof_token
        if self.arkose_token:
            headers["openai-sentinel-arkose-token"] = self.arkose_token
        if self.turnstile_token:
            headers["openai-sentinel-turnstile-token"] = self.turnstile_token

        base_url = self.host_url + ("/backend-api" if self.access_token else "/backend-anon")
        url = f"{base_url}/conversation"
        proxy = self.proxy_url if self.proxy_url else None

        if is_stream:
            return self._stream_response(url, headers, chat_request, web_model, proxy)
        else:
            return await self._non_stream_response(url, headers, chat_request, web_model, proxy)

    async def _stream_response(self, url, headers, chat_request, web_model, proxy):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers={"User-Agent": self.user_agent},
            proxy=proxy,
        ) as client:
            try:
                async with client.stream("POST", url, headers=headers, json=chat_request) as resp:
                    if resp.status_code >= 400:
                        error_body = await resp.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        logger.error(f"Web reverse error {resp.status_code}: {error_text}")
                        err = json.dumps({"error": {"message": error_text, "status_code": resp.status_code}})
                        yield ("data: " + err + "\n\n").encode()
                        yield b"data: [DONE]\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        msg = data.get("message", {})
                        author = msg.get("author", {})
                        role = author.get("role", "")

                        if role != "assistant":
                            continue

                        text = _extract_text_from_web(msg)
                        if not text:
                            continue

                        openai_chunk = {
                            "id": "chatcmpl-" + str(uuid.uuid4())[:8],
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": web_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield ("data: " + json.dumps(openai_chunk) + "\n\n").encode()

                finish_chunk = {
                    "id": "chatcmpl-" + str(uuid.uuid4())[:8],
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": web_model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield ("data: " + json.dumps(finish_chunk) + "\n\n").encode()
                yield b"data: [DONE]\n\n"

            except Exception as e:
                logger.error(f"Web reverse streaming error: {e}")
                err = json.dumps({"error": {"message": str(e), "type": "web_reverse_error"}})
                yield ("data: " + err + "\n\n").encode()
                yield b"data: [DONE]\n\n"

    async def _non_stream_response(self, url, headers, chat_request, web_model, proxy):
        full_text = ""
        async for chunk_bytes in self._stream_response(url, headers, chat_request, web_model, proxy):
            chunk_str = chunk_bytes.decode("utf-8")
            if chunk_str.startswith("data: ") and not chunk_str.startswith("data: [DONE]"):
                try:
                    data = json.loads(chunk_str[6:])
                    choices = data.get("choices", [])
                    if choices and choices[0].get("delta", {}).get("content"):
                        full_text += choices[0]["delta"]["content"]
                except json.JSONDecodeError:
                    continue

        return {
            "id": "chatcmpl-" + str(uuid.uuid4())[:8],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": web_model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": full_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": len(full_text) // 4,
                "total_tokens": len(full_text) // 4,
            },
        }
