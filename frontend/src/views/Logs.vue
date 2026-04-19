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
        <button class="btn btn-ghost" style="color:#ef4444" @click="clearLogs">清空</button>
      </div>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div></div>
    <div v-else class="card">
      <div v-if="logs.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="w-8"></th>
              <th>{{ $t('logs.time') }}</th>
              <th>{{ $t('logs.model') }}</th>
              <th>{{ $t('logs.provider') }}</th>
              <th class="text-center">{{ $t('logs.status') }}</th>
              <th class="text-right">耗时</th>
              <th class="text-right">首字</th>
              <th class="text-right">{{ $t('logs.inputTokens') }}</th>
              <th class="text-right">{{ $t('logs.outputTokens') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="log in logs" :key="log.id">
              <tr class="log-row" :class="{ 'row-expanded': expanded[log.id] }" @click="toggleExpand(log.id)">
                <td class="w-8 text-center">
                  <span class="expand-icon" :class="{ rotated: expanded[log.id] }">▶</span>
                </td>
                <td class="text-dim text-xs">{{ formatTime(log.timestamp) }}</td>
                <td class="mono">{{ log.model }}</td>
                <td class="text-dim">{{ log.provider }}</td>
                <td class="text-center">
                  <span class="badge" :class="log.status_code < 400 ? 'badge-green' : 'badge-red'">{{ log.status_code }}</span>
                </td>
                <td class="text-right mono">{{ formatMs(log.latency_ms) }}</td>
                <td class="text-right mono">{{ formatMs(log.first_token_ms) }}</td>
                <td class="text-right">{{ log.input_tokens || '-' }}</td>
                <td class="text-right">{{ log.output_tokens || '-' }}</td>
              </tr>
               <tr v-if="expanded[log.id]" class="expand-row">
                 <td colspan="9">
                   <div class="expand-content">
                     <div v-if="log.temperature || log.top_p || log.presence_penalty || log.frequency_penalty || log.max_tokens" class="params-block">
                       <div class="content-label">参数</div>
                       <div class="params-grid">
                         <span v-if="log.temperature">temperature: {{ log.temperature }}</span>
                         <span v-if="log.top_p">top_p: {{ log.top_p }}</span>
                         <span v-if="log.presence_penalty">presence_penalty: {{ log.presence_penalty }}</span>
                         <span v-if="log.frequency_penalty">frequency_penalty: {{ log.frequency_penalty }}</span>
                         <span v-if="log.max_tokens">max_tokens: {{ log.max_tokens }}</span>
                       </div>
                     </div>
                      <div v-if="log.request_preview || (fullContent[log.id]?.request_full) || (fullContent[log.id] && log.error_message)" class="content-block">
                        <div class="content-label">
                          Request
                          <button v-if="fullContent[log.id]?.request_full && !log.error_message" class="content-toggle" @click="fullContent[log.id].showFullRequest = !fullContent[log.id].showFullRequest">
                            {{ fullContent[log.id].showFullRequest ? '显示预览' : '显示完整' }}
                          </button>
                        </div>
                        <pre class="content-text">{{ (log.error_message || fullContent[log.id]?.showFullRequest) ? (fullContent[log.id].request_full || log.request_preview || '无请求内容') : (log.request_preview || '无请求内容') }}</pre>
                      </div>
                      <div v-if="log.response_preview || (fullContent[log.id]?.response_full) || (fullContent[log.id] && log.error_message)" class="content-block">
                        <div class="content-label">
                          Response
                          <button v-if="fullContent[log.id]?.response_full && !log.error_message" class="content-toggle" @click="fullContent[log.id].showFullResponse = !fullContent[log.id].showFullResponse">
                            {{ fullContent[log.id].showFullResponse ? '显示预览' : '显示完整' }}
                          </button>
                        </div>
                        <pre class="content-text">{{ (log.error_message || fullContent[log.id]?.showFullResponse) ? (fullContent[log.id].response_full || log.response_preview || '无响应内容') : (log.response_preview || '无响应内容') }}</pre>
                      </div>
                      <div v-if="log.error_message" class="content-block">
                        <div class="content-label">Error</div>
                        <pre class="content-text error-text">{{ log.error_message }}</pre>
                        <div v-if="log.error_type" class="error-meta">
                          <span class="error-meta-item">Type: {{ log.error_type }}</span>
                          <span v-if="log.error_code" class="error-meta-item">Code: {{ log.error_code }}</span>
                        </div>
                        <div v-if="log.error_details" class="content-block" style="margin-top: 12px;">
                          <div class="content-label">Error Details</div>
                          <pre class="content-text">{{ log.error_details }}</pre>
                        </div>
                      </div>
                     <div v-if="!log.request_preview && !log.response_preview && !log.error_message" class="text-dim text-sm">
                       无详细内容
                     </div>
                   </div>
                 </td>
               </tr>
            </template>
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
const expanded = ref({})
const fullContent = ref({})

async function fetchLogs() {
  loading.value = true
  try {
    const data = await api.getLogs(limit.value)
    logs.value = data.logs || data || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function clearLogs() {
  if (!confirm('确定清空所有请求日志？')) return
  try {
    await api.clearLogs()
    logs.value = []
  } catch (e) { console.error(e) }
}

async function loadFullContent(id) {
  if (fullContent.value[id]) return
  try {
    const data = await api.getLogDetail(id)
    const logEntry = logs.value.find(l => l.id === id)
    fullContent.value[id] = {
      ...data,
      showFullRequest: !!logEntry?.error_message,
      showFullResponse: !!logEntry?.error_message
    }
  } catch (e) { console.error(e) }
}

function toggleExpand(id) {
  expanded.value[id] = !expanded.value[id]
  if (expanded.value[id] && !fullContent.value[id]) {
    loadFullContent(id)
  }
}

function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

function formatMs(ms) {
  if (!ms) return '-'
  if (ms >= 1000) return (ms / 1000).toFixed(1) + 's'
  return ms.toFixed(0) + 'ms'
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
.text-sm { font-size: 12px; }
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

.w-8 { width: 32px; }
.log-row { cursor: pointer; transition: background 0.15s; }
.log-row:hover { background: rgba(255,255,255,0.02); }
.light .log-row:hover { background: rgba(0,0,0,0.03); }
.row-expanded { background: rgba(255,255,255,0.03); }
.light .row-expanded { background: rgba(0,0,0,0.05); }
.expand-icon { display: inline-block; font-size: 10px; color: var(--color-text-dim); transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }
.expand-row td { background: rgba(0,0,0,0.2); padding: 0; border-bottom: 1px solid var(--color-border); }
.light .expand-row td { background: rgba(0,0,0,0.05); }
.expand-content { padding: 16px 20px; max-height: 400px; overflow-y: auto; }
.content-block { margin-bottom: 16px; }
.content-block:last-child { margin-bottom: 0; }
.content-label { font-size: 11px; font-weight: 600; color: var(--color-accent); text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.content-toggle { font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-dim); cursor: pointer; transition: all 0.15s; }
.content-toggle:hover { border-color: var(--color-accent); color: var(--color-accent); }
.params-block { margin-bottom: 16px; }
.params-grid { display: flex; flex-wrap: wrap; gap: 8px 16px; }
.params-grid span { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 4px; padding: 4px 8px; font-size: 11px; font-family: 'SF Mono', 'Fira Code', monospace; }
.content-text { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 6px; padding: 12px; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; margin: 0; }
.error-text { color: var(--color-red); border-color: rgba(231,76,60,0.3); background: rgba(231,76,60,0.05); }
</style>