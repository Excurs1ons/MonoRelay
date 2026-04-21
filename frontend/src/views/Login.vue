<template>
<Toast />
<div class="auth-screen">
  <div class="bg-layer">
    <div class="bg-gradient"></div>
    <div class="bg-grain"></div>
  </div>
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

      <div v-if="isSetupMode">
        <p class="auth-subtitle">{{ $t('auth.setupRequired') }}</p>
        <form @submit.prevent="handleRegister">
          <input v-model="registerForm.username" type="text" name="username" autocomplete="username" :placeholder="$t('auth.usernamePlaceholder')" class="auth-input" autofocus />
          <input v-model="registerForm.email" type="email" name="email" autocomplete="email" :placeholder="$t('auth.emailPlaceholder')" class="auth-input" />
          <input v-model="registerForm.password" type="password" name="password" autocomplete="new-password" :placeholder="$t('auth.passwordPlaceholder')" class="auth-input" />
          <input v-model="registerForm.confirmPassword" type="password" name="confirmPassword" autocomplete="new-password" :placeholder="$t('auth.confirmPasswordPlaceholder')" class="auth-input" />
          <div v-if="turnstileSiteKey" class="cf-turnstile mt-4 mb-2" :data-sitekey="turnstileSiteKey" data-callback="onTurnstileVerify" data-expired-callback="onTurnstileExpired" data-theme="dark"></div>
          <transition name="slide-down">
            <p v-if="authError" class="auth-error">{{ authError }}</p>
          </transition>
          <button type="submit" class="btn btn-primary btn-block">{{ $t('auth.register') }}</button>
        </form>
      </div>

      <div v-else>
        <p class="auth-subtitle">{{ $t('auth.subtitle') }}</p>

        <div v-if="!ssoOnly && accessKeyEnabled" class="auth-toggle">
          <button :class="['auth-toggle-btn', { active: authMode === 'key' }]" @click="authMode = 'key'">{{ $t('auth.accessKey') || 'Access Key' }}</button>
          <button :class="['auth-toggle-btn', { active: authMode === 'user' }]" @click="authMode = 'user'">Native</button>
          <button v-if="ssoEnabled" :class="['auth-toggle-btn', { active: authMode === 'sso' }]" @click="authMode = 'sso'">SSO</button>
        </div>

        <form v-if="authMode === 'key'" @submit.prevent="handleKeyLogin">
          <div class="input-with-btn">
            <input v-model="inputKey" type="password" name="access-key" autocomplete="current-password" :placeholder="$t('auth.placeholder')" class="auth-input" autofocus />
            <button type="button" class="input-btn-icon" @click="inputKey = generateKey()" title="生成随机Key">
              <RefreshCw :size="16" />
            </button>
          </div>
          <transition name="slide-down">
            <p v-if="loginError" class="auth-error">{{ $t('auth.invalid') }}</p>
          </transition>
          <button type="submit" class="btn btn-primary btn-block">{{ $t('auth.submit') }}</button>
        </form>

        <form v-else-if="authMode === 'user'" @submit.prevent="handleUserLogin">
          <input v-model="loginForm.username" type="text" name="username" autocomplete="username" :placeholder="$t('auth.usernamePlaceholder')" class="auth-input" autofocus />
          <input v-model="loginForm.password" type="password" name="password" autocomplete="current-password" :placeholder="$t('auth.passwordPlaceholder')" class="auth-input" />
          <div v-if="turnstileSiteKey" class="cf-turnstile mt-4 mb-2" :data-sitekey="turnstileSiteKey" data-callback="onTurnstileVerify" data-expired-callback="onTurnstileExpired" data-theme="dark"></div>
          <transition name="slide-down">
            <p v-if="loginError" class="auth-error">{{ $t('auth.invalid') }}</p>
          </transition>
          <button type="submit" class="btn btn-primary btn-block">{{ $t('auth.login') }}</button>
        </form>

        <form v-if="authMode === 'sso' && !ssoLoading" @submit.prevent="handleSSOLogin">
          <p class="auth-sso-hint">{{ ssoProviderText }}</p>
          <button type="submit" class="btn btn-primary btn-block">
            <component :is="ssoProviderIcon" :size="16" class="mr-1" />
            {{ ssoProviderButtonText }}
          </button>
        </form>

        <div v-if="ssoLoading" class="auth-sso-loading">
          <div class="auth-sso-spinner">
            <div class="auth-sso-spinner-ring"></div>
            <div class="auth-sso-spinner-ring"></div>
            <div class="auth-sso-spinner-ring"></div>
          </div>
          <p class="auth-sso-loading-text">{{ localeStore.locale === 'zh' ? '正在跳转SSO登录...' : 'Redirecting to SSO...' }}</p>
          <p class="auth-sso-loading-hint">{{ localeStore.locale === 'zh' ? '请在新窗口中完成登录' : 'Complete login in the popup window' }}</p>
          <div class="auth-sso-dots"><span></span><span></span><span></span></div>
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
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore, useLocaleStore, useToastStore } from '@/stores'
import Toast from '@/components/Toast.vue'
import { api, setAccessKey, setToken } from '@/api'
import { Languages, RefreshCw, Github, Chrome } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()
const localeStore = useLocaleStore()
const toast = useToastStore()

const inputKey = ref('')
const loginError = ref(false)
const authError = ref('')
const isSetupMode = ref(false)
const authMode = ref('key')
const accessKeyEnabled = ref(true)
const turnstileSiteKey = ref('')
const turnstileToken = ref('')
const ssoEnabled = ref(false)
const ssoOnly = ref(false)
const ssoLoading = ref(false)
const ssoProvider = ref('github')
let ssoPopup = null

window.onTurnstileVerify = (token) => { turnstileToken.value = token }
window.onTurnstileExpired = () => { turnstileToken.value = '' }

const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ username: '', email: '', password: '', confirmPassword: '' })

const ssoProviderIcon = computed(() => {
  switch (ssoProvider.value) {
    case 'github':
      return Github
    case 'google':
      return Chrome
    default:
      return Github
  }
})

const ssoProviderText = computed(() => {
  switch (ssoProvider.value) {
    case 'github':
      return localeStore.locale === 'zh' ? '使用 GitHub 账号登录' : 'Sign in with GitHub'
    case 'google':
      return localeStore.locale === 'zh' ? '使用 Google 账号登录' : 'Sign in with Google'
    default:
      return localeStore.locale === 'zh' ? '使用 SSO 单点登录' : 'Sign in with SSO'
  }
})

const ssoProviderButtonText = computed(() => {
  switch (ssoProvider.value) {
    case 'github':
      return localeStore.locale === 'zh' ? 'GitHub 登录' : 'Login with GitHub'
    case 'google':
      return localeStore.locale === 'zh' ? 'Google 登录' : 'Login with Google'
    default:
      return localeStore.locale === 'zh' ? 'SSO 登录' : 'Login with SSO'
  }
})

async function checkSetup() {
  try {
    const status = await api.checkSetupStatus()
    isSetupMode.value = status.needs_setup
    const ssoStatus = await api.getSSOStatus()
    ssoEnabled.value = ssoStatus.enabled
    ssoOnly.value = ssoStatus.sso_only || false
    ssoProvider.value = ssoStatus.provider || 'github'
    const info = await api.getInfo()
    accessKeyEnabled.value = info.access_key_enabled !== false
    turnstileSiteKey.value = info.turnstile_site_key || ''
    if (turnstileSiteKey.value && !document.getElementById('turnstile-script')) {
      const script = document.createElement('script')
      script.id = 'turnstile-script'
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
      script.async = true
      script.defer = true
      document.head.appendChild(script)
    }
    if (ssoOnly.value && ssoEnabled.value) authMode.value = 'sso'
    else if (!accessKeyEnabled.value && authMode.value === 'key') authMode.value = 'user'
  } catch (e) {
    isSetupMode.value = false
    ssoEnabled.value = false
    ssoOnly.value = false
  }
}

async function handleKeyLogin() {
  loginError.value = false
  setAccessKey(inputKey.value)
  setToken('')
  try {
    await api.health(turnstileToken.value)
    authStore.setToken(inputKey.value)
    router.push('/dashboard')
  } catch { loginError.value = true }
}

function generateKey() {
  return [8, 13, 8, 13, 8, 13, 8, 13].map(x => x.toString(36)).join('-').toUpperCase()
}

async function handleUserLogin() {
  loginError.value = false
  try {
    const result = await api.login(loginForm.value.username, loginForm.value.password, turnstileToken.value)
    setToken(result.access_token)
    authStore.setToken(result.access_token)
    router.push('/dashboard')
  } catch (e) { loginError.value = true }
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
    const result = await api.register(registerForm.value.username, registerForm.value.email, registerForm.value.password, turnstileToken.value)
    setToken(result.access_token)
    authStore.setToken(result.access_token)
    isSetupMode.value = false
    router.push('/dashboard')
  } catch (e) { authError.value = e.message || 'Registration failed' }
}

async function handleSSOLogin() {
  ssoLoading.value = true
  loginError.value = false
  try {
    const result = await api.getSSOLoginUrl(window.location.origin)
    ssoPopup = window.open(result.login_url, 'SSO Login', 'width=500,height=600,scrollbars=yes,resizable=yes')
    if (!ssoPopup) { ssoLoading.value = false; loginError.value = 'Please allow popup windows'; return }
    const handleMessage = (event) => {
      if (event.data && event.data.type === 'SSO_CALLBACK') {
        window.removeEventListener('message', handleMessage)
        if (event.data.success && event.data.access_token) {
          setToken(event.data.access_token)
          authStore.setToken(event.data.access_token)
          router.push('/dashboard')
        }
        ssoLoading.value = false
      }
    }
    window.addEventListener('message', handleMessage)
  } catch (e) { loginError.value = true; ssoLoading.value = false }
}

onMounted(checkSetup)
</script>

<style>
/* 样式已移至 global style.css 以确保稳定性 */
</style>