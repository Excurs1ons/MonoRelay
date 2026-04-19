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


class UsageWindowConfig(BaseModel):
    """Time-based usage window limits for rate limiting."""
    window_5h: int = 0  # 0 = unlimited, max requests in 5 hours
    window_1d: int = 0  # 0 = unlimited, max requests in 1 day
    window_7d: int = 0  # 0 = unlimited, max requests in 7 days


class ProviderKey(BaseModel):
    key: str
    label: str = "default"
    weight: int = 1
    enabled: bool = True
    quota_limit: int = 0  # 0 = unlimited, max requests/keys
    quota_used: int = 0
    rate_limit_rps: float = 0.0  # 0 = unlimited, requests per second
    expires_at: str = ""  # ISO 8601 datetime, empty = no expiry
    metadata: dict[str, str] = Field(default_factory=dict)
    usage_window_limits: UsageWindowConfig = Field(default_factory=UsageWindowConfig)


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


class RequestCloakingConfig(BaseModel):
    """Request cloaking options for enhanced privacy/anonymity."""
    user_agent: str = ""  # Custom User-Agent header
    referer: str = ""  # Custom Referer header
    origin: str = ""  # Custom Origin header
    accept: str = ""  # Custom Accept header
    accept_language: str = ""  # Custom Accept-Language header
    # TLS fingerprint options (these are hints for clients)
    tls_fingerprint_profile: str = ""  # Profile name for TLS fingerprinting


class ProviderConfig(BaseModel):
    enabled: bool = True
    provider_type: str = "api"
    base_url: str = ""
    keys: list[ProviderKey] = Field(default_factory=list)
    rate_limit_cooldown: int = 60
    timeout: int = 120
    models: dict[str, list[str]] = Field(default_factory=lambda: {"include": [], "exclude": []})
    remote_models_cache: list[dict] = Field(default_factory=list)  # 缓存的远程模型列表
    headers: dict[str, str] = Field(default_factory=dict)
    cloaking: RequestCloakingConfig = Field(default_factory=RequestCloakingConfig)
    web_reverse: Optional[WebReverseConfig] = None
    test_model: str = ""
    console_url: str = ""
    cost_per_m_input: float = 0.0
    cost_per_m_output: float = 0.0


class ComplexityConfig(BaseModel):
    enabled: bool = False
    simple: str = "openai/gpt-4o-mini"
    moderate: str = "openai/gpt-4o"
    complex: str = "anthropic/claude-sonnet-4-20250514"


class CascadeConfig(BaseModel):
    enabled: bool = False
    models: list[str] = Field(default_factory=list)
    max_retries: int = 2


class TransformationRule(BaseModel):
    """Rule for transforming request payloads based on model patterns."""
    models: list[str] = Field(default_factory=list)  # fnmatch patterns
    inject_params: dict[str, Any] = Field(default_factory=dict)  # params to add
    override_params: dict[str, Any] = Field(default_factory=dict)  # params to override


class PayloadTransformation(BaseModel):
    """Configuration for request payload transformation."""
    enabled: bool = False
    rules: list[TransformationRule] = Field(default_factory=list)


class ModelRoutingConfig(BaseModel):
    enabled: bool = True
    mode: str = "passthrough"
    aliases: dict[str, str] = Field(default_factory=dict)
    provider_mapping: dict[str, str] = Field(default_factory=dict)
    model_overrides: dict[str, str] = Field(default_factory=dict)
    complexity: ComplexityConfig = Field(default_factory=ComplexityConfig)
    cascade: CascadeConfig = Field(default_factory=CascadeConfig)
    payload_transformation: PayloadTransformation = Field(default_factory=PayloadTransformation)


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
    access_key_enabled: bool = True
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    public_host: str = ""
    turnstile_enabled: bool = False
    turnstile_site_key: str = ""

    jwt_secret: str = Field(default="", exclude=True)
    turnstile_secret_key: str = Field(default="", exclude=True)


class KeySelectionConfig(BaseModel):
    strategy: str = "round-robin"


class SyncConfig(BaseModel):
    enabled: bool = False
    gist_id: str = ""
    gist_id_stats: str = ""


class SSOConfig(BaseModel):
    enabled: bool = False
    provider: str = "github"
    prismaauth_url: str = "http://localhost:8080"
    client_id: str = ""
    scopes: list[str] = ["openid", "profile", "email"]
    github_client_id: str = ""
    google_client_id: str = ""
    local_sso_enabled: bool = False
    sso_only: bool = False
    admin_usernames: list[str] = Field(default_factory=list)

    client_secret: str = Field(default="", exclude=True)
    github_client_secret: str = Field(default="", exclude=True)
    google_client_secret: str = Field(default="", exclude=True)
    local_sso_secret: str = Field(default="", exclude=True)


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    key_selection: KeySelectionConfig = Field(default_factory=KeySelectionConfig)
    tool_calling: ToolCallingConfig = Field(default_factory=ToolCallingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    sso: SSOConfig = Field(default_factory=SSOConfig)
