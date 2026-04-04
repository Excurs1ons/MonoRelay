"""SSE streaming core - bidirectional streaming relay."""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import httpx

logger = logging.getLogger("prisma.streaming")


async def stream_openai_response(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    json_body: dict,
    timeout: int = 120,
) -> AsyncGenerator[bytes, None]:
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
            logger.error(f"Upstream error {response.status_code}: {error_text}")
            err = json.dumps({"error": {"message": error_text, "status_code": response.status_code}})
            yield ("data: " + err + "\n\n").encode()
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
    timeout: int = 120,
) -> AsyncGenerator[bytes, None]:
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
            logger.error(f"Anthropic upstream error {response.status_code}: {error_text}")
            event_data = json.dumps({"type": "error", "error": {"message": error_text, "type": "upstream_error"}})
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
