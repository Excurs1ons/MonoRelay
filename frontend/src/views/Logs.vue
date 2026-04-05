<template>
  <div>
    <div class="flex-between mb-4">
      <h2 class="section-title">{{ $t('logs.title') }}</h2>
      <div class="flex gap-2">
        <select v-model.number="limit" class="form-input form-input-sm" @change="fetchLogs">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <button class="btn btn-ghost" @click="fetchLogs">{{ $t('logs.refresh') }}</button>
      </div>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div></div>
    <div v-else class="card">
      <div v-if="logs.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ $t('logs.time') }}</th>
              <th>{{ $t('logs.model') }}</th>
              <th>{{ $t('logs.provider') }}</th>
              <th class="text-center">{{ $t('logs.status') }}</th>
              <th class="text-right">{{ $t('logs.latency') }}</th>
              <th class="text-right">{{ $t('logs.inputTokens') }}</th>
              <th class="text-right">{{ $t('logs.outputTokens') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td class="text-dim text-xs">{{ formatTime(log.timestamp) }}</td>
              <td class="mono">{{ log.model }}</td>
              <td class="text-dim">{{ log.provider }}</td>
              <td class="text-center">
                <span class="badge" :class="log.status_code < 400 ? 'badge-green' : 'badge-red'">{{ log.status_code }}</span>
              </td>
              <td class="text-right mono">{{ log.latency_ms?.toFixed(0) || '-' }}ms</td>
              <td class="text-right">{{ log.input_tokens || '-' }}</td>
              <td class="text-right">{{ log.output_tokens || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">{{ $t('logs.noLogs') }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'

const loading = ref(true)
const logs = ref([])
const limit = ref(50)

async function fetchLogs() {
  loading.value = true
  try {
    const data = await api.getLogs(limit.value)
    logs.value = data.logs || data || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

onMounted(fetchLogs)
</script>

<style scoped>
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 16px; font-weight: 600; }
.mb-4 { margin-bottom: 16px; }
.flex { display: flex; }
.gap-2 { gap: 8px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--color-text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--color-border); }
th.text-center { text-align: center; }
th.text-right { text-align: right; }
td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
td.text-right { text-align: right; }
td.text-center { text-align: center; }
tr:last-child td { border-bottom: none; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
.text-dim { color: var(--color-text-dim); }
.text-xs { font-size: 11px; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green { background: rgba(0,184,148,0.15); color: var(--color-green); }
.badge-red { background: rgba(231,76,60,0.15); color: var(--color-red); }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.btn-ghost:hover { border-color: var(--color-accent); color: var(--color-accent); }
.form-input { padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.form-input:focus { outline: none; border-color: var(--color-accent); }
.form-input-sm { padding: 5px 10px; font-size: 12px; }
.empty { text-align: center; padding: 30px; color: var(--color-text-dim); font-size: 13px; }
.loading { text-align: center; padding: 40px; color: var(--color-text-dim); }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border); border-top-color: var(--color-accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
