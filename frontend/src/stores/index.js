import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import i18n from '@/i18n'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const isAuthenticated = computed(() => !!token.value)

  function setToken(t) {
    token.value = t
    localStorage.setItem('access_token', t)
  }

  function clearToken() {
    token.value = ''
    localStorage.removeItem('access_token')
  }

  return { token, isAuthenticated, setToken, clearToken }
})

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(localStorage.getItem('theme') !== 'light')

  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
    localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  }

  function toggle() {
    isDark.value = !isDark.value
    apply()
  }

  apply()

  return { isDark, toggle }
})

export const useLocaleStore = defineStore('locale', () => {
  const locale = ref(i18n.global.locale.value || 'zh')

  function set(lang) {
    i18n.global.locale.value = lang
    locale.value = lang
    localStorage.setItem('locale', lang)
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }

  function toggle() {
    set(locale.value === 'zh' ? 'en' : 'zh')
  }

  return { locale, set, toggle }
})
