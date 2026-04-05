<template>
  <!-- Auth screen -->
  <div v-if="!authed" class="auth-screen">
    <transition name="fade" appear>
      <div class="auth-card">
        <div class="auth-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h1 class="auth-title">PrismaAPIRelay</h1>
        <p class="auth-subtitle">{{ $t('auth.title') }}</p>
        <form @submit.prevent="handleLogin">
          <input
            v-model="inputKey"
            type="password"
            :placeholder="$t('auth.placeholder')"
            class="auth-input"
            autofocus
            @focus="$event.target.style.borderColor='var(--color-accent)'"
            @blur="$event.target.style.borderColor='var(--color-border)'"
          />
          <transition name="slide-down">
            <p v-if="loginError" class="auth-error">{{ $t('auth.invalid') }}</p>
          </transition>
          <button type="submit" class="btn btn-primary btn-block">{{ $t('auth.submit') }}</button>
        </form>
        <div class="auth-footer">
          <button class="lang-btn" @click="localeStore.toggle()">
            <Languages :size="14" />
            {{ localeStore.locale === 'zh' ? 'EN' : '中文' }}
          </button>
        </div>
      </div>
    </transition>
  </div>

  <!-- Main app -->
  <div v-else class="app">
    <div class="container">
      <!-- Header -->
      <header class="header">
        <h1>
          <svg class="header-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          PrismaAPIRelay
        </h1>
        <div class="header-right">
          <span class="status-dot"></span>
          <span class="status-text">{{ serverInfo }}</span>
          <button class="btn btn-ghost btn-xs" @click="localeStore.toggle()">
            <Languages :size="14" />
          </button>
          <button class="btn btn-ghost btn-xs" @click="handleLogout">
            <LogOut :size="14" />
          </button>
        </div>
      </header>

      <!-- Segmented tabs -->
      <nav class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.path"
          class="tab"
          :class="{ active: route.path === tab.path }"
          @click="$router.push(tab.path)"
        >
          <component :is="tab.icon" :size="16" />
          {{ $t(tab.label) }}
        </button>
      </nav>

      <!-- Page content -->
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore, useLocaleStore } from '@/stores'
import { api } from '@/api'
import { LayoutDashboard, Server, FileText, SlidersHorizontal, LogOut, Languages } from 'lucide-vue-next'

const route = useRoute()
const authStore = useAuthStore()
const localeStore = useLocaleStore()
const inputKey = ref('')
const loginError = ref(false)
const serverInfo = ref('')
const authed = ref(!!authStore.token)

const tabs = [
  { path: '/dashboard', label: 'common.dashboard', icon: LayoutDashboard },
  { path: '/providers', label: 'common.providers', icon: Server },
  { path: '/logs', label: 'common.logs', icon: FileText },
  { path: '/config', label: 'common.config', icon: SlidersHorizontal },
]

async function handleLogin() {
  loginError.value = false
  authStore.setToken(inputKey.value)
  try {
    await api.health()
    authed.value = true
    fetchInfo()
  } catch {
    authStore.clearToken()
    loginError.value = true
  }
}

function handleLogout() {
  authStore.clearToken()
  authed.value = false
  inputKey.value = ''
}

async function fetchInfo() {
  try {
    const data = await api.getInfo()
    serverInfo.value = `${data.local_ip || '127.0.0.1'}:${data.port || 8787}`
  } catch {
    serverInfo.value = 'localhost:8787'
  }
}

onMounted(() => { if (authed.value) fetchInfo() })
</script>

<style scoped>
.auth-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: var(--color-bg);
}
.auth-card {
  width: 100%;
  max-width: 380px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  padding: 32px;
  text-align: center;
}
.auth-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  color: var(--color-accent);
  animation: float 3s ease-in-out infinite;
}
.auth-icon svg {
  width: 100%;
  height: 100%;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.auth-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-accent);
  margin-bottom: 8px;
}
.auth-subtitle {
  font-size: 13px;
  color: var(--color-text-dim);
  margin-bottom: 24px;
}
.auth-input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text);
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  transition: border-color 0.15s, box-shadow 0.15s;
  margin-bottom: 12px;
}
.auth-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.15);
}
.auth-error {
  font-size: 12px;
  color: var(--color-red);
  margin-bottom: 12px;
}
.auth-footer {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}
.lang-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.lang-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.app {
  min-height: 100vh;
  background: var(--color-bg);
  color: var(--color-text);
}
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
}
.header h1 {
  font-size: 22px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-logo {
  width: 28px;
  height: 28px;
  color: var(--color-accent);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-green);
  display: inline-block;
  box-shadow: 0 0 6px var(--color-green);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--color-green); }
  50% { opacity: 0.7; box-shadow: 0 0 12px var(--color-green); }
}
.status-text {
  font-size: 13px;
  color: var(--color-text-dim);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 20px;
  background: var(--color-bg-card);
  padding: 4px;
  border-radius: var(--radius, 10px);
  border: 1px solid var(--color-border);
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-dim);
  background: transparent;
  border: none;
  transition: all 0.2s;
  white-space: nowrap;
  flex: 1 1 auto;
  justify-content: center;
  min-width: 0;
}
.tab:hover {
  color: var(--color-text);
  background: rgba(255,255,255,0.05);
}
.tab.active {
  background: var(--color-accent);
  color: #fff;
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.3);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 6px;
  border: none;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-primary {
  background: var(--color-accent);
  color: #fff;
}
.btn-primary:hover {
  background: var(--color-accent-hover);
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.3);
}
.btn-block {
  width: 100%;
  justify-content: center;
  padding: 10px 14px;
}
.btn-ghost {
  background: transparent;
  color: var(--color-text-dim);
  border: 1px solid var(--color-border);
}
.btn-ghost:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
.btn-xs {
  padding: 4px 10px;
  font-size: 11px;
}

@media (max-width: 768px) {
  .container {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 0;
    margin-bottom: 16px;
  }
  .header h1 {
    font-size: 18px;
  }
  .status-text {
    display: none;
  }
  .header-right {
    margin-left: auto;
  }
}
</style>
