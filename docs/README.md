# MonoRelay 功能文档

## 项目简介

MonoRelay 是一个统一的 LLM API 代理服务，支持同时连接多个 LLM 提供商，通过单一的 OpenAI 兼容接口对外提供服务。

**在线文档**: 访问 `/help` 页面查看完整使用教程

---

## 核心功能

### 1. 多提供商统一管理
- 支持 OpenAI、Anthropic、Groq、NVIDIA NIM、OpenRouter、DeepSeek、OpenCode Zen 等
- 一个入口访问所有模型

### 2. 自动路由
- 模型 ID 格式：`模型名@提供商名`（如 `gpt-4o@openai`）
- 根据模型名称自动选择提供商

### 3. 密钥管理
- 安全存储多个 API Key
- 支持权重配置

### 4. 请求日志
- 完整记录每次请求的详细信息
- 包含：耗时、首字延迟、Token 数量、请求参数、请求/响应内容

### 5. 配置同步
- 支持 GitHub Gist 同步配置

---

## 近期更新

### UI/视觉
- [x] 按 ociturner 设计文档重制视觉表现
- [x] 磨砂玻璃效果和 gradient 背景
- [x] 添加 grain 纹理

### Provider 管理
- [x] 测试弹窗支持批量测试
- [x] API Key 编辑窗口显示已存储密钥数量
- [x] 测试模型下拉框从已启用模型列表选择

### 模型管理
- [x] 模型列表缓存到本地配置（持久化）
- [x] 切换 provider 时自动加载缓存
- [x] 每个模型 ID 添加 provider 后缀（便于下游区分）

### API 变更
- [x] `/v1/models` 和 `/api/providers/{name}/models/remote` 改为公开 API
- [x] 请求处理时解析 provider 后缀映射回原 ID

### 请求日志
- [x] 添加首字延迟（first_token_ms）
- [x] 记录完整请求/响应内容（纯文本，非 JSON）
- [x] 记录请求参数（temperature, top_p, presence_penalty, frequency_penalty, max_tokens）
- [x] 日志条目支持展开查看详情
- [x] 耗时/首字延迟 >= 1000ms 时自动转为秒显示

### 密钥管理
- [x] 添加 Keys 页面入口
- [x] 删除密钥时提示无法删除最后一个密钥
- [x] Keys 页面改用全局 Toast 提示

### 其他
- [x] GitHub Token 输入框添加小眼睛显示/隐藏明文
- [x] 添加使用指南页面（/help）

---

## API 使用

### 基础调用

```bash
curl -X POST http://localhost:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_KEY" \
  -d '{
    "model": "gpt-4o@openai",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 获取模型列表

```bash
curl http://localhost:8787/v1/models
```

### 模型 ID 格式

| 示例 | 说明 |
|------|------|
| `gpt-4o@openai` | OpenAI GPT-4o |
| `claude-sonnet-4@anthropic` | Anthropic Claude Sonnet 4 |
| `llama-3.1-8b-instant@groq` | Groq Llama |
| `z-ai/glm4.7@nvidia` | NVIDIA NIM GLM |
| `minimax-m2.5-free@opencode` | OpenCode Zen 免费模型 |

---

## 免费模型推荐

### Groq
- **官网**: groq.com
- **Base URL**: `https://api.groq.com/openai/v1`
- **免费模型**: llama-3.1-8b-instant, gemma2-9b-it

### OpenRouter
- **官网**: openrouter.ai
- **Base URL**: `https://openrouter.ai/api/v1`
- **免费模型**: 多种免费模型可选

### NVIDIA NIM
- **官网**: build.nvidia.com
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **免费模型**: llama-3.1-8b-instant, nemotron-4-340b

### OpenCode Zen
- **官网**: opencode.ai/zen
- **Base URL**: `https://opencode.ai/zen/v1`
- **免费模型**:
  - `big-pickle` - OpenCode 独家，完全免费
  - `minimax-m2.5-free`
  - `trinity-large-preview-free`
  - `nemotron-3-super-free`
  - `kimi-k2.5-free`, `glm-4.7-free` 等

---

## 本地部署

```bash
# 启动服务
./start.sh

# 或使用 Python
python3 start.py --bg

# 重启
python3 start.py --restart

# 停止
python3 start.py --stop
```

默认端口: **8787**

---

## 配置说明

配置文件位于 `config.yml`，主要配置项：

- `server.access_key`: API 访问密钥
- `server.jwt_secret`: JWT 密钥
- `providers`: 各提供商配置
- `model_routing`: 模型路由规则

---

## 页面功能

| 页面 | 功能 |
|------|------|
| Dashboard | 总览统计、模型排行榜 |
| Providers | 添加/编辑提供商、测试连接 |
| Keys | 密钥管理 |
| Models | 模型列表管理、批量启用 |
| Logs | 请求日志、详情查看 |
| Analytics | 数据分析 |
| Config | 系统配置、GitHub 同步 |
| Help | 使用指南 |

---

## 更新日志

### vRecent
- 添加使用指南页面
- 请求日志显示参数详情
- 时间显示优化（自动转换秒）
- Token 明文显示小眼睛
- 模型列表不再添加 @provider 后缀（便于测试）
- /v1/models 和远程模型列表保持 @provider 后缀（便于下游区分）