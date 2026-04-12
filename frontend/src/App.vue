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
<h1 class="auth-title">MonoRelay</h1>

<!-- Setup mode: First user registration -->
<div v-if="isSetupMode">
<p class="auth-subtitle">{{ $t('auth.setupRequired') }}</p>
<form @submit.prevent="handleRegister">
<input
v-model="registerForm.username"
type="text"
:placeholder="$t('auth.usernamePlaceholder')"
class="auth-input"
autofocus
/>
<input
v-model="registerForm.email"
type="email"
:placeholder="$t('auth.emailPlaceholder')"
class="auth-input"
/>
<input
v-model="registerForm.password"
type="password"
:placeholder="$t('auth.passwordPlaceholder')"
class="auth-input"
/>
<input
v-model="registerForm.confirmPassword"
type="password"
:placeholder="$t('auth.confirmPasswordPlaceholder')"
class="auth-input"
/>
<transition name="slide-down">
<p v-if="authError" class="auth-error">{{ authError }}</p>
</transition>
<button type="submit" class="btn btn-primary btn-block">{{ $t('auth.register') }}</button>
</form>
</div>

<!-- Normal login mode -->
<div v-else>
<p class="auth-subtitle">{{ $t('auth.subtitle') }}</p>

<!-- Toggle between access key and user login (hidden in sso_only mode) -->
<div v-if="!ssoOnly" class="auth-toggle">
<button
:class="['auth-toggle-btn', { active: authMode === 'key' }]"
@click="authMode = 'key'"
>{{ $t('auth.accessKey') || 'Access Key' }}</button>
<button
:class="['auth-toggle-btn', { active: authMode === 'user' }]"
@click="authMode = 'user'"
>{{ $t('auth.userLogin') || 'User Login' }}</button>
<button
v-if="ssoEnabled"
:class="['auth-toggle-btn', { active: authMode === 'sso' }]"
@click="authMode = 'sso'"
>SSO</button>
</div>

<!-- Access Key Login -->
<form v-if="authMode === 'key'" @submit.prevent="handleKeyLogin">
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

<!-- User Login -->
<form v-else-if="authMode === 'user'" @submit.prevent="handleUserLogin">
<input
v-model="loginForm.username"
type="text"
:placeholder="$t('auth.usernamePlaceholder')"
class="auth-input"
autofocus
/>
<input
v-model="loginForm.password"
type="password"
:placeholder="$t('auth.passwordPlaceholder')"
class="auth-input"
/>
<transition name="slide-down">
<p v-if="loginError" class="auth-error">{{ $t('auth.invalid') }}</p>
</transition>
<button type="submit" class="btn btn-primary btn-block">{{ $t('auth.login') }}</button>
</form>

<!-- SSO Login -->
<form v-if="authMode === 'sso' && !ssoLoading" @submit.prevent="handleSSOLogin">
<p class="auth-sso-hint">{{ localeStore.locale === 'zh' ? '使用SSO单点登录' : 'Sign in with SSO' }}</p>
<button type="submit" class="btn btn-primary btn-block">
{{ localeStore.locale === 'zh' ? '使用SSO登录' : 'Login with SSO' }}
</button>
</form>

<!-- SSO Loading Overlay -->
<div v-if="ssoLoading" class="auth-sso-loading">
<div class="auth-sso-spinner">
<div class="auth-sso-spinner-ring"></div>
<div class="auth-sso-spinner-ring"></div>
<div class="auth-sso-spinner-ring"></div>
</div>
<p class="auth-sso-loading-text">
{{ localeStore.locale === 'zh' ? '正在跳转SSO登录...' : 'Redirecting to SSO...' }}
</p>
<p class="auth-sso-loading-hint">
{{ localeStore.locale === 'zh' ? '请在新窗口中完成登录' : 'Complete login in the popup window' }}
</p>
<div class="auth-sso-dots">
<span></span><span></span><span></span>
</div>
</div>

<div class="auth-footer">
<button class="lang-btn" @click="localeStore.toggle()">
<Languages :size="14" />
{{ localeStore.locale === 'zh' ? 'EN' : '中文' }}
</button>
</div>
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
          MonoRelay
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
import { api, setAccessKey, setToken } from '@/api'
import { LayoutDashboard, Server, FileText, SlidersHorizontal, LogOut, Languages, BarChart3 } from 'lucide-vue-next'

const route = useRoute()
const authStore = useAuthStore()
const localeStore = useLocaleStore()
const inputKey = ref('')
const loginError = ref(false)
const authError = ref('')
const serverInfo = ref('')
const authed = ref(!!authStore.token)
const isSetupMode = ref(false)
const authMode = ref('key') // 'key' or 'user' or 'sso'
const ssoEnabled = ref(false)
const ssoOnly = ref(false)
const ssoLoading = ref(false)
let ssoPopup = null

const loginForm = ref({
username: '',
password: ''
})

const registerForm = ref({
username: '',
email: '',
password: '',
confirmPassword: ''
})

const tabs = [
{ path: '/dashboard', label: 'common.dashboard', icon: LayoutDashboard },
{ path: '/providers', label: 'common.providers', icon: Server },
{ path: '/analytics', label: 'common.analytics', icon: BarChart3 },
{ path: '/logs', label: 'common.logs', icon: FileText },
{ path: '/config', label: 'common.config', icon: SlidersHorizontal },
]

async function checkSetup() {
try {
const status = await api.checkSetupStatus()
isSetupMode.value = status.needs_setup

// Check SSO status
const ssoStatus = await api.getSSOStatus()
ssoEnabled.value = ssoStatus.enabled
ssoOnly.value = ssoStatus.sso_only || false

// If SSO-only mode, auto-select SSO login
if (ssoOnly.value && ssoEnabled.value) {
authMode.value = 'sso'
}
} catch (e) {
isSetupMode.value = false
ssoEnabled.value = false
ssoOnly.value = false
}
}

async function handleSSOLogin() {
ssoLoading.value = true
loginError.value = false

try {
const result = await api.getSSOLoginUrl(window.location.origin)
const loginUrl = result.login_url
const state = result.state

// Open popup window
ssoPopup = window.open(
loginUrl,
'SSO Login',
'width=500,height=600,scrollbars=yes,resizable=yes'
)

if (!ssoPopup) {
ssoLoading.value = false
loginError.value = localeStore.locale === 'zh' ? '请允许弹出窗口' : 'Please allow popup windows'
return
}

// Listen for messages from popup
const handleMessage = (event) => {
if (event.data && event.data.type === 'SSO_CALLBACK') {
window.removeEventListener('message', handleMessage)
clearInterval(checkClosed)

// Do NOT close popup here - let the callback page handle closing with its delay

if (!event.data.success) {
ssoLoading.value = false
loginError.value = event.data.error || (localeStore.locale === 'zh' ? 'SSO登录失败' : 'SSO登录失败')
// Close popup on error
if (ssoPopup) {
ssoPopup.close()
ssoPopup = null
}
return
}

const { access_token: token, state: callbackState } = event.data
if (callbackState !== state) {
ssoLoading.value = false
loginError.value = localeStore.locale === 'zh' ? '状态验证失败' : 'State mismatch'
if (ssoPopup) {
ssoPopup.close()
ssoPopup = null
}
return
}

if (token) {
setToken(token)
authStore.setToken(token)
authed.value = true
fetchInfo()
}
// Popup will close itself after showing success message
}
}

if (!event.data.success) {
ssoLoading.value = false
loginError.value = event.data.error || (localeStore.locale === 'zh' ? 'SSO登录失败' : 'SSO login failed')
return
}

const { access_token: token, state: callbackState } = event.data
if (callbackState !== state) {
ssoLoading.value = false
loginError.value = localeStore.locale === 'zh' ? '状态验证失败' : 'State mismatch'
return
}

if (token) {
setToken(token)
authStore.setToken(token)
authed.value = true
fetchInfo()
}
ssoLoading.value = false
}
}

window.addEventListener('message', handleMessage)

// Check if popup was closed without completing
const checkClosed = setInterval(() => {
if (ssoPopup && ssoPopup.closed) {
clearInterval(checkClosed)
window.removeEventListener('message', handleMessage)
ssoLoading.value = false
ssoPopup = null
}
}, 500)

} catch (e) {
console.error('SSO login failed:', e)
loginError.value = true
ssoLoading.value = false
}
}

async function handleKeyLogin() {
loginError.value = false
setAccessKey(inputKey.value)
setToken('')
try {
await api.health()
authed.value = true
fetchInfo()
} catch {
loginError.value = true
}
}

async function handleUserLogin() {
loginError.value = false
try {
const result = await api.login(loginForm.value.username, loginForm.value.password)
setToken(result.access_token)
authed.value = true
fetchInfo()
} catch (e) {
loginError.value = true
}
}

async function handleRegister() {
authError.value = ''

if (registerForm.value.password !== registerForm.value.confirmPassword) {
authError.value = localeStore.locale === 'zh' ? '两次输入的密码不一致' : 'Passwords do not match'
return
}

if (registerForm.value.password.length < 8) {
authError.value = localeStore.locale === 'zh' ? '密码长度至少8位' : 'Password must be at least 8 characters'
return
}

try {
const result = await api.register(
registerForm.value.username,
registerForm.value.email,
registerForm.value.password
)
setToken(result.access_token)
authed.value = true
isSetupMode.value = false
fetchInfo()
} catch (e) {
authError.value = e.message || (localeStore.locale === 'zh' ? '注册失败' : 'Registration failed')
}
}

function handleLogout() {
authStore.clearToken()
authed.value = false
inputKey.value = ''
loginForm.value = { username: '', password: '' }
registerForm.value = { username: '', email: '', password: '', confirmPassword: '' }
}

async function fetchInfo() {
try {
const data = await api.getInfo()
serverInfo.value = `${data.local_ip || '127.0.0.1'}:${data.port || 8787}`
} catch {
serverInfo.value = 'localhost:8787'
}
}

onMounted(() => {
if (authed.value) {
fetchInfo()
} else {
checkSetup()
}
})
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
.auth-toggle {
display: flex;
gap: 8px;
margin-bottom: 20px;
justify-content: center;
}
.auth-toggle-btn {
padding: 8px 16px;
border-radius: 6px;
border: 1px solid var(--color-border);
background: transparent;
color: var(--color-text-dim);
font-size: 13px;
cursor: pointer;
transition: all 0.15s;
}
.auth-toggle-btn:hover {
border-color: var(--color-accent);
color: var(--color-accent);
}
.auth-toggle-btn.active {
background: var(--color-accent);
color: #fff;
border-color: var(--color-accent);
}
.auth-sso-hint {
  font-size: 13px;
  color: var(--color-text-dim);
  margin-bottom: 16px;
}
.auth-sso-loading {
  padding: 32px 0;
  text-align: center;
}
.auth-sso-spinner {
  width: 56px;
  height: 56px;
  margin: 0 auto 20px;
  position: relative;
}
.auth-sso-spinner-ring {
  position: absolute;
  width: 100%;
  height: 100%;
  border: 3px solid transparent;
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: auth-sso-spin 1.2s linear infinite;
}
.auth-sso-spinner-ring:nth-child(2) {
  width: 80%;
  height: 80%;
  top: 10%;
  left: 10%;
  border-top-color: var(--color-accent-light);
  animation-duration: 1.5s;
  animation-direction: reverse;
}
.auth-sso-spinner-ring:nth-child(3) {
  width: 60%;
  height: 60%;
  top: 20%;
  left: 20%;
  border-top-color: var(--color-accent);
  animation-duration: 0.9s;
}
@keyframes auth-sso-spin {
  to { transform: rotate(360deg); }
}
.auth-sso-loading-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
}
.auth-sso-loading-hint {
  font-size: 13px;
  color: var(--color-text-dim);
  margin-bottom: 16px;
}
.auth-sso-dots {
  display: flex;
  justify-content: center;
  gap: 6px;
}
.auth-sso-dots span {
  width: 6px;
  height: 6px;
  background: var(--color-accent);
  border-radius: 50%;
  animation: auth-sso-dot 1.4s ease-in-out infinite;
}
.auth-sso-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.auth-sso-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes auth-sso-dot {
  0%, 80%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.3);
    opacity: 1;
  }
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
