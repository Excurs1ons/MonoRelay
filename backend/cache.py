"""Response caching for identical LLM requests."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("monorelay.cache")


class ResponseCache:
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: dict[str, dict[str, Any]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def _make_key(self, body: dict, model: str) -> str:
        serialized = json.dumps(body, sort_keys=True, default=str)
        combined = f"{model}:{serialized}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    def get(self, body: dict, model: str) -> Optional[dict]:
        key = self._make_key(body, model)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > self._ttl_seconds:
            del self._cache[key]
            return None
        return entry["response"]

    def set(self, body: dict, model: str, response: dict):
        key = self._make_key(body, model)
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
            "model": model,
        }

    def invalidate(self, model: Optional[str] = None):
        if model is None:
            self._cache.clear()
        else:
            to_remove = [k for k, v in self._cache.items() if v.get("model") == model]
            for k in to_remove:
                del self._cache[k]

    def stats(self) -> dict:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl_seconds,
        }


response_cache = ResponseCache()
