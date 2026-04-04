"""Statistics tracking and cost estimation."""
from __future__ import annotations

import logging
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
    def __init__(self):
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_cost: float = 0.0
        self.requests_by_provider: dict[str, int] = {}
        self.requests_by_model: dict[str, int] = {}
        self.errors_by_provider: dict[str, int] = {}

    def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        success: bool = True,
    ):
        self.total_requests += 1
        self.requests_by_provider[provider] = self.requests_by_provider.get(provider, 0) + 1
        self.requests_by_model[model] = self.requests_by_model.get(model, 0) + 1

        if input_tokens:
            self.total_tokens_in += input_tokens
        if output_tokens:
            self.total_tokens_out += output_tokens

        if input_tokens and output_tokens:
            cost = estimate_cost(model, input_tokens, output_tokens)
            self.total_cost += cost

        if not success:
            self.total_errors += 1
            self.errors_by_provider[provider] = self.errors_by_provider.get(provider, 0) + 1

    def get_summary(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / max(self.total_requests, 1),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out,
            "estimated_total_cost": round(self.total_cost, 6),
            "requests_by_provider": dict(self.requests_by_provider),
            "requests_by_model": dict(self.requests_by_model),
            "errors_by_provider": dict(self.errors_by_provider),
        }

    def reset(self):
        self.__init__()
