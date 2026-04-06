"""API Key manager with round-robin, random, weighted selection and cooldown."""
from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Optional

from .models import ProviderConfig, ProviderKey

logger = logging.getLogger("monorelay.key_manager")

WINDOW_5H = 5 * 60 * 60
WINDOW_1D = 24 * 60 * 60
WINDOW_7D = 7 * 24 * 60 * 60


class KeyEntry:
    def __init__(self, key: ProviderKey):
        self.key = key
        self.cooldown_until: float = 0
        self.fail_count: int = 0
        self.last_used: float = 0
        self.total_requests: int = 0
        self.total_failures: int = 0
        self._request_timestamps: list[float] = []
        self._request_timestamps_5h: list[float] = []
        self._request_timestamps_1d: list[float] = []
        self._request_timestamps_7d: list[float] = []
        self.usage_5h: int = 0
        self.usage_1d: int = 0
        self.usage_7d: int = 0

    @property
    def is_cooled_down(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def is_available(self) -> bool:
        return self.key.enabled and self.is_cooled_down and not self.is_quota_exceeded and not self.is_rate_limited

    @property
    def is_quota_exceeded(self) -> bool:
        if self.key.quota_limit <= 0:
            return False
        return self.key.quota_used >= self.key.quota_limit

    @property
    def is_rate_limited(self) -> bool:
        if self.key.rate_limit_rps <= 0:
            return False
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 1.0]
        if len(self._request_timestamps) >= self.key.rate_limit_rps:
            logger.warning(f"Key '{self.key.label}' rate limited (RPS)")
            return True
        if self.check_usage_limit("5h"):
            logger.warning(f"Key '{self.key.label}' hit 5h usage limit ({self.key.usage_window_limits.window_5h})")
            return True
        if self.check_usage_limit("1d"):
            logger.warning(f"Key '{self.key.label}' hit 1d usage limit ({self.key.usage_window_limits.window_1d})")
            return True
        if self.check_usage_limit("7d"):
            logger.warning(f"Key '{self.key.label}' hit 7d usage limit ({self.key.usage_window_limits.window_7d})")
            return True
        return False

    def check_usage_limit(self, window_type: str) -> bool:
        limits = self.key.usage_window_limits
        now = time.time()

        if window_type == "5h":
            if limits.window_5h <= 0:
                return False
            self._request_timestamps_5h = [t for t in self._request_timestamps_5h if now - t < WINDOW_5H]
            return len(self._request_timestamps_5h) >= limits.window_5h
        elif window_type == "1d":
            if limits.window_1d <= 0:
                return False
            self._request_timestamps_1d = [t for t in self._request_timestamps_1d if now - t < WINDOW_1D]
            return len(self._request_timestamps_1d) >= limits.window_1d
        elif window_type == "7d":
            if limits.window_7d <= 0:
                return False
            self._request_timestamps_7d = [t for t in self._request_timestamps_7d if now - t < WINDOW_7D]
            return len(self._request_timestamps_7d) >= limits.window_7d
        return False

    def record_usage(self, tokens: int):
        now = time.time()
        self._request_timestamps_5h.append(now)
        self._request_timestamps_1d.append(now)
        self._request_timestamps_7d.append(now)
        self.usage_5h += tokens
        self.usage_1d += tokens
        self.usage_7d += tokens

    def check_rate_limit(self) -> bool:
        if self.key.rate_limit_rps <= 0:
            return True
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 1.0]
        if len(self._request_timestamps) >= self.key.rate_limit_rps:
            return False
        self._request_timestamps.append(now)
        return True

    def mark_failure(self, cooldown_seconds: int = 60):
        self.fail_count += 1
        self.total_failures += 1
        self.cooldown_until = time.time() + cooldown_seconds
        logger.warning(f"Key '{self.key.label}' cooled down for {cooldown_seconds}s (fail #{self.fail_count})")

    def mark_success(self):
        self.fail_count = 0
        self.last_used = time.time()
        self.total_requests += 1

    def use(self):
        self.last_used = time.time()
        self.total_requests += 1


class KeyManager:
    USAGE_FILE = "./data/key_usage.json"

    def __init__(self):
        self._entries: dict[str, list[KeyEntry]] = {}
        self._round_robin_index: dict[str, int] = {}
        self._load_usage()

    def _load_usage(self):
        if not os.path.exists(self.USAGE_FILE):
            return
        try:
            with open(self.USAGE_FILE, "r") as f:
                data = json.load(f)
            for provider_name, entries_data in data.items():
                if provider_name not in self._entries:
                    continue
                for entry_data in entries_data:
                    label = entry_data.get("label")
                    for entry in self._entries[provider_name]:
                        if entry.key.label == label:
                            entry._request_timestamps_5h = entry_data.get("timestamps_5h", [])
                            entry._request_timestamps_1d = entry_data.get("timestamps_1d", [])
                            entry._request_timestamps_7d = entry_data.get("timestamps_7d", [])
                            entry.usage_5h = entry_data.get("usage_5h", 0)
                            entry.usage_1d = entry_data.get("usage_1d", 0)
                            entry.usage_7d = entry_data.get("usage_7d", 0)
                            break
            logger.info("Loaded key usage from JSON")
        except Exception as e:
            logger.warning(f"Failed to load key usage: {e}")

    def _save_usage(self):
        data = {}
        for provider_name, entries in self._entries.items():
            data[provider_name] = [
                {
                    "label": entry.key.label,
                    "timestamps_5h": entry._request_timestamps_5h,
                    "timestamps_1d": entry._request_timestamps_1d,
                    "timestamps_7d": entry._request_timestamps_7d,
                    "usage_5h": entry.usage_5h,
                    "usage_1d": entry.usage_1d,
                    "usage_7d": entry.usage_7d,
                }
                for entry in entries
            ]
        os.makedirs(os.path.dirname(self.USAGE_FILE), exist_ok=True)
        with open(self.USAGE_FILE, "w") as f:
            json.dump(data, f)

    def register_provider(self, name: str, config: ProviderConfig):
        entries = [KeyEntry(k) for k in config.keys]
        self._entries[name] = entries
        self._round_robin_index[name] = 0
        self._load_usage()
        logger.info(f"Registered provider '{name}' with {len(entries)} key(s)")

    def get_available_keys(self, provider_name: str) -> list[KeyEntry]:
        entries = self._entries.get(provider_name, [])
        return [e for e in entries if e.is_available]

    def select_key(self, provider_name: str, strategy: str = "round-robin") -> Optional[KeyEntry]:
        entries = self._entries.get(provider_name, [])
        if not entries:
            return None

        available = [e for e in entries if e.is_available]
        if not available:
            cooled_down = [e for e in entries if e.key.enabled and e.is_cooled_down and not e.is_quota_exceeded and not e.is_rate_limited]
            if cooled_down:
                logger.warning(f"No fully-available keys for '{provider_name}', using cooled-down key")
                entry = cooled_down[0]
                entry.use()
                return entry
            quota_exceeded = [e for e in entries if e.key.enabled and e.is_quota_exceeded]
            if quota_exceeded:
                logger.warning(f"All keys quota-exceeded for '{provider_name}'")
                return None
            rate_limited = [e for e in entries if e.key.enabled and e.is_rate_limited]
            if rate_limited:
                logger.warning(f"All keys rate-limited for '{provider_name}'")
                return None
            if entries:
                logger.warning(f"No available keys for '{provider_name}', using first key")
                entry = entries[0]
                entry.use()
                return entry
            return None

        if strategy == "random":
            entry = random.choice(available)
        elif strategy == "weighted":
            weights = [e.key.weight for e in available]
            entry = random.choices(available, weights=weights, k=1)[0]
        else:
            idx = self._round_robin_index.get(provider_name, 0) % len(available)
            entry = available[idx]
            self._round_robin_index[provider_name] = idx + 1

        entry.use()
        self._save_usage()
        return entry

    def report_failure(self, provider_name: str, key: KeyEntry, cooldown: int = 60):
        key.mark_failure(cooldown)

    def report_success(self, key: KeyEntry, tokens: int = 0):
        key.mark_success()
        if key.key.quota_limit > 0:
            key.key.quota_used += 1
        if tokens > 0:
            key.record_usage(tokens)

    def get_stats(self) -> dict:
        stats = {}
        for provider, entries in self._entries.items():
            stats[provider] = {
                "total_keys": len(entries),
                "available": sum(1 for e in entries if e.is_available),
                "keys": [
                    {
                        "label": e.key.label,
                        "available": e.is_available,
                        "total_requests": e.total_requests,
                        "total_failures": e.total_failures,
                        "cooldown_until": e.cooldown_until if not e.is_cooled_down else None,
                        "quota_limit": e.key.quota_limit,
                        "quota_used": e.key.quota_used,
                        "rate_limit_rps": e.key.rate_limit_rps,
                        "expires_at": e.key.expires_at,
                    }
                    for e in entries
                ],
            }
        return stats
