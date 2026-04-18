<template>
  <div class="about-page">
    <h2 class="section-title">关于 MonoRelay</h2>

    <div class="about-content">
      <div class="card mb-4">
        <div class="about-logo">
          <div class="logo-icon">MR</div>
          <div class="logo-text">
            <h3>MonoRelay</h3>
            <p class="version">统一 LLM API 代理服务</p>
          </div>
        </div>
        <p class="desc">
          MonoRelay 是一个强大的 LLM API 聚合网关，支持同时连接多个 LLM 提供商，
          通过单一的 OpenAI 兼容接口对外提供服务。
        </p>
        <div class="features">
          <div class="feature-item">
            <CheckCircle :size="16" />
            <span>多提供商统一管理</span>
          </div>
          <div class="feature-item">
            <CheckCircle :size="16" />
            <span>自动模型路由</span>
          </div>
          <div class="feature-item">
            <CheckCircle :size="16" />
            <span>完整请求日志</span>
          </div>
          <div class="feature-item">
            <CheckCircle :size="16" />
            <span>配置 GitHub 同步</span>
          </div>
        </div>
      </div>

      <div class="card mb-4">
        <h3 class="card-title">技术栈</h3>
        <div class="tech-list">
          <span class="tech-tag">Python</span>
          <span class="tech-tag">FastAPI</span>
          <span class="tech-tag">Vue 3</span>
          <span class="tech-tag">SQLite</span>
          <span class="tech-tag">httpx</span>
        </div>
      </div>

      <div class="card mb-4">
        <h3 class="card-title">支持的提供商</h3>
        <div class="providers-grid">
          <div class="provider-badge" v-for="p in providers" :key="p">
            {{ p }}
          </div>
        </div>
      </div>

      <div class="card">
        <h3 class="card-title">链接</h3>
        <div class="links">
          <a href="https://github.com/Excurs1ons/MonoRelay" target="_blank">
            <Github :size="16" /> GitHub
          </a>
          <a href="https://github.com/Excurs1ons/MonoRelay/issues" target="_blank">
            <Bug :size="16" /> 问题反馈
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { CheckCircle, Github, Bug } from 'lucide-vue-next'

const providers = ref([])

onMounted(async () => {
  try {
    const health = await api.health()
    providers.value = Object.keys(health.providers || {})
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.about-page {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 24px;
}

.mb-4 { margin-bottom: 16px; }

.card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  padding: 20px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--color-text-dim);
}

.about-logo {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.logo-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--color-accent), #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  color: white;
}

.logo-text h3 {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 4px 0;
}

.version {
  color: var(--color-text-dim);
  font-size: 13px;
  margin: 0;
}

.desc {
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 16px;
}

.features {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text);
}

.feature-item svg {
  color: var(--color-green);
}

.tech-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tech-tag {
  background: var(--color-bg-input);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-family: 'SF Mono', monospace;
}

.providers-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.provider-badge {
  background: var(--color-accent);
  color: white;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
}

.links {
  display: flex;
  gap: 16px;
}

.links a {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-accent);
  text-decoration: none;
  font-size: 13px;
}

.links a:hover {
  text-decoration: underline;
}
</style>