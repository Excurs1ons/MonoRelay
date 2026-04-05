"""Shared utilities for PyInstaller compatibility and SSE parsing."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger("monorelay.utils")


def get_exe_dir() -> Path:
    """获取可执行文件所在目录（兼容 PyInstaller 打包）。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """获取资源路径，兼容 PyInstaller 打包环境。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(getattr(sys, '_MEIPASS')) / relative_path  # type: ignore[arg-type]
    return Path(__file__).resolve().parent.parent / relative_path


async def parse_sse_events(buffer: bytes, max_buffer_size: int = 1024 * 1024) -> tuple[list[dict], bytes]:
    """Parse SSE events from a byte buffer.

    Returns a tuple of (list of parsed event dicts, remaining buffer bytes).
    If the buffer exceeds max_buffer_size without a delimiter, it is truncated
    to prevent unbounded memory growth.
    """
    events = []
    while b"\n\n" in buffer:
        event, buffer = buffer.split(b"\n\n", 1)
        event_dict: dict = {"raw": event}
        for line in event.decode("utf-8", errors="replace").split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    event_dict["done"] = True
                    continue
                try:
                    event_dict["data"] = json.loads(data_str)
                except json.JSONDecodeError:
                    event_dict["data_raw"] = data_str
            elif line.startswith("event: "):
                event_dict["event_type"] = line[7:]
        events.append(event_dict)

    if len(buffer) > max_buffer_size:
        logger.warning(f"SSE buffer exceeded {max_buffer_size} bytes, truncating")
        buffer = buffer[-max_buffer_size:]

    return events, buffer


def mask_token(token: str, prefix_len: int = 4) -> str:
    """Mask a token for safe logging/display."""
    if not token or len(token) <= prefix_len:
        return "***"
    return token[:prefix_len] + "..." + token[-4:]
