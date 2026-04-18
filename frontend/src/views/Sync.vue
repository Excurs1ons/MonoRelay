<template>
  <div>
    <h2 class="section-title mb-4">{{ $t('sync.title') }}</h2>

    <div class="card">
      <div class="form-group">
        <label>{{ $t('sync.token') }}</label>
        <div class="flex gap-2">
          <div class="input-with-toggle flex-1">
            <input v-model="token" :type="showToken ? 'text' : 'password'" :placeholder="$t('sync.tokenPlaceholder')" class="form-input mono" />
            <button type="button" class="toggle-btn" @click="showToken = !showToken">
              <Eye v-if="!showToken" :size="16" />
              <EyeOff v-else :size="16" />
            </button>
          </div>
          <button class="btn btn-ghost" @click="verifyToken">{{ $t('sync.verifyToken') }}</button>
        </div>
        <p v-if="tokenStatus" class="mt-2 text-sm" :class="tokenStatus.ok ? 'text-green' : 'text-red'">{{ tokenStatus.message }}</p>
      </div>

      <div class="form-group">
        <label>{{ $t('sync.gistId') }}</label>
        <div class="flex gap-2">
          <input v-model="gistId" type="text" placeholder="gist_id (optional)" class="form-input flex-1 mono" />
          <button class="btn btn-ghost" @click="findGist">{{ $t('sync.findGist') }}</button>
        </div>
      </div>

      <div class="flex gap-3 mt-4">
        <button class="btn btn-primary flex-1" :disabled="busy" @click="pushSync">
          {{ busy && action === 'push' ? $t('common.loading') : $t('sync.push') }}
        </button>
        <button class="btn btn-ghost flex-1" :disabled="busy" @click="pullSync">
          {{ busy && action === 'pull' ? $t('common.loading') : $t('sync.pull') }}
        </button>
      </div>

      <div v-if="statusMsg" class="mt-4 p-3 rounded-lg text-sm" :class="statusMsg.ok ? 'toast-success' : 'toast-error'">
        {{ statusMsg.message }}
      </div>

      <!-- Gist Info -->
      <div v-if="gistInfo" class="mt-4 pt-4 border-t border-dashed border-gray-700/30">
        <div class="flex items-center gap-2 text-xs text-dim mb-3">
          <Clock :size="12" />
          <span>Gist 状态</span>
        </div>
        <div class="space-y-2">
          <div class="flex justify-between text-xs">
            <span class="text-dim">创建于</span>
            <span class="mono">{{ formatDate(gistInfo.created_at) }}</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-dim">最后同步</span>
            <span class="mono">{{ formatDate(gistInfo.updated_at) }}</span>
          </div>
          <div class="flex justify-between text-xs" v-if="gistInfo.version">
            <span class="text-dim">当前版本</span>
            <span class="mono text-xs">{{ gistInfo.version.substring(0, 7) }}</span>
          </div>
          <div class="flex justify-between text-xs font-medium">
            <span class="text-dim">距离现在</span>
            <span class="text-accent">{{ timeAgo }}</span>
          </div>
        </div>
        <div class="mt-3 flex justify-end">
          <button class="btn btn-ghost btn-xs text-xs" @click="pullSync(true)" :disabled="busy">
            强制拉取覆盖
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import { Eye, EyeOff, Clock } from 'lucide-vue-next'

const { t } = useI18n()

const token = ref('')
const showToken = ref(false)
const gistId = ref('')
const busy = ref(false)
const action = ref('')
const tokenStatus = ref(null)
const statusMsg = ref(null)
const gistInfo = ref(null)
const now = ref(new Date())

let nowTimer = null

const timeAgo = computed(() => {
  if (!gistInfo.value || !gistInfo.value.updated_at) return '-'
  const updated = new Date(gistInfo.value.updated_at)
  const diff = Math.floor((now.value - updated) / 1000)
  
  if (diff < 0) return '刚刚'
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  
  const days = Math.floor(diff / 86400)
  const hours = Math.floor((diff % 86400) / 3600)
  return `${days}天 ${hours}小时前`
})

async function fetchStatus() {
  try {
    const data = await api.getSyncStatus()
    if (data.has_token) token.value = data.token_full || ''
    if (data.gist_id) {
      gistId.value = data.gist_id
      fetchGistInfo()
    }
  } catch (e) { console.error(e) }
}

async function fetchGistInfo() {
  try {
    const res = await api.getGistInfo()
    if (res.status === 'ok') {
      gistInfo.value = res.info
      // We'll update the backend getGistInfo to return the latest version too
    }
  } catch (e) { console.error(e) }
}

async function verifyToken() {
  try {
    const data = await api.verifyToken(token.value)
    tokenStatus.value = { ok: data.valid, message: data.valid ? t('sync.tokenValid') : data.error || t('sync.tokenInvalid') }
  } catch (e) { tokenStatus.value = { ok: false, message: e.message } }
}

async function findGist() {
  try {
    const data = await api.findGist(token.value)
    if (data.found) { 
      gistId.value = data.gist_id
      statusMsg.value = { ok: true, message: `${t('sync.gistFound')}: ${data.gist_id}` }
      fetchGistInfo()
    }
    else { statusMsg.value = { ok: false, message: data.error || t('sync.gistNotFound') } }
  } catch (e) { statusMsg.value = { ok: false, message: e.message } }
}

async function pushSync() {
  busy.value = true; action.value = 'push'
  try { 
    const data = await api.pushSync(); 
    statusMsg.value = { ok: true, message: data.message || t('sync.pushSuccess') }
    fetchGistInfo()
  }
  catch (e) { statusMsg.value = { ok: false, message: e.message } }
  finally { busy.value = false }
}

async function pullSync(force = false) {
  busy.value = true; action.value = 'pull'
  try { 
    const data = await api.pullSync(token.value, force); 
    statusMsg.value = { ok: true, message: data.message || t('sync.pullSuccess') }
    fetchGistInfo()
  }
  catch (e) { statusMsg.value = { ok: false, message: e.message } }
  finally { busy.value = false }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

onMounted(() => {
  fetchStatus()
  nowTimer = setInterval(() => {
    now.value = new Date()
  }, 1000)
})

onUnmounted(() => {
  if (nowTimer) clearInterval(nowTimer)
})
</script>

<style scoped>
.section-title { font-size: 16px; font-weight: 600; }
.mb-4 { margin-bottom: 16px; }
.mt-2 { margin-top: 8px; }
.mt-4 { margin-top: 16px; }
.flex { display: flex; }
.gap-2 { gap: 8px; }
.gap-3 { gap: 12px; }
.flex-1 { flex: 1; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; max-width: 600px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 12px; color: var(--color-text-dim); margin-bottom: 6px; }
.form-input { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.form-input:focus { outline: none; border-color: var(--color-accent); }
.input-with-toggle { position: relative; display: flex; flex: 1; }
.input-with-toggle .form-input { padding-right: 36px; flex: 1; }
.toggle-btn { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--color-text-dim); cursor: pointer; padding: 4px; display: flex; align-items: center; }
.toggle-btn:hover { color: var(--color-text); }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.text-sm { font-size: 12px; }
.text-green { color: var(--color-green); }
.text-red { color: var(--color-red); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { background: var(--color-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.btn-ghost:hover { border-color: var(--color-accent); color: var(--color-accent); }
.toast-success { background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.3); color: var(--color-green); border-radius: 6px; }
.toast-error { background: rgba(231,76,60,0.1); border: 1px solid rgba(231,76,60,0.3); color: var(--color-red); border-radius: 6px; }
</style>
