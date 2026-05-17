# MonoRelay: 大语言模型 API 中继服务器

MonoRelay 是一个可配置的大语言模型 (LLM) API 中继服务器，支持多种提供商（如 OpenRouter, NVIDIA NIM, OpenAI, Anthropic, DeepSeek, Groq 等），并全面兼容 OpenAI 和 Anthropic 的 API 接口标准。

## 项目概述

- **后端:** 基于 Python 3.11+ (推荐 3.12)，使用 **FastAPI** 框架和 **Uvicorn** 服务器。
- **前端:** 使用 **Vue 3** (Composition API)、**Vite** 构建工具、**Tailwind CSS** 样式框架和 **Pinia** 状态管理。
- **数据库:** 使用 **SQLite** 存储请求日志和身份认证信息；统计数据采用 JSON 格式存储。
- **配置:** 采用 **YAML** 格式 (`config.yml`)，支持配置文件热重载。
- **部署:** 支持 Docker 部署、Windows 单文件打包 (PyInstaller) 以及源码运行。

## 项目结构

- `backend/`: FastAPI 后端代码。
    - `main.py`: 项目入口、API 路由定义及中间件。
    - `config.py`: 配置管理逻辑，支持文件变更自动重载。
    - `models.py`: Pydantic 数据模型，定义配置结构和 API 格式。
    - `key_manager.py`: 提供商密钥管理、轮询调度及限速冷却逻辑。
    - `router.py`: 模型路由与别名映射引擎。
    - `logger.py`: 基于 SQLite 的请求日志记录器。
    - `proxy/`: OpenAI 与 Anthropic 格式双向转换处理器。
    - `web_reverse/`: ChatGPT 网页版反代逻辑实现。
- `frontend/`: Vue 3 管理面板前端代码。
    - `src/views/`: 包含仪表盘、提供商管理、日志查询、用户管理等页面。
    - `src/stores/`: Pinia 全局状态管理。
    - `src/api.js`: 基于 Axios 的后端 API 请求封装。
- `scripts/`: 项目构建、打包及服务安装脚本。
- `docs/`: 设计文档、开发经验记录等。

## 构建与运行

### 后端开发
1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务:
   ```bash
   python -m backend.main
   ```
   *注意: 默认端口为 8787。可以通过 `--port` 参数指定端口。*

### 前端开发
1. 进入前端目录:
   ```bash
   cd frontend
   npm install
   ```
2. 启动开发服务器:
   ```bash
   npm run dev
   ```
3. 构建生产环境文件:
   ```bash
   npm run build
   ```
   *构建后的文件存放在 `frontend/dist`，由后端负责静态托管。*

### 生产部署
- **Docker:**
  ```bash
  docker compose up -d
  ```
- **Windows 打包:**
  ```powershell
  .\scripts\build.ps1
  ```

## 开发约定

- **接口兼容性:** 所有中继端点必须严格遵循 OpenAI 或 Anthropic 的接口规范。
- **配置扩展:** 所有的配置项更新应同步修改 `backend/models.py` 中的 `AppConfig` 模型。
- **异步处理:** 所有 I/O 操作（如使用 `httpx` 发送 HTTP 请求、使用 `aiosqlite` 操作数据库）必须使用 `async/await`。
- **日志记录:** 请求日志持久化存储在 `data/requests.db` 中。开发时请调用 `request_logger` 记录交易详情。
- **身份认证:** 同时支持简易的 `access_key` 认证和基于 JWT 的 SSO 认证（GitHub/Google）。
- **多语言:** 前端通过 `vue-i18n` 支持中英文切换。

## 关键文件
- `config.yml`: 核心配置文件（参考 `config.yml.example` 进行创建）。
- `backend/main.py`: 后端逻辑核心及路由注册。
- `backend/models.py`: 配置对象及请求对象的结构定义。
- `frontend/src/api.js`: 前后端交互的统一点。
