from __future__ import annotations

from typing import Any, Optional, Dict
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None
    name: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[str | list[str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[dict[str, float]] = None
    user: Optional[str] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str | dict[str, Any]] = None
    response_format: Optional[dict[str, Any]] = None
    seed: Optional[int] = None


class UsageWindowConfig(BaseModel):
    window_5h: int = 0
    window_1d: int = 0
    window_7d: int = 0


class ProviderKey(BaseModel):
    key: str
    label: str = "default"
    weight: int = 1
    enabled: bool = True
    quota_limit: int = 0
    quota_used: int = 0
    rate_limit_rps: float = 0.0
    expires_at: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)
    usage_window_limits: UsageWindowConfig = Field(default_factory=UsageWindowConfig)


class ModelRate(BaseModel):
    """Credit cost per 1M tokens for a specific model."""
    input: float = 0.0
    output: float = 0.0


class ProviderConfig(BaseModel):
    enabled: bool = True
    provider_type: str = "api"
    base_url: str = ""
    keys: list[ProviderKey] = Field(default_factory=list)
    rate_limit_cooldown: int = 60
    timeout: int = 120
    models: dict[str, list[str]] = Field(default_factory=lambda: {"include": [], "exclude": []})
    remote_models_cache: list[dict] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    cloaking: Any = None
    web_reverse: Any = None
    test_model: str = ""
    console_url: str = ""
    # Default rates for this provider
    cost_per_m_input: float = 0.0
    cost_per_m_output: float = 0.0
    # Fine-grained rates per model ID
    model_rates: Dict[str, ModelRate] = Field(default_factory=dict)
    retry: Any = Field(default_factory=dict)
    ignore: Any = Field(default_factory=dict)


class BillingConfig(BaseModel):
    enabled: bool = False
    enforce_balance: bool = True  # Block request if balance <= 0
    free_quota: float = 0.0       # Initial balance for new users


class AppConfig(BaseModel):
    server: Any = Field(default_factory=dict)
    billing: BillingConfig = Field(default_factory=BillingConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_routing: Any = Field(default_factory=dict)
    key_selection: Any = Field(default_factory=dict)
    tool_calling: Any = Field(default_factory=dict)
    logging: Any = Field(default_factory=dict)
    sync: Any = Field(default_factory=dict)
    sso: Any = Field(default_factory=dict)
