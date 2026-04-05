import { createI18n } from 'vue-i18n'
import zh from './locales/zh.json'
import en from './locales/en.json'

const saved = localStorage.getItem('locale')
const browser = navigator.language.startsWith('zh') ? 'zh' : 'en'

const i18n = createI18n({
  legacy: false,
  locale: saved || browser,
  fallbackLocale: 'en',
  messages: { zh, en },
})

export default i18n
