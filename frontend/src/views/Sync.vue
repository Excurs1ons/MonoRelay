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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import { Eye, EyeOff } from 'lucide-vue-next'

const { t } = useI18n()

const token = ref('')
const showToken = ref(false)
const gistId = ref('')
const busy = ref(false)
const action = ref('')
const tokenStatus = ref(null)
const statusMsg = ref(null)

async function fetchStatus() {
  try {
    const data = await api.getSyncStatus()
    if (data.has_token) token.value = data.token_full || ''
    if (data.gist_id) gistId.value = data.gist_id
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
    if (data.found) { gistId.value = data.gist_id; statusMsg.value = { ok: true, message: `${t('sync.gistFound')}: ${data.gist_id}` } }
    else { statusMsg.value = { ok: false, message: data.error || t('sync.gistNotFound') } }
  } catch (e) { statusMsg.value = { ok: false, message: e.message } }
}

async function pushSync() {
  busy.value = true; action.value = 'push'
  try { await api.setupSync(token.value, gistId.value); statusMsg.value = { ok: true, message: t('sync.pushSuccess') } }
  catch (e) { statusMsg.value = { ok: false, message: e.message } }
  finally { busy.value = false }
}

async function pullSync() {
  busy.value = true; action.value = 'pull'
  try { await api.pullSync(); statusMsg.value = { ok: true, message: t('sync.pullSuccess') } }
  catch (e) { statusMsg.value = { ok: false, message: e.message } }
  finally { busy.value = false }
}

onMounted(fetchStatus)
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
