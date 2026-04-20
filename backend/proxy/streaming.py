"""SSE streaming core - bidirectional streaming relay."""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger("monorelay.streaming")


async def stream_openai_response(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    json_body: dict,
    provider_name: str = "upstream",
    timeout: int = 120,
) -> AsyncGenerator[bytes]:
    async with client.stream(
        "POST",
        url,
        headers=headers,
        json=json_body,
        timeout=httpx.Timeout(timeout, connect=10.0),
    ) as response:
        if response.status_code >= 400:
            error_body = await response.aread()
            error_text = error_body.decode("utf-8", errors="replace")
            logger.error(f"[{provider_name}] Upstream error {response.status_code}: {error_text}")
            err = json.dumps({"error": {"message": f"[{provider_name}] {error_text}", "status_code": response.status_code}})
            yield f"data: {err}\n\n".encode()
            yield b"data: [DONE]\n\n"
            return

        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk


async def stream_anthropic_response(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    json_body: dict,
    provider_name: str = "anthropic",
    timeout: int = 120,
) -> AsyncGenerator[bytes]:
    async with client.stream(
        "POST",
        url,
        headers=headers,
        json=json_body,
        timeout=httpx.Timeout(timeout, connect=10.0),
    ) as response:
        if response.status_code >= 400:
            error_body = await response.aread()
            error_text = error_body.decode("utf-8", errors="replace")
            logger.error(f"[{provider_name}] Anthropic upstream error {response.status_code}: {error_text}")
            event_data = json.dumps({"type": "error", "error": {"message": f"[{provider_name}] {error_text}", "type": "upstream_error"}})
            yield ("event: error\ndata: " + event_data + "\n\n").encode()
            return

        buffer = b""
        async for chunk in response.aiter_bytes():
            buffer += chunk
            while b"\n\n" in buffer:
                event, buffer = buffer.split(b"\n\n", 1)
                yield event + b"\n\n"

        if buffer:
            yield buffer


def extract_stream_usage(chunk_bytes: bytes) -> Optional[dict]:
    """Parse SSE chunk to extract token usage from the final [DONE] message.

    OpenAI-compatible APIs include usage in the last data chunk before [DONE].
    Returns the usage dict if found, None otherwise.
    """
    try:
        text = chunk_bytes.decode("utf-8", errors="replace")
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue
                data = json.loads(data_str)
                usage = data.get("usage")
                if usage:
                    return usage
    except Exception:
        pass
    return None
