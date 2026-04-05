"""Model routing engine with alias, prefix matching, auto-mapping, and complexity scoring."""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Optional

from .models import AppConfig, ModelRoutingConfig

logger = logging.getLogger("monorelay.router")

REASONING_KEYWORDS = [
    "analyze", "compare", "evaluate", "synthesize", "reason", "prove",
    "methodology", "architecture", "design pattern", "trade-off", "complex",
]

SIMPLE_KEYWORDS = [
    "what is", "define", "translate", "summarize", "list", "hello", "hi",
    "order status", "tracking", "hours", "help",
]

CODE_KEYWORDS = [
    "code", "function", "class", "def ", "import ", "```", "debug",
    "refactor", "implement", "algorithm", "data structure",
]


class ModelRouter:
    def __init__(self, config: AppConfig):
        self.config = config

    def resolve_model(self, model: str, messages: list[dict] | None = None) -> tuple[str, str]:
        """Resolve model by alias, provider_mapping, override, then provider matching."""
        original_model = model

        # Step 1: Resolve alias
        aliased = self._resolve_alias(model)
        if aliased:
            model = aliased
            logger.info(f"Model alias: '{original_model}' -> '{model}'")

        # Step 2: Apply provider_mapping (fnmatch patterns -> target provider)
        mapped_provider = self._resolve_provider_mapping(model)
        if mapped_provider:
            return model, mapped_provider

        # Step 3: Apply model_overrides
        model = self._apply_override(model)

        # Step 4: Complexity routing (if enabled and messages provided)
        if self.config.model_routing.complexity.enabled and messages:
            model = self._complexity_route(messages)

        provider = self._resolve_provider(model)
        if model != original_model:
            logger.info(f"Model routing: '{original_model}' -> '{model}' (provider: {provider})")
        return model, provider

    def _resolve_alias(self, model: str) -> Optional[str]:
        aliases = self.config.model_routing.aliases
        return aliases.get(model)

    def _resolve_provider_mapping(self, model: str) -> Optional[str]:
        """Match model against provider_mapping fnmatch patterns.

        Returns the provider name if a pattern matches, None otherwise.
        Only considers enabled providers.
        """
        mapping = self.config.model_routing.provider_mapping
        for pattern, target_provider in mapping.items():
            if fnmatch.fnmatch(model.lower(), pattern.lower()):
                # Verify target provider is enabled
                pc = self.config.providers.get(target_provider)
                if pc and pc.enabled:
                    logger.info(f"Provider mapping: '{model}' -> provider '{target_provider}' (pattern: '{pattern}')")
                    return target_provider
        return None

    def _apply_override(self, model: str) -> str:
        overrides = self.config.model_routing.model_overrides
        for pattern, target in overrides.items():
            if fnmatch.fnmatch(model.lower(), pattern.lower()):
                return target
        return model

    def _resolve_provider(self, model: str) -> str:
        """Find the first provider (in config order) that has this model enabled."""
        # Pass 1: Exact match
        for name, pc in self.config.providers.items():
            if not pc.enabled:
                continue
            enabled_models = pc.models.get("include", []) if pc.models else []
            if not enabled_models or model in enabled_models:
                return name

        # Pass 2: Substring match (either direction)
        for name, pc in self.config.providers.items():
            if not pc.enabled:
                continue
            enabled_models = pc.models.get("include", []) if pc.models else []
            if not enabled_models:
                return name  # No filter = all models available
            for em in enabled_models:
                if em in model or model in em:
                    return name

        # Fallback: first enabled provider
        for name, pc in self.config.providers.items():
            if pc.enabled:
                return name

        return "openrouter"

    def _guess_provider(self, model: str) -> str:
        return self._resolve_provider(model)

    def resolve_cascade(self, body: dict, messages: list[dict] | None = None) -> list[tuple[str, str]]:
        """Resolve cascade model sequence for fallback.

        Returns list of (model, provider) tuples in cascade order.
        """
        cascade = self.config.model_routing.cascade
        if not cascade.enabled or not cascade.models:
            return []

        results = []
        for model in cascade.models:
            # Apply alias and provider_mapping for each cascade model
            aliased = self._resolve_alias(model)
            if aliased:
                model = aliased

            mapped_provider = self._resolve_provider_mapping(model)
            if mapped_provider:
                results.append((model, mapped_provider))
                continue

            provider = self._resolve_provider(model)
            results.append((model, provider))

        return results

    def _complexity_route(self, messages: list[dict]) -> str:
        score = self._score_complexity(messages)
        cfg = self.config.model_routing.complexity

        if score < 0:
            return cfg.simple
        elif score < 0.35:
            return cfg.moderate
        else:
            return cfg.complex

    def _score_complexity(self, messages: list[dict]) -> float:
        text = " ".join(
            m.get("content", "") for m in messages
            if isinstance(m.get("content"), str)
        )
        if not text:
            return 0

        score = 0.0
        text_lower = text.lower()
        token_estimate = len(text) / 4

        if token_estimate > 50000:
            return 1.0

        reasoning_count = sum(1 for kw in REASONING_KEYWORDS if kw in text_lower)
        if reasoning_count >= 2:
            return 0.95

        for kw in REASONING_KEYWORDS:
            if kw in text_lower:
                score += 0.18
        for kw in CODE_KEYWORDS:
            if kw in text_lower:
                score += 0.14
        for kw in SIMPLE_KEYWORDS:
            if kw in text_lower:
                score -= 0.12

        if "```" in text:
            score += 0.1
        if text.count("?") > 2:
            score += 0.05

        return max(-1.0, min(1.0, score))

    def supports_tools(self, model: str) -> bool:
        patterns = self.config.tool_calling.unsupported_models
        if not self.config.tool_calling.auto_downgrade:
            return True
        for pattern in patterns:
            if fnmatch.fnmatch(model.lower(), pattern.lower()):
                return False
        return True

    def strip_tools(self, body: dict) -> dict:
        body = body.copy()
        body.pop("tools", None)
        body.pop("tool_choice", None)
        return body
