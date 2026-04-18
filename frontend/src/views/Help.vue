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
        <li>多提供商统一管理 - 一个入口访问所有模型</li>
        <li>自动路由 - 根据模型名称自动选择提供商</li>
        <li>密钥管理 - 安全存储多个 API Key</li>
        <li>请求日志 - 完整记录每次请求的详细信息</li>
        <li>配置同步 - 支持 GitHub Gist 同步配置</li>
      </ul>
    `
  },
  {
    id: 'quickstart',
    title: '2. 快速开始',
    content: `
      <p><strong>步骤 1：启动服务</strong></p>
      <pre class="code-block"># Linux/macOS
./start.sh

# 或使用 Python
python3 start.py --bg</pre>
      
      <p>服务启动后访问 <code>http://localhost:8787</code></p>
      
      <p><strong>步骤 2：添加 Provider</strong></p>
      <ol>
        <li>进入 <strong>Providers</strong> 页面</li>
        <li>点击 <strong>Add Provider</strong> 按钮</li>
        <li>填写配置信息：
          <ul>
            <li><code>Name</code>: 提供商名称（如 openai, anthropic, groq）</li>
            <li><code>Base URL</code>: API 端点 URL</li>
            <li><code>API Key</code>: 提供商的 API 密钥</li>
          </ul>
        </li>
        <li>点击保存</li>
      </ol>
      
      <p><strong>步骤 3：添加模型</strong></p>
      <ol>
        <li>进入 <strong>Models</strong> 页面</li>
        <li>选择要启用的 Provider</li>
        <li>点击 <strong>Fetch Remote Models</strong> 获取可用模型</li>
        <li>勾选要启用的模型</li>
        <li>点击保存</li>
      </ol>
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
      
      <p><strong>获取模型列表</strong></p>
      <pre class="code-block">curl http://localhost:8787/v1/models</pre>
      
      <p><strong>访问密钥</strong></p>
      <p>在 <strong>Config</strong> 页面设置 <code>Access Key</code>，用于验证 API 请求。</p>
      
      <p><strong>模型 ID 格式</strong></p>
      <p>使用 <code>模型名@提供商名</code> 格式指定模型，例如：</p>
      <ul>
        <li><code>gpt-4o@openai</code> - OpenAI GPT-4o</li>
        <li><code>claude-sonnet-4@anthropic</code> - Anthropic Claude Sonnet 4</li>
        <li><code>llama-3.1-8b-instant@groq</code> - Groq Llama</li>
        <li><code>z-ai/glm4.7@nvidia</code> - NVIDIA NIM GLM</li>
      </ul>
    `
  },
  {
    id: 'provider-setup',
    title: '4. Provider 配置指南',
    content: `
      <p><strong>Groq (免费额度)</strong></p>
      <ul>
        <li>官网: <a href="https://groq.com" target="_blank">groq.com</a></li>
        <li>注册后获取 API Key</li>
        <li>Base URL: <code>https://api.groq.com/openai/v1</code></li>
        <li>免费模型: llama-3.1-8b-instant, llama3-8b-8192, gemma2-9b-it 等</li>
      </ul>
      
      <p><strong>OpenRouter (聚合多提供商)</strong></p>
      <ul>
        <li>官网: <a href="https://openrouter.ai" target="_blank">openrouter.ai</a></li>
        <li>注册后获取 API Key</li>
        <li>Base URL: <code>https://openrouter.ai/api/v1</code></li>
        <li>支持数百种模型，包括免费模型</li>
      </ul>
      
      <p><strong>NVIDIA NIM (免费额度)</strong></p>
      <ul>
        <li>官网: <a href="https://build.nvidia.com" target="_blank">build.nvidia.com</a></li>
        <li>注册后获取 API Key</li>
        <li>Base URL: <code>https://integrate.api.nvidia.com/v1</code></li>
        <li>免费模型: llama-3.1-8b-instant, nemotron-4-340b 等</li>
      </ul>
      
      <p><strong>OpenCode Zen (免费模型)</strong></p>
      <ul>
        <li>官网: <a href="https://opencode.ai/zen" target="_blank">opencode.ai/zen</a></li>
        <li>注册后获取 API Key（或使用 GitHub Copilot 免费访问）</li>
        <li>Base URL: <code>https://opencode.ai/zen/v1</code></li>
        <li><strong>免费模型</strong>（无需充值）:
          <ul>
            <li>big-pickle - OpenCode 独家模型，完全免费</li>
            <li>minimax-m2.5-free - MiniMax 免费模型</li>
            <li>trinity-large-preview-free - 免费预览版</li>
            <li>nemotron-3-super-free - NVIDIA 免费模型</li>
            <li>kimi-k2.5-free, glm-4.7-free 等</li>
          </ul>
        </li>
        <li>付费模型: gpt-5.x, claude-opus-4, glm-5.1 等</li>
      </ul>
      
      <p><strong>DeepSeek</strong></p>
      <ul>
        <li>官网: <a href="https://deepseek.com" target="_blank">deepseek.com</a></li>
        <li>注册后获取 API Key</li>
        <li>Base URL: <code>https://api.deepseek.com/v1</code></li>
      </ul>
    `
  },
  {
    id: 'features',
    title: '5. 核心功能',
    content: `
      <p><strong>请求日志</strong></p>
      <p>在 <strong>Logs</strong> 页面查看所有 API 请求记录，包括：</p>
      <ul>
        <li>请求时间、模型、提供商</li>
        <li>状态码、耗时、首字延迟</li>
        <li>Token 数量</li>
        <li>请求参数 (temperature, top_p 等)</li>
        <li>请求/响应内容预览</li>
      </ul>
      
      <p><strong>模型管理</strong></p>
      <p>在 <strong>Models</strong> 页面：</p>
      <ul>
        <li>查看各 Provider 的可用模型</li>
        <li>批量启用/禁用模型</li>
        <li>模型列表本地缓存，切换 Provider 时自动加载</li>
      </ul>
      
      <p><strong>密钥管理</strong></p>
      <p>在 <strong>Keys</strong> 页面：</p>
      <ul>
        <li>查看各 Provider 的密钥数量</li>
        <li>删除不再使用的密钥</li>
        <li>无法删除最后一个密钥（安全保护）</li>
      </ul>
      
      <p><strong>配置同步</strong></p>
      <p>在 <strong>Config</strong> 页面：</p>
      <ul>
        <li>配置 GitHub Token 和 Gist ID</li>
        <li><strong>Push</strong>: 将本地配置推送到 GitHub Gist</li>
        <li><strong>Pull</strong>: 从 GitHub Gist 拉取配置</li>
        <li>实现多设备配置同步</li>
      </ul>
      
      <p><strong>数据分析</strong></p>
      <p>在 <strong>Analytics</strong> 页面：</p>
      <ul>
        <li>总请求数、Token 消耗</li>
        <li>按 Provider/模型统计</li>
        <li>平均延迟、首字延迟分析</li>
      </ul>
    `
  },
  {
    id: 'troubleshooting',
    title: '6. 常见问题',
    content: `
      <p><strong>Q: 请求返回 401 错误？</strong></p>
      <p>A: 检查 Access Key 是否正确，或在 Config 页面重新设置。</p>
      
      <p><strong>Q: 模型列表为空？</strong></p>
      <p>A: 在 Models 页面点击对应 Provider 的 "Fetch Remote Models" 按钮获取模型列表。</p>
      
      <p><strong>Q: 请求超时？</strong></p>
      <p>A: 检查 Provider 的 API 是否可用，或在 Provider 设置中增加 timeout 值。</p>
      
      <p><strong>Q: 如何查看请求日志？</strong></p>
      <p>A: 进入 Logs 页面，点击日志条目可展开查看详细内容和请求参数。</p>
      
      <p><strong>Q: 模型 ID 为什么要加 @provider 后缀？</strong></p>
      <p>A: 用于区分不同 Provider 提供的相同模型。例如 gpt-4o@openai 和 gpt-4o@nvidia 是不同的模型。</p>
      
      <p><strong>Q: 服务启动失败？</strong></p>
      <p>A: 检查端口 8787 是否被占用，或查看 data/server.log 日志文件排查错误。</p>
    `
  },
  {
    id: 'deployment',
    title: '7. 部署',
    content: `
      <p><strong>开发模式</strong></p>
      <pre class="code-block"># 启动后端
python3 -m backend.main

# 或使用启动脚本
./start.sh

# 前端开发服务器
cd frontend
npm run dev</pre>
      
      <p><strong>Docker 部署</strong></p>
      <pre class="code-block">docker compose up -d</pre>
      
      <p><strong>端口配置</strong></p>
      <pre class="code-block"># 默认端口 8787
python3 start.py --port 9000

# 查看帮助
python3 start.py --help</pre>
      
      <p><strong>配置说明</strong></p>
      <p>配置文件位于项目根目录 <code>config.yml</code>，可配置：</p>
      <ul>
        <li>Server: 端口、访问密钥、JWT 密钥</li>
        <li>Providers: 各提供商的配置</li>
        <li>Model Routing: 模型路由规则</li>
        <li>SSO: OAuth 配置</li>
      </ul>
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
  padding: 20px;
}

.help-section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--color-accent);
}

.help-section-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text);
}

.help-section-content p {
  margin-bottom: 12px;
}

.help-section-content ul,
.help-section-content ol {
  margin: 12px 0;
  padding-left: 24px;
}

.help-section-content li {
  margin-bottom: 6px;
}

.code-block {
  background: var(--color-bg-input);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 12px 0;
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
}
</style>