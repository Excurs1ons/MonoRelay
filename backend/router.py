"""Model routing engine with alias, prefix matching, auto-mapping, and complexity scoring."""
from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any, Optional

from .models import AppConfig
from .tenant_manager import TenantManager

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
    def __init__(self, config: AppConfig, tenant_manager: Optional[TenantManager] = None):
        self.config = config
        self.tenant_manager = tenant_manager

    def resolve_model(self, model: str, messages: list[dict] | None = None) -> tuple[str, str]:
        """Resolve model by alias, provider_mapping, override, then provider matching."""
        original_model = model

        # Check if model has provider suffix (e.g., "gpt-4o@openrouter")
        if "@" in model:
            parts = model.rsplit("@", 1)
            if len(parts) == 2:
                resolved_model = parts[0]
                explicit_provider_raw = parts[1]
                
                # Normalize requested provider name
                norm_requested = self._normalize_id(explicit_provider_raw)
                
                # Find matching provider in config (normalized)
                found_provider = None
                for p_name, pc in self.config.providers.items():
                    if self._normalize_id(p_name) == norm_requested:
                        if pc.enabled:
                            found_provider = p_name
                        break
                
                if found_provider:
                    # Apply alias and model_overrides to the model part (before sending to upstream)
                    model_part = resolved_model

                    aliased = self._resolve_alias(model_part)
                    if aliased:
                        model_part = aliased
                        logger.info(f"Model alias (explicit provider): '{resolved_model}' -> '{model_part}'")

                    model_part = self._apply_override(model_part)
                    if model_part != resolved_model:
                        logger.info(f"Model override (explicit provider): '{resolved_model}' -> '{model_part}'")

                    logger.info(f"Model with provider suffix: '{model}' -> model='{model_part}', provider='{found_provider}'")
                    return model_part, found_provider

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

        model, provider = self._resolve_provider(model)
        if model != original_model:
            logger.info(f"Model routing: '{original_model}' -> '{model}' (provider: {provider})")
        return model, provider

    def _resolve_alias(self, model: str) -> Optional[str]:
        aliases = self.config.model_routing.aliases
        visited = set()
        current = model
        while current not in visited:
            visited.add(current)
            found = None
            for alias_key, target in aliases.items():
                if self._normalize_id(alias_key) == self._normalize_id(current):
                    found = target
                    break
            if found:
                current = found
            else:
                break
        return current if current != model else None

    def _resolve_provider_mapping(self, model: str) -> Optional[str]:
        """Match model against provider_mapping fnmatch patterns."""
        mapping = self.config.model_routing.provider_mapping
        for pattern, target_provider in mapping.items():
            if fnmatch.fnmatch(model.lower(), pattern.lower()):
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

    def _normalize_id(self, model: str) -> str:
        """Normalize model ID by lowering case and removing common separators."""
        return model.lower().replace("-", "").replace("_", "")

    def _resolve_provider(self, model: str) -> tuple[str, str]:
        """Find the first provider that has this model enabled."""
        # Pass 1: Exact match in 'include' list (Sensitive)
        for name, pc in self.config.providers.items():
            if not pc.enabled: continue
            enabled_models = pc.models.get("include", []) if pc.models else []
            if model in enabled_models: return model, name

        # Pass 2: Insensitive/Normalized match or catch-all
        model_norm = self._normalize_id(model)
        for name, pc in self.config.providers.items():
            if not pc.enabled: continue
            enabled_models = pc.models.get("include", []) if pc.models else []
            if not enabled_models: return model, name
            for em in enabled_models:
                em_norm = self._normalize_id(em)
                if em_norm == model_norm: return em, name
                if em_norm in model_norm or model_norm in em_norm: return em, name

        for name, pc in self.config.providers.items():
            if pc.enabled: return model, name
        return model, "openrouter"

    def _guess_provider(self, model: str) -> tuple[str, str]:
        return self._resolve_provider(model)

    def resolve_cascade(self, body: dict, messages: list[dict] | None = None) -> list[tuple[str, str]]:
        cascade = self.config.model_routing.cascade
        if not cascade.enabled or not cascade.models: return []
        results = []
        for model in cascade.models:
            aliased = self._resolve_alias(model)
            if aliased: model = aliased
            mapped_provider = self._resolve_provider_mapping(model)
            if mapped_provider:
                results.append((model, mapped_provider))
                continue
            model, provider = self._resolve_provider(model)
            results.append((model, provider))
        return results

    def _complexity_route(self, messages: list[dict]) -> str:
        score = self._score_complexity(messages)
        cfg = self.config.model_routing.complexity
        if score < 0: return cfg.simple
        elif score < 0.35: return cfg.moderate
        else: return cfg.complex

    def _score_complexity(self, messages: list[dict]) -> float:
        text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))
        if not text: return 0
        score, text_lower = 0.0, text.lower()
        if (len(text) / 4) > 50000: return 1.0
        if sum(1 for kw in REASONING_KEYWORDS if kw in text_lower) >= 2: return 0.95
        for kw in REASONING_KEYWORDS:
            if kw in text_lower: score += 0.18
        for kw in CODE_KEYWORDS:
            if kw in text_lower: score += 0.14
        for kw in SIMPLE_KEYWORDS:
            if kw in text_lower: score -= 0.12
        if "```" in text: score += 0.1
        if text.count("?") > 2: score += 0.05
        return max(-1.0, min(1.0, score))

    def supports_tools(self, model: str) -> bool:
        patterns = self.config.tool_calling.unsupported_models
        if not self.config.tool_calling.auto_downgrade: return True
        for pattern in patterns:
            if fnmatch.fnmatch(model.lower(), pattern.lower()): return False
        return True

    def strip_tools(self, body: dict) -> dict:
        body = body.copy()
        body.pop("tools", None)
        body.pop("tool_choice", None)
        return body

    def apply_transformation(self, body: dict, model: str) -> dict:
        body = body.copy()
        
        for mp in self.config.model_routing.model_params:
            if mp.model_pattern and fnmatch.fnmatch(model.lower(), mp.model_pattern.lower()):
                for key, value in mp.params.items():
                    body[key] = value
                if mp.system_prompt:
                    messages = body.get("messages", [])
                    if isinstance(messages, list):
                        messages.insert(0, {"role": "system", "content": mp.system_prompt})
                        body["messages"] = messages
                break
        
        # 1. Payload Transformation Rules
        pt = self.config.model_routing.payload_transformation
        if pt.enabled:
            for rule in pt.rules:
                if not rule.models: continue
                if any(fnmatch.fnmatch(model.lower(), p.lower()) for p in rule.models):
                    for key, value in rule.inject_params.items():
                        if key not in body: body[key] = value
                    for key, value in rule.override_params.items():
                        if "." in key: self._set_nested(body, key, value)
                        else: body[key] = value
        
        # 2. Global Request Parameters & System Prompt
        gp = self.config.model_routing.global_params
        if gp.enabled:
            # Handle standard params
            if gp.params:
                for key, value in gp.params.items():
                    if gp.mode == "override":
                        if "." in key: self._set_nested(body, key, value)
                        else: body[key] = value
                    else: # "default" mode (Combination/Fill)
                        if key not in body:
                            if "." in key: self._set_nested(body, key, value)
                            else: body[key] = value
            
            if gp.system_prompt:
                messages = body.get("messages", [])
                if isinstance(messages, list):
                    if gp.mode == "override":
                        messages = [m for m in messages if m.get("role") != "system"]
                        messages.insert(0, {"role": "system", "content": gp.system_prompt})
                        body["messages"] = messages
                    else:
                        found_system = False
                        for m in messages:
                            if m.get("role") == "system":
                                current_content = m.get("content", "")
                                if isinstance(current_content, str):
                                    m["content"] = f"{gp.system_prompt}\n\n{current_content}"
                                    found_system = True
                                    break
                        if not found_system:
                            messages.insert(0, {"role": "system", "content": gp.system_prompt})
                            body["messages"] = messages
        
        return body

    def _set_nested(self, d: dict, path: str, value: Any) -> None:
        keys = path.split(".")
        current = d
        for key in keys[:-1]:
            if key not in current: current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    async def get_providers_for_user(self, user_id: Optional[int] = None) -> dict[str, Any]:
        """Get providers for a specific user, checking tenant-specific providers first."""
        if user_id and self.tenant_manager:
            tenant_providers = await self.tenant_manager.get_tenant_providers(user_id)
            if tenant_providers:
                logger.info(f"Using tenant-specific providers for user {user_id}")
                return self._build_tenant_provider_dict(tenant_providers)
        
        return self.config.providers

    def _build_tenant_provider_dict(self, tenant_providers: list) -> dict[str, Any]:
        """Build a provider dict from tenant-specific providers."""
        providers = {}
        for tp in tenant_providers:
            if not tp.enabled:
                continue
            
            providers[tp.provider_name] = {
                "enabled": True,
                "base_url": tp.base_url,
                "headers": json.loads(tp.headers_json) if tp.headers_json else {},
                "models": json.loads(tp.models_json) if tp.models_json else {"include": [], "exclude": []},
                "priority": tp.priority
            }
        
        return providers

    async def resolve_model_for_user(
        self,
        model: str,
        user_id: Optional[int] = None,
        messages: list[dict] | None = None
    ) -> tuple[str, str]:
        """Resolve model for a specific user, using tenant-specific providers if available."""
        if user_id and self.tenant_manager:
            tenant_providers = await self.tenant_manager.get_tenant_providers(user_id)
            if tenant_providers:
                logger.info(f"Resolving model for user {user_id} using tenant-specific providers")
                return self._resolve_model_with_providers(model, messages, tenant_providers)
        
        return self.resolve_model(model, messages)

    def _resolve_model_with_providers(
        self,
        model: str,
        messages: list[dict] | None,
        tenant_providers: list
    ) -> tuple[str, str]:
        """Resolve model using tenant-specific providers."""
        original_model = model

        if "@" in model:
            parts = model.rsplit("@", 1)
            if len(parts) == 2:
                resolved_model = parts[0]
                explicit_provider_raw = parts[1]
                
                norm_requested = self._normalize_id(explicit_provider_raw)
                
                for tp in tenant_providers:
                    if self._normalize_id(tp.provider_name) == norm_requested and tp.enabled:
                        return resolved_model, tp.provider_name
        
        aliased = self._resolve_alias(model)
        if aliased:
            model = aliased
            logger.info(f"Model alias: '{original_model}' -> '{model}'")

        model = self._apply_override(model)

        if self.config.model_routing.complexity.enabled and messages:
            model = self._complexity_route(messages)

        for tp in tenant_providers:
            if not tp.enabled:
                continue
            
            models = json.loads(tp.models_json) if tp.models_json else {"include": [], "exclude": []}
            enabled_models = models.get("include", [])
            
            if model in enabled_models:
                return model, tp.provider_name
            
            model_norm = self._normalize_id(model)
            for em in enabled_models:
                em_norm = self._normalize_id(em)
                if em_norm == model_norm:
                    return em, tp.provider_name
                if em_norm in model_norm or model_norm in em_norm:
                    return em, tp.provider_name
            
            if not enabled_models:
                return model, tp.provider_name
        
        return model, "openrouter"
