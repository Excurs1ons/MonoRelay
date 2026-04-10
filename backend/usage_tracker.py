"""Per-client API usage tracking."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClientUsage:
    requests: int = 0
    errors: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    last_request: float = 0.0
    latency_ms_total: float = 0.0


class UsageTracker:
    def __init__(self, max_clients: int = 1000):
        self._clients: dict[str, ClientUsage] = defaultdict(ClientUsage)
        self._max_clients = max_clients
        self._total: ClientUsage = ClientUsage()

    def record(
        self,
        client_id: Optional[str],
        success: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = 0.0,
        latency_ms: float = 0.0,
    ):
        cid = client_id or "anonymous"
        u = self._clients[cid]
        u.requests += 1
        u.tokens_in += tokens_in
        u.tokens_out += tokens_out
        u.cost += cost
        u.latency_ms_total += latency_ms
        u.last_request = time.time()
        if not success:
            u.errors += 1

        self._total.requests += 1
        self._total.errors += 0 if success else 1
        self._total.tokens_in += tokens_in
        self._total.tokens_out += tokens_out
        self._total.cost += cost
        self._total.latency_ms_total += latency_ms
        self._total.last_request = time.time()

    def get_stats(self, client_id: Optional[str] = None) -> dict:
        if client_id:
            u = self._clients.get(client_id)
            if not u:
                return {}
            return {
                "client_id": client_id,
                "requests": u.requests,
                "errors": u.errors,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost": round(u.cost, 6),
                "avg_latency_ms": round(u.latency_ms_total / u.requests, 1) if u.requests else 0,
                "last_request": u.last_request,
            }
        return {
            "total": {
                "requests": self._total.requests,
                "errors": self._total.errors,
                "tokens_in": self._total.tokens_in,
                "tokens_out": self._total.tokens_out,
                "cost": round(self._total.cost, 6),
                "avg_latency_ms": round(self._total.latency_ms_total / self._total.requests, 1) if self._total.requests else 0,
            },
            "clients": {
                cid: {
                    "requests": u.requests,
                    "errors": u.errors,
                    "tokens_in": u.tokens_in,
                    "tokens_out": u.tokens_out,
                    "cost": round(u.cost, 6),
                    "last_request": u.last_request,
                }
                for cid, u in sorted(self._clients.items(), key=lambda x: x[1].requests, reverse=True)
            },
            "active_clients": len(self._clients),
        }

    def clear(self, client_id: Optional[str] = None):
        if client_id:
            self._clients.pop(client_id, None)
        else:
            self._clients.clear()
            self._total = ClientUsage()


usage_tracker = UsageTracker()
