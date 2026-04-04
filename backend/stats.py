"""Statistics tracking and cost estimation."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("prisma.stats")

# Approximate per-token costs in USD (input / output per 1M tokens)
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 3.50),
    "llama-3.3-70b": (0.20, 0.60),
    "llama-3.1-8b": (0.05, 0.10),
    "mixtral-8x7b": (0.24, 0.24),
    "deepseek-chat": (0.14, 0.28),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    model_lower = model.lower()
    for pattern, (input_cost, output_cost) in MODEL_COSTS.items():
        if pattern in model_lower:
            return (input_tokens / 1_000_000) * input_cost + (output_tokens / 1_000_000) * output_cost
    return (input_tokens / 1_000_000) * 0.50 + (output_tokens / 1_000_000) * 1.50


def extract_token_usage(response_data: dict) -> tuple[Optional[int], Optional[int]]:
    usage = response_data.get("usage")
    if usage:
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        return (
            int(input_tokens) if input_tokens is not None else None,
            int(output_tokens) if output_tokens is not None else None,
        )
    return None, None


def extract_anthropic_token_usage(response_data: dict) -> tuple[Optional[int], Optional[int]]:
    usage = response_data.get("usage")
    if usage:
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        return (
            int(input_tokens) if input_tokens is not None else None,
            int(output_tokens) if output_tokens is not None else None,
        )
    return None, None


class StatsTracker:
    DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "stats.json"

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self.DEFAULT_PATH
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_tokens_estimated: int = 0
        self.total_cost: float = 0.0
        self.requests_by_provider: dict[str, int] = {}
        self.requests_by_model: dict[str, int] = {}
        self.errors_by_provider: dict[str, int] = {}
        self.model_stats: dict[str, dict] = {}

        # Load persisted stats on init
        self._load()

    def _load(self):
        """Load stats from disk if file exists."""
        if not self.db_path.exists():
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.total_requests = data.get("total_requests", 0)
            self.total_errors = data.get("total_errors", 0)
            self.total_tokens_in = data.get("total_tokens_in", 0)
            self.total_tokens_out = data.get("total_tokens_out", 0)
            self.total_tokens_estimated = data.get("total_tokens_estimated", 0)
            self.total_cost = data.get("total_cost", 0.0)
            self.requests_by_provider = data.get("requests_by_provider", {})
            self.requests_by_model = data.get("requests_by_model", {})
            self.errors_by_provider = data.get("errors_by_provider", {})
            self.model_stats = data.get("model_stats", {})
            logger.info(f"Stats loaded from {self.db_path} ({self.total_requests} requests)")
        except Exception as e:
            logger.warning(f"Failed to load stats: {e}")

    def save(self):
        """Persist stats to disk."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_tokens_in": self.total_tokens_in,
                "total_tokens_out": self.total_tokens_out,
                "total_tokens_estimated": self.total_tokens_estimated,
                "total_cost": self.total_cost,
                "requests_by_provider": self.requests_by_provider,
                "requests_by_model": self.requests_by_model,
                "errors_by_provider": self.errors_by_provider,
                "model_stats": self.model_stats,
            }
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        success: bool = True,
        is_estimated: bool = False,
        latency_ms: float = 0,
        is_streaming: bool = False,
        first_token_ms: Optional[float] = None,
        stream_chunks: int = 0,
    ):
        self.total_requests += 1
        self.requests_by_provider[provider] = self.requests_by_provider.get(provider, 0) + 1
        self.requests_by_model[model] = self.requests_by_model.get(model, 0) + 1

        in_tokens = input_tokens or 0
        out_tokens = output_tokens or 0

        if input_tokens is not None:
            self.total_tokens_in += in_tokens
        if output_tokens is not None:
            self.total_tokens_out += out_tokens
        if is_estimated and (input_tokens is not None or output_tokens is not None):
            self.total_tokens_estimated += in_tokens + out_tokens

        # Calculate cost even with partial token data
        cost = estimate_cost(model, in_tokens, out_tokens)
        if input_tokens is not None or output_tokens is not None:
            self.total_cost += cost

        if not success:
            self.total_errors += 1
            self.errors_by_provider[provider] = self.errors_by_provider.get(provider, 0) + 1

        # Per-model detailed stats
        if model not in self.model_stats:
            self.model_stats[model] = {
                "requests": 0,
                "errors": 0,
                "total_tokens_in": 0,
                "total_tokens_out": 0,
                "total_latency_ms": 0,
                "total_first_token_ms": 0,
                "first_token_count": 0,
                "streaming_requests": 0,
                "total_stream_chunks": 0,
                "total_output_tokens_for_speed": 0,
                "total_stream_duration_ms": 0,
            }
        ms = self.model_stats[model]
        ms["requests"] += 1
        if not success:
            ms["errors"] += 1
        ms["total_tokens_in"] += in_tokens
        ms["total_tokens_out"] += out_tokens
        ms["total_latency_ms"] += latency_ms
        if is_streaming:
            ms["streaming_requests"] += 1
            ms["total_stream_chunks"] += stream_chunks
            if output_tokens is not None and latency_ms > 0:
                ms["total_output_tokens_for_speed"] += out_tokens
                ms["total_stream_duration_ms"] += latency_ms
        if first_token_ms is not None:
            ms["total_first_token_ms"] += first_token_ms
            ms["first_token_count"] += 1

        # Auto-save after each request
        self.save()

    def get_summary(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / max(self.total_requests, 1),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens_estimated": self.total_tokens_estimated,
            "total_tokens": self.total_tokens_in + self.total_tokens_out,
            "estimated_total_cost": round(self.total_cost, 6),
            "requests_by_provider": dict(self.requests_by_provider),
            "requests_by_model": dict(self.requests_by_model),
            "errors_by_provider": dict(self.errors_by_provider),
        }

    def get_model_details(self) -> dict:
        """Get detailed per-model statistics."""
        result = {}
        for model, ms in self.model_stats.items():
            req = ms["requests"]
            if req == 0:
                continue
            avg_latency = ms["total_latency_ms"] / req if req > 0 else 0
            avg_first_token = ms["total_first_token_ms"] / ms["first_token_count"] if ms["first_token_count"] > 0 else None
            avg_speed = ms["total_output_tokens_for_speed"] / (ms["total_stream_duration_ms"] / 1000) if ms["total_stream_duration_ms"] > 0 else None

            result[model] = {
                "requests": req,
                "errors": ms["errors"],
                "total_tokens_in": ms["total_tokens_in"],
                "total_tokens_out": ms["total_tokens_out"],
                "avg_latency_ms": round(avg_latency, 1),
                "avg_first_token_ms": round(avg_first_token, 1) if avg_first_token is not None else None,
                "avg_speed_tps": round(avg_speed, 1) if avg_speed is not None else None,
                "streaming_requests": ms["streaming_requests"],
            }
        return result

    def reset(self):
        self.__init__()
