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
- 安全存储多个 API Key，支持权重、额度、速率限制配置
- 支持密钥轮询与自动降级

### 4. 请求日志与监控
- 完整记录每次请求的详细信息（耗时、首字延迟、Token 数量、请求参数）
- 仪表盘实时统计模型请求排行榜与错误率

### 5. 多用户与权限
- 支持本地账号系统与 **GitHub OAuth SSO** 登录
- 完善的用户管理：启用/禁用、权限切换、删除用户
- 管理员白名单配置（基于 SSO 用户名）

### 6. 配置同步
- 基于 **GitHub Gist** 的配置同步，支持原始 YAML 文本（保留注释）
- 版本化管理，支持增量对比与强制覆盖

---

## 近期更新

### 认证与安全
- [x] 完整实现 GitHub SSO 登录流程
- [x] 增加 **admin_usernames** 白名单，自动映射 SSO 用户为管理员
- [x] 增加用户管理页面（Users），支持管理员增删改查
- [x] 支持用户修改个人密码
- [x] 移除 401 响应的 WWW-Authenticate 头部，防止浏览器弹出原生登录框

### 全局设置
- [x] 新增 **Settings** 页面，图形化管理服务器核心参数
- [x] 支持设置公网 Host、端口、访问密钥、日志保留天数等
- [x] 支持配置密钥选择策略和工具调用降级

### 同步系统
- [x] 同步逻辑重构为“原始文本”模式，**完美保留 config.yml 中的注释和格式**
- [x] 引入版本号（Commit Hash）对比，支持检测“本地已是最新”
- [x] 增加“强制拉取覆盖”功能
- [x] 同步界面显示 Gist 创建/更新时间以及友好的人性化时间差（如：2小时前）

### UI/UX 优化
- [x] 页面重构：Help 移至 About 页面入口，侧边栏新增“设置”与“账户”
- [x] 文本框增加字符数与行数统计
- [x] 增强用户组视觉区分（精美紫色渐变 Admin 标签）
- [x] 后端 `index.html` 注入动态 build-id 强制刷新浏览器缓存

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

---

## 页面功能映射

| 页面 | 权限 | 功能说明 |
|------|------|------|
| **Dashboard** | 所有用户 | 总览统计、模型使用排行榜、快速状态检查 |
| **Providers** | 管理员 | 添加/编辑/测试/删除提供商及其 API Key |
| **Keys** | 管理员 | 集中管理所有提供商的密钥状态 |
| **Models** | 管理员 | 远程模型获取、本地模型别名与白名单管理 |
| **Logs** | 管理员 | 完整请求审计、详情展开、参数查看 |
| **Settings** | 管理员 | **(New)** 服务器核心配置、鉴权设置、策略配置 |
| **Users** | 管理员 | **(New)** 用户列表、权限切换、账户状态控制 |
| **Config** | 管理员 | YAML 源码编辑、Gist 备份与恢复 |
| **Account** | 所有用户 | **(New)** 个人资料查看、密码修改 |
| **Help** | 所有用户 | 完整使用指南与 API 参考 |

---

## 配置说明 (config.yml)

```yaml
server:
  port: 8787
  access_key: "your-access-key" # 用于 API 调用
  public_host: "relay.example.com" # 可选，对外展示地址

sso:
  enabled: true
  provider: "github"
  github_client_id: "..."
  github_client_secret: "..."
  admin_usernames: ["YourGitHubUser"] # 指定管理员
```

默认端口: **8787**
默认访问路径: `http://localhost:8787`
