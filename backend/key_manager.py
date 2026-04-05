"""API Key manager with round-robin, random, weighted selection and cooldown."""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

from .models import ProviderConfig, ProviderKey

logger = logging.getLogger("monorelay.key_manager")


class KeyEntry:
    def __init__(self, key: ProviderKey):
        self.key = key
        self.cooldown_until: float = 0
        self.fail_count: int = 0
        self.last_used: float = 0
        self.total_requests: int = 0
        self.total_failures: int = 0
        self._request_timestamps: list[float] = []

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
        return len(self._request_timestamps) >= self.key.rate_limit_rps

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
    def __init__(self):
        self._entries: dict[str, list[KeyEntry]] = {}
        self._round_robin_index: dict[str, int] = {}

    def register_provider(self, name: str, config: ProviderConfig):
        entries = [KeyEntry(k) for k in config.keys]
        self._entries[name] = entries
        self._round_robin_index[name] = 0
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
        return entry

    def report_failure(self, provider_name: str, key: KeyEntry, cooldown: int = 60):
        key.mark_failure(cooldown)

    def report_success(self, key: KeyEntry):
        key.mark_success()
        if key.key.quota_limit > 0:
            key.key.quota_used += 1

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
