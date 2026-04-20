"""Statistics tracking and cost estimation."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .logger import RequestLogger

# Exponential decay weighted average config
MAX_HISTORY = 100       # Max history entries per model
DECAY_RATE = 0.85       # Each older entry's weight = DECAY_RATE ^ distance_from_newest

logger = logging.getLogger("monorelay.stats")


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_per_m_input: float = 0.0,
    cost_per_m_output: float = 0.0,
) -> float:
    if cost_per_m_input > 0 or cost_per_m_output > 0:
        return (input_tokens / 1_000_000) * cost_per_m_input + (output_tokens / 1_000_000) * cost_per_m_output
    return 0.0


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


def _get_exe_dir() -> Path:
    """获取可执行文件所在目录（兼容 PyInstaller 打包）。"""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


class StatsTracker:
    DEFAULT_PATH = _get_exe_dir() / "data" / "stats.json"

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self.DEFAULT_PATH
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
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
            self.total_cost = data.get("total_cost", 0.0)
            self.requests_by_provider = data.get("requests_by_provider", {})
            self.requests_by_model = data.get("requests_by_model", {})
            self.errors_by_provider = data.get("errors_by_provider", {})
            self.model_stats = data.get("model_stats", {})
            self._migrate_model_stats()
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
        cost_per_m_input: float = 0.0,
        cost_per_m_output: float = 0.0,
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

        cost = estimate_cost(model, in_tokens, out_tokens, cost_per_m_input, cost_per_m_output)
        if input_tokens is not None or output_tokens is not None:
            self.total_cost += cost

        if not success:
            self.total_errors += 1
            self.errors_by_provider[provider] = self.errors_by_provider.get(provider, 0) + 1

        ms = self.model_stats.setdefault(model, {
            "requests": 0, "errors": 0, "total_tokens_in": 0, "total_tokens_out": 0,
            "streaming_requests": 0, "_first_token_history": [], "_speed_history": [],
        })
        ms["requests"] += 1
        if not success: ms["errors"] += 1
        ms["total_tokens_in"] += in_tokens
        ms["total_tokens_out"] += out_tokens
        if is_streaming:
            ms["streaming_requests"] += 1
            if first_token_ms is not None:
                ms["_first_token_history"].append(first_token_ms)
                if len(ms["_first_token_history"]) > MAX_HISTORY: ms["_first_token_history"] = ms["_first_token_history"][-MAX_HISTORY:]
            if output_tokens is not None and latency_ms > 0:
                speed = out_tokens / (latency_ms / 1000)
                ms["_speed_history"].append(speed)
                if len(ms["_speed_history"]) > MAX_HISTORY: ms["_speed_history"] = ms["_speed_history"][-MAX_HISTORY:]
        self.save()

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

    def _migrate_model_stats(self):
        for model, ms in self.model_stats.items():
            if "total_first_token_ms" in ms:
                count = ms.get("first_token_count", 0)
                ms["_first_token_history"] = [ms["total_first_token_ms"] / count] * min(count, MAX_HISTORY) if count > 0 else []
                del ms["total_first_token_ms"], ms["first_token_count"]
            if "total_output_tokens_for_speed" in ms and ms.get("total_stream_duration_ms", 0) > 0:
                avg_speed = ms["total_output_tokens_for_speed"] / (ms["total_stream_duration_ms"] / 1000)
                ms["_speed_history"] = [avg_speed] * min(ms.get("streaming_requests", 1), MAX_HISTORY)
                del ms["total_output_tokens_for_speed"], ms["total_stream_duration_ms"]
            for k in ["total_stream_chunks", "total_latency_ms"]: ms.pop(k, None)

    @staticmethod
    def _weighted_avg(values: list[float]) -> float | None:
        if not values: return None
        n = len(values)
        total_weight = sum(DECAY_RATE ** (n - 1 - i) for i in range(n))
        return sum(values[i] * (DECAY_RATE ** (n - 1 - i)) for i in range(n)) / total_weight if total_weight > 0 else None

    def get_model_details(self) -> dict:
        result = {}
        for model, ms in self.model_stats.items():
            if ms["requests"] == 0: continue
            avg_ft = self._weighted_avg(ms.get("_first_token_history", []))
            avg_sp = self._weighted_avg(ms.get("_speed_history", []))
            result[model] = {
                "requests": ms["requests"], "errors": ms["errors"],
                "total_tokens_in": ms["total_tokens_in"], "total_tokens_out": ms["total_tokens_out"],
                "avg_first_token_ms": round(avg_ft, 1) if avg_ft is not None else None,
                "avg_speed_tps": round(avg_sp, 1) if avg_sp is not None else None,
                "streaming_requests": ms["streaming_requests"],
            }
        return result

    async def reset(self, request_logger: Optional[RequestLogger] = None):
        """彻底清空统计数据、删除 JSON 文件并（可选）清空数据库日志。"""
        self.total_requests = 0
        self.total_errors = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost = 0.0
        self.requests_by_provider = {}
        self.requests_by_model = {}
        self.errors_by_provider = {}
        self.model_stats = {}
        if self.db_path.exists():
            try: os.remove(self.db_path)
            except Exception: pass
        if request_logger:
            await request_logger.clear_all()
        logger.info("Statistics and logs cleared via reset.")
