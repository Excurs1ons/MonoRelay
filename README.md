# MonoRelay

[![Build & Release](https://github.com/Excurs1ons/MonoRelay/actions/workflows/release.yml/badge.svg)](https://github.com/Excurs1ons/MonoRelay/actions/workflows/release.yml)

可配置的大语言模型 API 中继服务器，支持 OpenRouter、NVIDIA NIM、OpenAI、Anthropic、DeepSeek、Groq 等提供商。兼容 OpenAI 和 Anthropic API 接口。

## 功能特性

- **多提供商支持**：API 接入 + 网页反代（ChatGPT）
- **智能路由**：模型别名、自动映射、工具调用降级
- **密钥管理**：轮询/随机/加权选择，限速冷却
- **完整流式输出**：OpenAI / Anthropic 格式双向 SSE
- **管理面板**：Vue 3 SPA，支持中英文 i18n、移动端适配、浅色/深色主题
- **用户管理**：支持 OAuth SSO（GitHub/Google）和本地账号，超级管理员权限
- **请求日志**：SQLite 持久化，支持完整请求/响应内容查看、错误详情
- **Gist 同步**：GitHub Gist 备份配置，多设备同步
- **Docker / Windows 单文件 / 源码** 三种部署方式

## 环境要求

- **Python 3.11+**（推荐 Python 3.12）

> ⚠️ Python 3.10 及以下版本可能因依赖包不兼容而无法运行。

## 快速开始

### Windows 可执行文件

1. 前往 [Releases](https://github.com/Excurs1ons/MonoRelay/releases) 下载 `MonoRelay-Windows-x64.zip`
2. 解压，编辑 `config.yml` 填入 API 密钥
3. 双击 `启动.bat`，浏览器打开 **http://localhost:8787**

### Docker

```bash
cp config.yml.example config.yml
docker compose up -d
```

### 源码

```bash
git clone https://github.com/Excurs1ons/MonoRelay.git
cd MonoRelay
pip install -r requirements.txt
cp config.yml.example config.yml
python -m backend.main
```

## 配置

编辑 `config.yml`，核心配置项：

```yaml
server:
  host: "0.0.0.0"
  port: 8787
  access_key: "your-secret-key"  # 请修改
  public_host: "https://your-domain.com"  # 公网访问地址（可选）

sso:
  enabled: true
  provider: "github"  # github, google, prismaauth
  github_client_id: "your-github-client-id"
  github_client_secret: "your-github-client-secret"
  google_client_id: "your-google-client-id"
  google_client_secret: "your-google-client-secret"

providers:
  openrouter:
    enabled: true
    base_url: "https://openrouter.ai/api/v1"
    keys:
      - key: "sk-or-v1-xxx"
        label: "main"
    headers:
      HTTP-Referer: "https://your-site.com"
      X-Title: "Your App"

  chatgpt_web:
    enabled: false
    provider_type: "web_reverse"
    keys:
      - key: "your-chatgpt-access-token"
    web_reverse:
      pow_difficulty: "00003a"
      conversation_only: false
```

完整配置模板见 [config.yml.example](config.yml.example)。

## 管理面板

启动后访问 **http://localhost:8787**，输入 `access_key` 登录。

| 模块 | 说明 |
|------|------|
| 仪表盘 | 请求数、错误率、Token 消耗、模型统计、API 地址 |
| 提供商 | 添加/编辑/测试提供商，配置模型白名单 |
| 请求日志 | SQLite 持久化的请求详情，支持完整内容查看和错误分析 |
| 用户管理 | 管理用户账号、权限、超级管理员设置 |
| 设置 | 系统设置、SSO 配置、数据清空、主题切换 |
| 配置同步 | GitHub Gist 备份与恢复 |
| 配置文件 | 在线编辑 config.yml，保存后热重载 |

### 主题切换

管理面板支持浅色/深色主题切换，点击右上角主题按钮即可切换。

### SSO 登录

支持 GitHub、Google OAuth 登录，在设置页面配置 SSO 后即可使用。

### 日志详情

请求日志支持查看完整的请求和响应内容，错误日志默认展开显示。

## API 文档

FastAPI 自动生成 Swagger 文档，启动后访问 **http://localhost:8787/docs** 查看完整接口列表和在线测试。

## 项目结构

```
MonoRelay/
├── backend/              # FastAPI 后端
│   ├── main.py           # 入口、路由、认证
│   ├── config.py         # 配置管理（热重载）
│   ├── models.py         # Pydantic 数据模型
│   ├── key_manager.py    # 密钥轮换与冷却
│   ├── router.py         # 模型路由引擎
│   ├── logger.py         # SQLite 请求日志
│   ├── stats.py          # 统计与费用估算
│   ├── sync.py           # Gist 同步
│   ├── secrets.py        # 敏感信息管理（SQLite）
│   ├── auth.py           # 用户认证和授权
│   ├── proxy/            # OpenAI / Anthropic 格式处理
│   └── web_reverse/      # ChatGPT 网页反代
├── frontend/             # Vue 3 管理面板
│   ├── src/
│   │   ├── views/        # 页面组件
│   │   ├── components/   # 公共组件
│   │   ├── stores/       # 状态管理
│   │   └── api.js        # API 调用
├── data/                 # 运行时数据（已 gitignore）
├── docs/                 # 文档
│   └── LESSONS_LEARNED.md # 开发经验教训
├── config.yml.example    # 配置模板
└── .github/workflows/    # 自动构建发布
```

## 打包

推送 `v*.*.*` 格式的 tag 即可触发 GitHub Workflow 自动构建 Windows 可执行文件并发布 Release：

```bash
git tag -a v0.0.3 -m "Release v0.0.3"
git push origin --tags
```

也可本地打包：

```bash
bash scripts/build.sh      # Linux/macOS
.\scripts\build.ps1        # Windows
```

## 常见问题

### 如何配置公网访问？

在 `config.yml` 中设置 `public_host`：

```yaml
server:
  public_host: "https://your-domain.com"
```

系统会自动生成正确的 API 地址。

### 如何启用 SSO 登录？

在设置页面配置 SSO provider 和密钥，或直接编辑 `config.yml`：

```yaml
sso:
  enabled: true
  provider: "github"
  github_client_id: "your-client-id"
  github_client_secret: "your-client-secret"
```

### 如何查看完整的请求和响应内容？

在请求日志页面，点击日志条目展开查看。错误日志默认显示完整内容，普通日志可按需查看。

### 如何清空统计数据和日志？

在设置页面或仪表盘页面点击"清空"按钮即可。

### 如何切换主题？

点击右上角的主题按钮（太阳/月亮图标）即可切换浅色/深色主题。

## 许可证

MIT
