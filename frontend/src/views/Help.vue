<template>
  <div class="help-page">
    <h2 class="section-title">MonoRelay 使用指南</h2>

    <div class="help-content">
      <div class="help-section" v-for="section in sections" :key="section.id" :id="section.id">
        <h3 class="help-section-title">{{ section.title }}</h3>
        <div class="help-section-content" v-html="section.content"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
const sections = [
  {
    id: 'intro',
    title: '1. 简介',
    content: `
      <p>MonoRelay 是一个统一的 LLM API 代理服务，支持同时连接多个 LLM 提供商（如 OpenAI、Anthropic、Groq、NVIDIA、OpenRouter 等），通过单一的 OpenAI 兼容接口对外提供服务。</p>
      <p><strong>核心功能：</strong></p>
      <ul>
        <li><strong>多提供商统一管理</strong> - 一个入口访问所有模型，支持权重、额度与速率限制。</li>
        <li><strong>自动路由与别名</strong> - 根据模型名称自动选择提供商，支持通过别名（如 balanced, fast）调用。</li>
        <li><strong>多用户与 SSO</strong> - 支持本地账号及 GitHub OAuth 登录，拥有完善的权限控制。</li>
        <li><strong>请求日志审计</strong> - 完整记录每次请求的参数、内容、耗时、首字延迟及 Token 消耗。</li>
        <li><strong>智能同步</strong> - 基于 GitHub Gist 的配置同步，完美保留注释，支持版本管理。</li>
      </ul>
    `
  },
  {
    id: 'auth',
    title: '2. 身份验证与权限',
    content: `
      <p><strong>登录方式</strong></p>
      <ul>
        <li><strong>本地账号</strong>: 首次启动时注册的第一个用户自动成为管理员。</li>
        <li><strong>GitHub SSO</strong>: 在“设置”或配置文件中配置 GitHub OAuth 凭据后，可使用 GitHub 一键登录。</li>
      </ul>
      
      <p><strong>管理员配置</strong></p>
      <p>在配置文件 <code>config.yml</code> 或“设置”页面中的 <code>admin_usernames</code> 列表中添加 GitHub 用户名，该用户登录后将自动获得管理员权限。</p>
      
      <p><strong>权限说明</strong></p>
      <ul>
        <li><strong>普通用户</strong>: 可查看仪表盘、使用 API、修改个人密码。</li>
        <li><strong>管理员</strong>: 拥有完整权限，包括管理 Provider、查看日志、管理用户、修改系统设置等。</li>
      </ul>
    `
  },
  {
    id: 'api-usage',
    title: '3. API 使用',
    content: `
      <p>MonoRelay 提供完全兼容 OpenAI 的 API 接口。</p>
      
      <p><strong>基础调用</strong></p>
      <pre class="code-block">curl -X POST http://localhost:8787/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_ACCESS_KEY" \\
  -d '{
    "model": "gpt-4o@openai",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'</pre>
      
      <p><strong>访问密钥 (Access Key)</strong></p>
      <p>在 <strong>Settings</strong> 页面设置 <code>Access Key</code>。这是用于 API 鉴权的 Bearer Token，与登录 UI 的账号密码无关。</p>
      
      <p><strong>模型 ID 格式</strong></p>
      <p>使用 <code>模型名@提供商名</code> 格式显式指定，或直接使用模型名（依赖路由规则）：</p>
      <ul>
        <li><code>gpt-4o@openai</code> - 指定使用 OpenAI 的 GPT-4o</li>
        <li><code>claude-3-5-sonnet@openrouter</code> - 使用 OpenRouter 提供的 Claude</li>
        <li><code>balanced</code> - 路由别名，指向预配置的具体模型</li>
      </ul>
    `
  },
  {
    id: 'sync',
    title: '4. 配置同步 (Gist)',
    content: `
      <p><strong>特性</strong></p>
      <ul>
        <li><strong>保留注释</strong>: 与旧版不同，现在的同步系统直接操作原始 YAML，你的所有手动注释都会被保留。</li>
        <li><strong>版本化</strong>: 系统会记录每次同步的版本号，支持检测本地是否已是最新。</li>
        <li><strong>强制覆盖</strong>: 如果本地配置损坏或想彻底同步 Gist，可使用“强制拉取覆盖”按钮。</li>
      </ul>
      
      <p><strong>设置步骤</strong></p>
      <ol>
        <li>在 GitHub 创建一个 <strong>Fine-grained Personal Access Token</strong>，并勾选 <strong>Gists (Read & Write)</strong> 权限。</li>
        <li>在 Config 或 Settings 页面填入 Token。</li>
        <li>点击 <strong>Push</strong> 将当前配置备份到云端。</li>
      </ol>
    `
  },
  {
    id: 'global-settings',
    title: '5. 系统设置',
    content: `
      <p><strong>全局设置页面提供以下功能：</strong></p>
      <ul>
        <li><strong>公网 Host</strong>: 设置后，页面上显示的测试 curl 脚本将自动使用该域名。</li>
        <li><strong>工具降级</strong>: 开启后，系统会自动为不支持 Tool Calling 的模型进行兼容转换。</li>
        <li><strong>日志清理</strong>: 可配置请求日志的保留天数，系统将自动定期清理过期数据。</li>
        <li><strong>强制 SSO</strong>: 开启后将隐藏本地登录入口，仅允许 OAuth 登录。</li>
      </ul>
    `
  },
  {
    id: 'troubleshooting',
    title: '6. 常见问题',
    content: `
      <p><strong>Q: 修改了 config.yml 但页面没变化？</strong></p>
      <p>A: 系统支持热重载，但如果通过外部编辑器修改，可能需要几秒钟同步。建议直接在 <strong>Config</strong> 页面编辑并保存。</p>
      
      <p><strong>Q: GitHub 登录成功后是普通用户？</strong></p>
      <p>A: 请检查 <code>admin_usernames</code> 中是否正确填入了你的 GitHub 用户名（注意大小写）。</p>
      
      <p><strong>Q: 页面显示旧版样式？</strong></p>
      <p>A: 请使用 <code>Ctrl + F5</code> 强制刷新。我们在后端增加了 build-id 注入逻辑，通常刷新一次即可看到最新版。</p>
      
      <p><strong>Q: 如何找回 Access Key？</strong></p>
      <p>A: 管理员进入 <strong>Settings</strong> 页面，点击 Access Key 旁边的眼睛图标即可查看。</p>
    `
  }
]
</script>

<style scoped>
.help-page {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 24px;
}

.help-content {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.help-section {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  padding: 24px;
}

.help-section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--color-accent);
}

.help-section-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text);
}

.help-section-content p {
  margin-bottom: 14px;
}

.help-section-content ul,
.help-section-content ol {
  margin: 12px 0;
  padding-left: 20px;
}

.help-section-content li {
  margin-bottom: 8px;
}

.code-block {
  background: var(--color-bg-input);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 14px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 14px 0;
  line-height: 1.5;
}

.help-section-content a {
  color: var(--color-accent);
  text-decoration: none;
}

.help-section-content a:hover {
  text-decoration: underline;
}

.help-section-content strong {
  font-weight: 600;
  color: var(--color-accent);
}
</style>
