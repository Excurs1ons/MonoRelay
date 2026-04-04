# PrismaAPIRelay

A configurable LLM API relay server supporting **OpenRouter**, **NVIDIA NIM**, **OpenAI**, and **Anthropic**. Drop-in replacement for OpenAI and Anthropic API endpoints with smart routing, key rotation, and streaming support.

## Features

- **Multi-Provider Support**: OpenRouter, NVIDIA NIM, OpenAI, Anthropic
- **OpenAI Compatible**: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models`
- **Anthropic Compatible**: `/v1/messages` with full SSE streaming
- **Smart Model Routing**: Alias, prefix matching, auto-mapping, complexity-based routing
- **Key Rotation**: Round-robin, random, weighted selection with automatic cooldown on rate limits
- **Tool Calling Auto-Downgrade**: Automatically strips tools for models that don't support them (e.g. NVIDIA Llama)
- **Full Streaming**: Bidirectional SSE streaming for both OpenAI and Anthropic formats
- **Request Logging**: SQLite-based persistent request logging with cost estimation
- **Management API**: Real-time stats, logs, config management via REST API
- **Hot Config Reload**: Configuration changes are automatically detected and applied
- **Docker Ready**: Dockerfile and docker-compose for one-line deployment

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url> PrismaAPIRelay
cd PrismaAPIRelay
cp config.yml.example config.yml
# Edit config.yml with your API keys
```

### 2. Run

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python -m backend.main

# Or with custom config
python -m backend.main --config /path/to/config.yml --port 8787
```

### 3. Use

```bash
# OpenAI-compatible endpoint
curl http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'

# NVIDIA NIM endpoint
curl http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta/llama-4-maverick-17b-128e-instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Anthropic Messages endpoint
curl http://localhost:8787/v1/messages \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Docker

```bash
# Copy and edit config
cp config.yml.example config.yml

# Start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f
```

## Configuration

### Providers

```yaml
providers:
  openrouter:
    enabled: true
    base_url: "https://openrouter.ai/api/v1"
    keys:
      - key: "sk-or-v1-xxx"
        label: "main"
        weight: 1
    headers:
      HTTP-Referer: "https://your-site.com"
      X-Title: "Your App Name"
    rate_limit_cooldown: 60

  nvidia:
    enabled: true
    base_url: "https://integrate.api.nvidia.com/v1"
    keys:
      - key: "nvapi-xxx"
    rate_limit_cooldown: 30

  chatgpt_web:
    enabled: false
    provider_type: "web_reverse"
    keys:
      - key: "your-chatgpt-access-token"
        label: "main"
        weight: 1
    rate_limit_cooldown: 120
    web_reverse:
      pow_difficulty: "00003a"
      conversation_only: false
      history_disabled: true
      proxy_url: ""
      chatgpt_base_url: "https://chatgpt.com"
```

### Model Routing

```yaml
model_routing:
  enabled: true
  mode: "passthrough"  # passthrough | complexity | cascade

  # Aliases: use "fast" instead of full model name
  aliases:
    "fast": "openai/gpt-4o-mini"
    "smart": "anthropic/claude-sonnet-4-20250514"
    "nvidia-fast": "meta/llama-4-maverick-17b-128e-instruct"

  # Auto-mapping: gpt-4o -> openrouter, llama-* -> nvidia
  provider_mapping:
    "gpt-*": "openrouter"
    "claude-*": "openrouter"
    "llama-*": "nvidia"
    "meta/*": "nvidia"

  # Model overrides: silently redirect expensive models
  model_overrides:
    "gpt-4o": "openai/gpt-4o-mini"
```

### Key Selection

```yaml
key_selection:
  strategy: "round-robin"  # round-robin | random | weighted
```

### Tool Calling Auto-Downgrade

```yaml
tool_calling:
  auto_downgrade: true
  unsupported_models:
    - "meta/llama-4-maverick-*"
    - "meta/llama-3.1-*"
```

## API Endpoints

### Proxy Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | OpenAI chat completions (streaming supported) |
| POST | `/v1/completions` | OpenAI text completions (streaming supported) |
| POST | `/v1/embeddings` | OpenAI embeddings |
| GET | `/v1/models` | List all available models from all providers |
| POST | `/v1/messages` | Anthropic Messages API (streaming supported) |

### Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check with provider status |
| GET | `/api/stats` | Request statistics and key status |
| GET | `/api/logs` | Recent request logs |
| GET | `/api/config` | Current configuration |
| PUT | `/api/config` | Update configuration (hot reload) |
| GET | `/api/providers` | Provider status |
| POST | `/api/providers/{name}/test` | Test provider connection |
| GET | `/api/router` | Router configuration info |

### Authentication

All `/v1/*` and `/api/*` endpoints require authentication via Bearer token:

```
Authorization: Bearer your-access-key
```

The access key is configured in `config.yml` under `server.access_key`.

## Architecture

```
Client (any OpenAI/Anthropic SDK)
        |
        |  Authorization: Bearer <access_key>
        v
+--------------------------------------------------+
| PrismaAPIRelay (FastAPI)                          |
|--------------------------------------------------|
| 1. Auth middleware                                |
| 2. Model Router: resolve model -> provider        |
| 3. Key Manager: select API key (rotation/cooldown)|
| 4. Tool Calling: auto-strip if unsupported        |
| 5. Proxy: forward to upstream with streaming      |
| 6. Logger: record to SQLite                       |
+--------------------------------------------------+
        |
        v
   OpenRouter / NVIDIA NIM / OpenAI / Anthropic
```

## Project Structure

```
PrismaAPIRelay/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Config manager with hot-reload
│   ├── models.py               # Pydantic data models
│   ├── key_manager.py          # API key rotation & cooldown
│   ├── router.py               # Model routing engine
│   ├── logger.py               # SQLite request logging
│   ├── stats.py                # Cost estimation & stats
│   ├── proxy/
│   │   ├── streaming.py        # SSE streaming core
│   │   ├── openai_format.py    # OpenAI format handler
│   │   └── anthropic_format.py # Anthropic format handler
├── frontend/
│   └── index.html              # Dashboard UI
├── config.yml.example          # Configuration template
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── scripts/
│   ├── service_install.sh      # systemd install
│   └── service_uninstall.sh    # systemd uninstall
└── README.md
```

## License

MIT
