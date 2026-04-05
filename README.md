# MonoRelay

可配置的大语言模型 API 中继服务器，支持 **OpenRouter**、**NVIDIA NIM**、**OpenAI**、**Anthropic**、**DeepSeek**、**Groq** 等多家提供商。完美兼容 OpenAI 和 Anthropic API 接口，支持智能模型路由、密钥轮换、流式输出和管理面板。

## 功能特性

- **多提供商支持**：OpenRouter、NVIDIA NIM、OpenAI、Anthropic、DeepSeek、Groq，以及网页反代（ChatGPT）
- **OpenAI 兼容接口**：`/v1/chat/completions`、`/v1/completions`、`/v1/embeddings`、`/v1/models`
- **Anthropic 兼容接口**：`/v1/messages`，完整支持 SSE 流式输出
- **模型路由**：精确匹配 → 子字符串匹配 → 首个启用提供商，支持按 provider 配置模型白/黑名单
- **密钥轮换**：轮询、随机、加权选择，自动限速冷却
- **工具调用自动降级**：自动移除不支持工具调用的模型的 tools 参数
- **完整流式输出**：OpenAI 和 Anthropic 格式双向 SSE 流
- **请求日志**：基于 SQLite 的持久化请求日志，含费用估算
- **管理面板**：实时统计、日志查询、提供商 CRUD、密钥管理、模型库配置
- **配置热重载**：配置文件变更自动检测并应用
- **Gist 配置同步**：通过 GitHub Gist 备份和恢复配置，支持多设备同步
- **深浅双主题**：SkillHub 深色 / ClawHub 浅色，一键切换
- **移动端适配**：完整响应式布局，支持手机竖屏操作
- **Docker 一键部署**：docker-compose 单命令启动
- **Windows 单文件运行**：下载即用，无需安装 Python

## 快速开始

### 方式一：Windows 可执行文件（推荐）

1. 前往 [Releases](https://github.com/Excurs1ons/MonoRelay/releases) 下载最新版本 `MonoRelay-Windows-x64.zip`
2. 解压到任意目录
3. 编辑 `config.yml`，填入你的 API 密钥
4. 双击 `启动.bat` 或直接运行 `MonoRelay.exe`
5. 浏览器打开 **http://localhost:8787**

### 方式二：Docker 部署

```bash
# 复制并编辑配置
cp config.yml.example config.yml

# 一键启动
docker compose up -d

# 查看日志
docker compose logs -f
```

### 方式三：源码运行

```bash
# 克隆仓库
git clone https://github.com/Excurs1ons/MonoRelay.git
cd MonoRelay

# 安装依赖
pip install -r requirements.txt

# 复制配置
cp config.yml.example config.yml

# 启动服务
python -m backend.main

# 或自定义配置
python -m backend.main --config /path/to/config.yml --port 8787
```

### 使用示例

```bash
# OpenAI 兼容接口
curl http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "你好！"}],
    "stream": true
  }'

# NVIDIA NIM 接口
curl http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta/llama-4-maverick-17b-128e-instruct",
    "messages": [{"role": "user", "content": "你好！"}]
  }'

# Anthropic Messages 接口
curl http://localhost:8787/v1/messages \
  -H "Authorization: Bearer prisma-relay-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "你好！"}]
  }'
```

## 配置说明

### 提供商配置

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
    test_model: "openai/gpt-4o-mini"  # 测试连接时使用的模型
    console_url: "https://openrouter.ai/workspaces"  # 管理控制台链接

  nvidia:
    enabled: true
    base_url: "https://integrate.api.nvidia.com/v1"
    keys:
      - key: "nvapi-xxx"
    rate_limit_cooldown: 30
    models:
      include:  # 模型白名单（留空表示不限制）
        - "meta/llama-3.1-8b-instruct"
        - "meta/llama-3.1-70b-instruct"
      exclude: []  # 模型黑名单

  chatgpt_web:
    enabled: false
    provider_type: "web_reverse"
    keys:
      - key: "your-chatgpt-access-token"
        label: "main"
    rate_limit_cooldown: 120
    web_reverse:
      pow_difficulty: "00003a"
      conversation_only: false
      history_disabled: true
      proxy_url: ""
      chatgpt_base_url: "https://chatgpt.com"
```

### 模型路由

```yaml
model_routing:
  enabled: true
  mode: "passthrough"  # passthrough | complexity | cascade

  # 别名：使用简短名称代替完整模型名
  aliases:
    "fast": "openai/gpt-4o-mini"
    "smart": "anthropic/claude-sonnet-4-20250514"

  # 自动映射：根据模型名自动匹配提供商
  provider_mapping:
    "gpt-*": "openrouter"
    "claude-*": "openrouter"
    "llama-*": "nvidia"
    "meta/*": "nvidia"
```

### 密钥选择策略

```yaml
key_selection:
  strategy: "round-robin"  # round-robin（轮询）| random（随机）| weighted（加权）
```

### 工具调用自动降级

```yaml
tool_calling:
  auto_downgrade: true
  unsupported_models:
    - "meta/llama-4-maverick-*"
    - "meta/llama-3.1-*"
```

### 服务器设置

```yaml
server:
  host: "0.0.0.0"
  port: 8787
  access_key: "prisma-relay-change-me"  # 访问密钥，请修改
  log_level: "INFO"
```

## 管理面板

启动服务后访问 **http://localhost:8787** 打开管理面板，功能包括：

| 功能 | 说明 |
|------|------|
| **概览** | 实时统计：请求数、错误率、Token 消耗、预估费用、首字延迟、输出速度 |
| **提供商管理** | 添加/编辑/删除提供商，测试连接，配置模型白/黑名单 |
| **密钥管理** | 为每个提供商添加多个 API 密钥，支持启用/禁用 |
| **模型库** | 从上游 API 获取可用模型列表，勾选启用 |
| **请求日志** | 查看最近的请求详情，包括模型、提供商、状态、延迟 |
| **配置同步** | 通过 GitHub Gist 备份和恢复配置 |
| **配置文件** | 在线编辑 config.yml，保存后自动热重载 |

### 数据统计

- **总请求数 / 错误率**：累计请求统计
- **Token 消耗**：输入/输出 Token 总数
- **预估费用**：根据模型单价估算（支持在提供商配置中自定义 `cost_per_m_input` 和 `cost_per_m_output`）
- **模型详细统计**：每个模型的平均首字延迟、输出速度（tokens/s）、流式请求数

### 配置同步

通过 GitHub Gist 实现配置备份与恢复：

1. 前往 [GitHub Token 设置](https://github.com/settings/tokens) 创建 Fine-grained PAT
2. 权限勾选 **Gist → Read and write**
3. 在管理面板「同步」标签页输入 Token
4. 系统自动查找已有 Gist 或创建新的
5. 支持推送、拉取、禁用同步

> Token 存储在本地 `data/sync.json`，不会写入 config.yml 或提交到 Git。

## API 接口

### 代理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | OpenAI 聊天补全（支持流式） |
| POST | `/v1/completions` | OpenAI 文本补全（支持流式） |
| POST | `/v1/embeddings` | OpenAI 嵌入向量 |
| GET | `/v1/models` | 列出所有可用模型 |
| POST | `/v1/messages` | Anthropic 消息接口（支持流式） |

### 管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/stats` | 统计数据 |
| GET | `/api/logs` | 最近请求日志 |
| GET | `/api/config` | 当前配置 |
| PUT | `/api/config` | 更新配置（热重载） |
| GET | `/api/providers` | 提供商列表 |
| POST | `/api/providers/{name}/test` | 测试提供商连接 |
| GET | `/api/sync` | 同步状态 |
| POST | `/api/sync/setup` | 配置同步 |
| POST | `/api/sync/push` | 推送到 Gist |
| POST | `/api/sync/pull` | 从 Gist 拉取 |

### 认证

所有 `/v1/*` 和 `/api/*` 接口需要 Bearer Token 认证：

```
Authorization: Bearer your-access-key
```

访问密钥在 `config.yml` 的 `server.access_key` 中配置。

## 项目结构

```
MonoRelay/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理（热重载）
│   ├── models.py               # Pydantic 数据模型
│   ├── key_manager.py          # API 密钥轮换与冷却
│   ├── router.py               # 模型路由引擎
│   ├── logger.py               # SQLite 请求日志
│   ├── stats.py                # 统计与费用估算
│   ├── sync.py                 # Gist 同步
│   ├── sync_storage.py         # 同步凭证本地存储
│   ├── proxy/
│   │   ├── streaming.py        # SSE 流式核心
│   │   ├── openai_format.py    # OpenAI 格式处理
│   │   └── anthropic_format.py # Anthropic 格式处理
│   └── web_reverse/            # 网页反代模块
├── frontend/
│   └── index.html              # 管理面板（单文件）
├── data/                       # 运行时数据（已 gitignore）
│   ├── requests.db             # 请求日志
│   ├── stats.json              # 统计数据
│   └── sync.json               # 同步凭证
├── config.yml.example          # 配置模板
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── MonoRelay.spec         # PyInstaller 打包配置
├── scripts/
│   ├── build.ps1               # Windows 打包脚本
│   ├── build.sh                # Linux 打包脚本
│   ├── service_install.sh      # systemd 安装
│   └── service_uninstall.sh    # systemd 卸载
└── .github/workflows/
    └── release.yml             # 自动发布 Workflow
```

## 打包发布

### 本地打包

```bash
# Windows
.\scripts\build.ps1

# Linux/macOS
bash scripts/build.sh
```

打包产物为单个可执行文件，config.yml 和 data/ 目录保留在运行时目录。

### 自动发布

推送 `v*.*.*` 格式的 tag 即可触发 GitHub Workflow 自动构建和发布：

```bash
git tag -a v0.0.1 -m "Release v0.0.1"
git push origin --tags
```

## 许可证

MIT
