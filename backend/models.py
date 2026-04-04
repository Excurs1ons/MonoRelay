from __future__ import annotations

from typing import Any, Optional
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


class AnthropicMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int
    messages: list[AnthropicMessage]
    system: Optional[str | list[dict[str, Any]]] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    stream: Optional[bool] = False
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[dict[str, Any]] = None


class ProviderKey(BaseModel):
    key: str
    label: str = "default"
    weight: int = 1
    enabled: bool = True


class WebReverseConfig(BaseModel):
    pow_difficulty: str = "00003a"
    conversation_only: bool = False
    enable_limit: bool = True
    history_disabled: bool = True
    proxy_url: str = ""
    turnstile_solver_url: str = ""
    ark0se_token_url: str = ""
    chatgpt_base_url: str = "https://chatgpt.com"
    model_mapping: dict[str, str] = Field(default_factory=lambda: {
        "gpt-3.5-turbo": "text-davinci-002-render-sha",
        "gpt-4": "gpt-4",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "o1-mini": "o1-mini",
        "o1": "o1",
        "o3-mini": "o3-mini",
    })


class ProviderConfig(BaseModel):
    enabled: bool = True
    provider_type: str = "api"
    base_url: str = ""
    keys: list[ProviderKey] = Field(default_factory=list)
    rate_limit_cooldown: int = 60
    timeout: int = 120
    models: dict[str, list[str]] = Field(default_factory=lambda: {"include": [], "exclude": []})
    headers: dict[str, str] = Field(default_factory=dict)
    web_reverse: Optional[WebReverseConfig] = None
    test_model: str = ""


class ComplexityConfig(BaseModel):
    enabled: bool = False
    simple: str = "openai/gpt-4o-mini"
    moderate: str = "openai/gpt-4o"
    complex: str = "anthropic/claude-sonnet-4-20250514"


class CascadeConfig(BaseModel):
    enabled: bool = False
    models: list[str] = Field(default_factory=list)
    max_retries: int = 2


class ModelRoutingConfig(BaseModel):
    enabled: bool = True
    mode: str = "passthrough"
    aliases: dict[str, str] = Field(default_factory=dict)
    provider_mapping: dict[str, str] = Field(default_factory=dict)
    model_overrides: dict[str, str] = Field(default_factory=dict)
    complexity: ComplexityConfig = Field(default_factory=ComplexityConfig)
    cascade: CascadeConfig = Field(default_factory=CascadeConfig)


class ToolCallingConfig(BaseModel):
    auto_downgrade: bool = True
    unsupported_models: list[str] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    enabled: bool = True
    db_path: str = "./data/requests.db"
    max_age_days: int = 30
    content_preview_length: int = 200


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8787
    access_key: str = "prisma-relay-change-me"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class KeySelectionConfig(BaseModel):
    strategy: str = "round-robin"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    key_selection: KeySelectionConfig = Field(default_factory=KeySelectionConfig)
    tool_calling: ToolCallingConfig = Field(default_factory=ToolCallingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
