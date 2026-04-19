<template>
<Toast />
  <!-- Main app -->
  <div class="app">
    <div class="bg-layer">
      <div class="bg-gradient"></div>
    </div>

    <!-- Header - 全屏固定浮层 -->
    <header class="header">
      <div class="header-inner">
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
          <button class="btn btn-ghost btn-xs" @click="localeStore.toggle()">
            <Languages :size="14" />
          </button>
          <button class="btn btn-ghost btn-xs" @click="handleLogout">
            <LogOut :size="14" />
          </button>
        </div>
      </div>
    </header>

    <div class="container">
      <!-- Segmented tabs -->
      <nav class="tabs">
        <button
          v-for="tab in filteredTabs"
          :key="tab.path"
          class="tab"
          :class="{ active: route.path === tab.path }"
          @click="$router.push(tab.path)"
        >
          <component :is="tab.icon" :size="16" />
          {{ tab.label.startsWith('common.') ? $t(tab.label) : tab.label }}
        </button>
      </nav>

      <!-- Page content -->
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore, useLocaleStore } from '@/stores'
import Toast from '@/components/Toast.vue'
import { api, setAccessKey, setToken } from '@/api'
import { LayoutDashboard, Server, FileText, SlidersHorizontal, LogOut, Languages, BarChart3, Key, Boxes, Info, Users, User, Settings } from 'lucide-vue-next'

const route = useRoute()
const authStore = useAuthStore()
const localeStore = useLocaleStore()
const inputKey = ref('')
const loginError = ref(false)
const authError = ref('')
const serverInfo = ref('')
const authed = computed(() => !!authStore.token)
const isSetupMode = ref(false)
const userData = ref(null)
const authMode = ref('key') // 'key' or 'user' or 'sso'
const accessKeyEnabled = ref(true)
const turnstileSiteKey = ref('')
const turnstileToken = ref('')
const ssoEnabled = ref(false)
const ssoOnly = ref(false)
const ssoLoading = ref(false)
let ssoPopup = null

// Turnstile verify callback
window.onTurnstileVerify = (token) => {
  console.log('Turnstile verified')
  turnstileToken.value = token
}

window.onTurnstileExpired = () => {
  console.log('Turnstile expired')
  turnstileToken.value = ''
}

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
  { path: '/keys', label: 'common.keys', icon: Key },
  { path: '/models', label: 'common.models', icon: Boxes },
  { path: '/analytics', label: 'common.analytics', icon: BarChart3 },
  { path: '/logs', label: 'common.logs', icon: FileText },
  { path: '/config', label: 'common.config', icon: SlidersHorizontal },
  { path: '/settings', label: '设置', icon: Settings, adminOnly: true },
  { path: '/users', label: '用户', icon: Users, adminOnly: true },
  { path: '/account', label: '账户', icon: User },
  { path: '/about', label: '关于', icon: Info },
]

const filteredTabs = computed(() => {
  return tabs.filter(tab => {
    if (tab.adminOnly && (!userData.value || !userData.value.is_admin)) {
      return false
    }
    return true
  })
})

async function checkSetup() {
try {
const status = await api.checkSetupStatus()
isSetupMode.value = status.needs_setup

// Check SSO status
const ssoStatus = await api.getSSOStatus()
ssoEnabled.value = ssoStatus.enabled
ssoOnly.value = ssoStatus.sso_only || false

// Check if access key is enabled
const info = await api.getInfo()
accessKeyEnabled.value = info.access_key_enabled !== false
turnstileSiteKey.value = info.turnstile_site_key || ''

if (turnstileSiteKey.value) {
  // Inject Turnstile script
  if (!document.getElementById('turnstile-script')) {
    const script = document.createElement('script')
    script.id = 'turnstile-script'
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
    script.async = true
    script.defer = true
    document.head.appendChild(script)
  }
}

// If SSO-only mode, auto-select SSO login
if (ssoOnly.value && ssoEnabled.value) {
authMode.value = 'sso'
} else if (!accessKeyEnabled.value && authMode.value === 'key') {
  authMode.value = 'user'
}

// Only check for SSO token if NOT already logged in
if (!authStore.token) {
const ssoToken = localStorage.getItem('sso_token')
if (ssoToken) {
localStorage.removeItem('sso_token')
setToken(ssoToken)
authStore.setToken(ssoToken)
fetchInfo()
window.history.replaceState({}, document.title, window.location.pathname)
}
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
console.log('handleMessage: received', event.data)
if (event.data && event.data.type === 'SSO_CALLBACK') {
window.removeEventListener('message', handleMessage)
clearInterval(checkClosed)

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
fetchInfo()
}
ssoLoading.value = false
} else if (event.data && event.data.type === 'SSO_LOGIN_SUCCESS') {
console.log('handleMessage: SSO_LOGIN_SUCCESS received')
window.removeEventListener('message', handleMessage)
clearInterval(checkClosed)
if (event.data.token) {
setToken(event.data.token)
authStore.setToken(event.data.token)
fetchInfo()
}
ssoLoading.value = false
ssoPopup = null
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
    await api.health(turnstileToken.value)
    authStore.setToken(inputKey.value)

fetchInfo()
} catch {
loginError.value = true
}
}

async function handleUserLogin() {
loginError.value = false
try {
const result = await api.login(loginForm.value.username, loginForm.value.password, turnstileToken.value)
setToken(result.access_token)
authStore.setToken(result.access_token)
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
registerForm.value.password,
turnstileToken.value
)
setToken(result.access_token)
authStore.setToken(result.access_token)
isSetupMode.value = false
fetchInfo()
} catch (e) {
authError.value = e.message || (localeStore.locale === 'zh' ? '注册失败' : 'Registration failed')
}
}
function handleLogout() {
  authStore.clearToken()
  inputKey.value = ''
  loginForm.value = { username: '', password: '' }
  registerForm.value = { username: '', email: '', password: '', confirmPassword: '' }
  window.location.href = '/login'
}

async function fetchInfo() {
try {
console.log('fetchInfo: calling api.getInfo()...')
const data = await api.getInfo()
console.log('fetchInfo: got data:', data)
serverInfo.value = `${data.local_ip || '127.0.0.1'}:${data.port || 8787}`

// Fetch user info for admin check
try {
  userData.value = await api.getMe()
} catch (e) {
  console.log('Failed to fetch user info', e)
  userData.value = null
}
} catch (e) {
console.error('fetchInfo: error:', e)
serverInfo.value = 'localhost:8787'
}
}

onMounted(() => {
if (authed.value) {
  fetchInfo()
} else {
  checkSetup()
}

// Listen for storage changes (from SSO callback in popup)
window.addEventListener('storage', (e) => {
if (e.key === 'sso_token' && e.newValue) {
console.log('Storage event: sso_token changed')
localStorage.removeItem('sso_token')
setToken(e.newValue)
authStore.setToken(e.newValue)
fetchInfo()
}
})
})
</script>

<style scoped>
.auth-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--color-bg);
  position: relative;
  overflow: hidden;
}
.auth-screen .bg-layer {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
}
.auth-screen .bg-gradient {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(ellipse 100% 60% at 15% 20%, rgba(249, 115, 22, 0.12) 0%, transparent 50%),
    radial-gradient(ellipse 80% 50% at 85% 80%, rgba(124, 58, 237, 0.1) 0%, transparent 45%),
    radial-gradient(ellipse 60% 40% at 50% 60%, rgba(219, 39, 119, 0.08) 0%, transparent 40%);
  animation: gradientPulse 25s ease-in-out infinite alternate;
}
.auth-screen .bg-grain {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  opacity: 0.025;
}
@keyframes gradientPulse {
  0% { opacity: 0.7; transform: scale(1); }
  100% { opacity: 1; transform: scale(1.03); }
}
.auth-card {
  width: 100%;
  max-width: 380px;
  background: rgba(24, 24, 27, 0.6);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 40px 32px;
  text-align: center;
  position: relative;
  z-index: 1;
  box-shadow: 
    0 1px 2px rgba(0, 0, 0, 0.3),
    0 8px 32px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.auth-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 20px;
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
  font-size: 28px;
  font-weight: 700;
  font-family: var(--font-mono);
  background: linear-gradient(135deg, var(--color-text), var(--color-text-dim));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 8px;
}
.auth-subtitle {
  font-size: 14px;
  color: var(--color-text-dim);
  margin-bottom: 28px;
}
.auth-input {
  width: 100%;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text);
  font-size: 14px;
  font-family: var(--font-mono);
  transition: border-color 0.15s, box-shadow 0.15s;
  margin-bottom: 14px;
}
.auth-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15);
}
.auth-input::placeholder {
  color: var(--color-text-dim);
  opacity: 0.6;
}
.auth-error {
  font-size: 12px;
  color: var(--color-red);
  margin-bottom: 14px;
}
.auth-footer {
  margin-top: 24px;
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
  font-family: var(--font-mono);
}
.lang-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
.auth-toggle {
display: flex;
gap: 8px;
margin-bottom: 24px;
justify-content: center;
}
.auth-toggle-btn {
padding: 8px 18px;
border-radius: 6px;
border: 1px solid var(--color-border);
background: transparent;
color: var(--color-text-dim);
font-size: 13px;
cursor: pointer;
transition: all 0.15s;
font-family: var(--font-mono);
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
  border-top-color: var(--color-accent);
  opacity: 0.6;
  animation-duration: 1.5s;
  animation-direction: reverse;
}
.auth-sso-spinner-ring:nth-child(3) {
  width: 60%;
  height: 60%;
  top: 20%;
  left: 20%;
  border-top-color: var(--color-accent);
  opacity: 0.3;
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
  position: relative;
  overflow: hidden;
}
.app .bg-layer {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
}
.app .bg-gradient {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(ellipse 100% 60% at 15% 20%, rgba(249, 115, 22, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse 80% 50% at 85% 80%, rgba(124, 58, 237, 0.06) 0%, transparent 45%);
  animation: gradientPulse 25s ease-in-out infinite alternate;
}
.container {
  max-width: 1120px;
  margin: 0 auto;
  padding: 80px 24px 24px;
  position: relative;
  z-index: 1;
}
.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(24, 24, 27, 0.75);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 
    0 1px 2px rgba(0, 0, 0, 0.15),
    0 4px 16px rgba(0, 0, 0, 0.2);
}
.header-inner {
  max-width: 1120px;
  margin: 0 auto;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header h1 {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-mono);
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-logo {
  width: 24px;
  height: 24px;
  color: var(--color-accent);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-green);
  display: inline-block;
  box-shadow: 0 0 8px var(--color-green);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px var(--color-green); }
  50% { opacity: 0.6; box-shadow: 0 0 16px var(--color-green); }
}
.status-text {
  font-size: 12px;
  color: var(--color-text-dim);
  font-family: var(--font-mono);
}

.tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin-bottom: 32px;
  margin-top: 72px;
  background: rgba(24, 24, 27, 0.6);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  padding: 4px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 
    0 1px 2px rgba(0, 0, 0, 0.2),
    0 4px 16px rgba(0, 0, 0, 0.3);
}
.tab {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-dim);
  background: transparent;
  border: none;
  transition: all 0.2s;
  width: 100%;
  justify-content: center;
}
.tab:hover {
  color: var(--color-text);
  background: rgba(255,255,255,0.04);
}
.tab.active {
  background: var(--color-accent);
  color: #fff;
  box-shadow: 0 2px 12px rgba(249, 115, 22, 0.35);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  font-family: var(--font-mono);
}
.btn-primary {
  background: var(--color-accent);
  color: #fff;
}
.btn-primary:hover {
  background: var(--color-accent-hover);
  box-shadow: 0 4px 12px rgba(249, 115, 22, 0.35);
}
.btn-block {
  width: 100%;
  justify-content: center;
  padding: 12px 16px;
  font-size: 13px;
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
  padding: 6px 12px;
  font-size: 11px;
}

@media (max-width: 768px) {
  .container {
    padding: 16px;
  }
  .header {
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px 0;
    margin-bottom: 20px;
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
  .tabs {
    margin-bottom: 20px;
  }
  .tab {
    padding: 8px 14px;
    font-size: 12px;
  }
}
</style>
