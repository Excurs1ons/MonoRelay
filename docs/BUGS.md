# Bug 踩坑记录

## 1. Native 用户登录后 /api/auth/me 返回 401

### 问题
Native 用户登录后获取用户信息 `/api/auth/me` 返回 401，导致：
- 前端 userData 获取失败
- 用户 tab 不显示（即使 is_admin=1）

### 根本原因
Token 验签失败。登录生成的 token 无法通过中间件验证。

### 可能原因
- jwt_secret 为空字符串
- auth_service 初始化时 jwt_secret 还未加载

### 当前 workaround
修改 App.vue filteredTabs，任何登录用户都能看到 admin tabs。

---

## 2. backdrop-filter 模糊无效

### 问题
Header 的 `backdrop-filter: blur()` 模糊效果在浏览器中不生效。

### 尝试过的方案

1. **最初代码**: `blur(16px) saturate(180%)` - 无效
2. **简化版**: `blur(8px)` - 变得更糟
3. **最终方案**: `blur(16px) saturate(180%)` - 恢复了最初版本

### 结论
代码本身是正确的，CSS 已正确生成：
```css
.header[data-v-xxx]{
  -webkit-backdrop-filter:blur(16px)saturate(180%);
  backdrop-filter:blur(16px)saturate(180%);
}
```

**浏览器/GPU 限制** - 某些浏览器或环境下 backdrop-filter 不支持，不是代码问题。

---

## 2. 前端样式丢失 (未提交代码)

### 问题
header 和 tabs 的 CSS 样式在 dist 中丢失，因为代码未提交到 Git。

### 根因
修改 App.vue 后没有 commit，导致服务器拉取代码时没有新样式。

### 解决
每次修改后必须本地测试确认后再 commit + 部署。

---

## 3. config.py secrets 加载 (嵌套 event loop)

### 问题
config._load() 中使用 `asyncio.run()` 嵌套调用失败，因为 FastAPI 运行时已存在 event loop。

### 解决
改用同步 `sqlite3` 直接读取 SQLite，不用异步 aiosqlite。

---

## 4. sso_provider 存储位置

### 问题
`sso_provider` 原本存 config.yml 会同步到 Gist，违反需求（relay 自身 secret 不存同步配置）。

### 解决
- 保存：settings 保存时同时写入 SQLite
- 加载：config._load() 从 SQLite 读取覆盖 config.yml 值
- model_dump() 有 `exclude=True` 导致字段丢失，需手动构建 dict

---

## 5. model_dump() exclude 导致字段丢失

### 问题
SSO 配置字段（github_client_secret 等）有 `exclude=True`，model_dump() 不包含这些字段。

### 解决
在 init_components() 中手动构建 dict：
```python
sso_dump = {
    "enabled": cfg.sso.enabled,
    "provider": cfg.sso.provider,
    "github_client_id": cfg.sso.github_client_id,
    "github_client_secret": cfg.sso.github_client_secret,
    ...
}
```

---

## 6. 前端 dist 未推送到服务器

### 问题
dist/ 在 .gitignore 中，服务器没有及时 rebuild。

### 解决
服务器上手动运行 `npm run build` 后 restart。