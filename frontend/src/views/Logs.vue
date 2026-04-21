<template>
  <div class="logs-page">
    <div class="flex-between mb-4">
      <div>
        <h2 class="section-title">{{ $t('logs.title') }}</h2>
        <p class="text-dim text-sm">{{ isAdmin ? '全站请求记录' : '我的请求记录' }}</p>
      </div>
      <div class="flex gap-2">
        <select v-model.number="limit" class="form-input form-input-sm" @change="fetchLogs">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <button class="btn btn-ghost" @click="fetchLogs">
          <RefreshCw :size="14" :class="{ 'spin': loading }" class="mr-1" />
          {{ $t('logs.refresh') }}
        </button>
        <button v-if="isAdmin" class="btn btn-ghost" style="color:#ef4444" @click="clearLogs">清空</button>
      </div>
    </div>

    <div v-if="loading && !logs.length" class="loading"><div class="spinner"></div></div>
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
              <th class="text-right">Token (I/O)</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="log in logs" :key="log.id">
              <tr class="log-row" :class="{ 'row-expanded': expanded[log.id] }" @click="toggleExpand(log.id)">
                <td class="w-8 text-center">
                  <span class="expand-icon" :class="{ rotated: expanded[log.id] }">▶</span>
                </td>
                <td class="text-dim text-xs">{{ formatTime(log.timestamp) }}</td>
                <td class="mono text-xs">{{ log.model }}</td>
                <td class="text-dim">{{ log.provider }}</td>
                <td class="text-center">
                  <span class="badge" :class="log.status_code < 400 ? 'badge-green' : 'badge-red'">{{ log.status_code }}</span>
                </td>
                <td class="text-right mono text-xs">{{ formatMs(log.latency_ms) }}</td>
                <td class="text-right mono text-xs">{{ log.input_tokens || 0 }}/{{ log.output_tokens || 0 }}</td>
              </tr>
                <tr v-if="expanded[log.id]" class="expand-row">
                  <td colspan="7">
                    <div class="expand-content">
                     <!-- Params Block -->
                     <div v-if="log.temperature || log.top_p || log.max_tokens" class="params-block">
                       <div class="content-label">参数</div>
                       <div class="params-grid">
                         <span v-if="log.temperature">temp: {{ log.temperature }}</span>
                         <span v-if="log.top_p">top_p: {{ log.top_p }}</span>
                         <span v-if="log.max_tokens">limit: {{ log.max_tokens }}</span>
                       </div>
                     </div>

                      <!-- Request Section -->
                      <div v-if="log.request_preview || getFullRequest(log.id)" class="content-block">
                        <div class="content-label">
                          Request
                          <button v-if="getFullRequest(log.id)" class="content-toggle" @click="toggleFullRequest(log.id)">
                            {{ isFullRequest(log.id) ? '显示请求文本' : '显示原始请求' }}
                          </button>
                        </div>
                        <div v-if="!isFullRequest(log.id) && getParsedMessages(log.id)" class="chat-container">
                          <div v-for="(msg, idx) in getParsedMessages(log.id)" :key="idx" class="message-item" :class="'msg-' + msg.role">
                            <div class="message-role">{{ msg.role.toUpperCase() }}</div>
                            <div class="message-bubble">{{ msg.content }}</div>
                          </div>
                        </div>
                        <pre v-else class="content-text">{{ isFullRequest(log.id) ? getFullRequest(log.id) : (log.request_preview || '无预览内容') }}</pre>
                      </div>

                      <!-- Response Section -->
                      <div v-if="log.response_preview || getFullResponse(log.id)" class="content-block">
                        <div class="content-label">
                          Response
                          <button v-if="getFullResponse(log.id)" class="content-toggle" @click="toggleFullResponse(log.id)">
                            {{ isFullResponse(log.id) ? '显示响应文本' : '显示原始响应' }}
                          </button>
                        </div>

                        <!-- Thinking Sub-section -->
                        <div v-if="getThinkingContent(log.id) && !isFullResponse(log.id)" class="thinking-sub-block" style="margin-bottom: 12px;">
                          <div class="sub-label">Thinking Process</div>
                          <pre class="content-text thinking-text">{{ getThinkingContent(log.id) }}</pre>
                        </div>

                        <pre class="content-text">{{ isFullResponse(log.id) ? getFullResponse(log.id) : (getCleanResponseContent(log.id) || '无预览内容') }}</pre>
                      </div>

                      <!-- Error Section -->
                      <div v-if="log.error_message" class="content-block">
                        <div class="content-label">Error</div>
                        <pre class="content-text error-text">{{ log.error_message }}</pre>
                        <div v-if="log.error_type" class="error-meta">
                          <span class="error-meta-item">Type: {{ log.error_type }}</span>
                        </div>
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
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api'
import { RefreshCw } from 'lucide-vue-next'

const loading = ref(true)
const logs = ref([])
const limit = ref(50)
const expanded = ref({})
const fullContent = ref({})
const showFullReqState = ref({})
const showFullResState = ref({})
const user = ref(null)

const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.is_admin)

async function fetchLogs() {
  loading.value = true
  try {
    user.value = await api.getMe()
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
    fullContent.value[id] = data
    if (data.error_message) {
      showFullReqState.value[id] = true
      showFullResState.value[id] = true
    }
  } catch (e) { console.error(e) }
}

function toggleExpand(id) {
  expanded.value[id] = !expanded.value[id]
  if (expanded.value[id] && !fullContent.value[id]) loadFullContent(id)
}

function isFullRequest(id) { return !!showFullReqState.value[id] }
function isFullResponse(id) { return !!showFullResState.value[id] }
function toggleFullRequest(id) { showFullReqState.value[id] = !showFullReqState.value[id] }
function toggleFullResponse(id) { showFullResState.value[id] = !showFullResState.value[id] }

function getFullRequest(id) {
  const full = fullContent.value[id]
  if (!full?.request_full) return null
  try {
    const obj = typeof full.request_full === 'string' ? JSON.parse(full.request_full) : full.request_full
    return JSON.stringify(obj, null, 2)
  } catch (e) { return full.request_full }
}

function getFullResponse(id) {
  const full = fullContent.value[id]
  if (!full?.response_full) return null
  try {
    const obj = typeof full.response_full === 'string' ? JSON.parse(full.response_full) : full.response_full
    return JSON.stringify(obj, null, 2)
  } catch (e) { return full.response_full }
}

function getParsedMessages(id) {
  const full = fullContent.value[id]
  if (!full?.request_full) return null
  try {
    const obj = typeof full.request_full === 'string' ? JSON.parse(full.request_full) : full.request_full
    if (obj.messages && Array.isArray(obj.messages)) {
      return obj.messages.map(m => ({
        role: m.role || 'user',
        content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
      }))
    }
  } catch (e) {}
  return null
}

function getThinkingContent(id) {
  const full = fullContent.value[id]
  const log = logs.value.find(l => l.id === id)
  if (full?.response_full) {
    try {
      const parsed = typeof full.response_full === 'string' ? JSON.parse(full.response_full) : full.response_full
      if (parsed.reasoning_content) return parsed.reasoning_content
      if (parsed.choices?.[0]?.message?.reasoning_content) return parsed.choices[0].message.reasoning_content
    } catch (e) {}
  }
  const preview = log?.response_preview || full?.response_preview
  if (preview && preview.startsWith('[Thinking]')) {
    const parts = preview.split('\n\n---\n\n')
    if (parts.length > 1) return parts[0].replace('[Thinking]\n', '')
  }
  return null
}

function getCleanResponseContent(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  const preview = log?.response_preview || full?.response_preview
  if (preview && preview.startsWith('[Thinking]')) {
    const parts = preview.split('\n\n---\n\n')
    if (parts.length > 1) return parts[1]
  }
  return preview
}

function formatTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '-' }
function formatMs(ms) { return ms ? (ms >= 1000 ? (ms / 1000).toFixed(1) + 's' : ms.toFixed(0) + 'ms') : '-' }

onMounted(fetchLogs)
</script>

<style scoped>
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 16px; font-weight: 600; }
.mb-4 { margin-bottom: 16px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 10px; padding: 20px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--color-text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--color-border); }
th.text-right { text-align: right; }
td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
td.text-right { text-align: right; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.text-dim { color: var(--color-text-dim); }
.text-xs { font-size: 11px; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green { background: rgba(0,184,148,0.15); color: #00b894; }
.badge-red { background: rgba(231,76,60,0.15); color: #e74c3c; }
.badge-gray { background: rgba(255,255,255,0.1); color: var(--color-text-dim); }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.expand-icon { display: inline-block; font-size: 10px; transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }
.expand-row td { background: rgba(0,0,0,0.2); padding: 0; }
.expand-content { padding: 16px 20px; max-height: 500px; overflow-y: auto; }
.content-block { margin-bottom: 16px; }
.content-label { font-size: 11px; font-weight: 600; color: var(--color-accent); text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.content-toggle { font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-dim); cursor: pointer; }
.content-text { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }

.chat-container { display: flex; flex-direction: column; gap: 12px; background: rgba(0,0,0,0.1); padding: 16px; border-radius: 10px; border: 1px solid var(--color-border); }
.message-item { display: flex; flex-direction: column; max-width: 85%; }
.msg-user { align-self: flex-end; align-items: flex-end; }
.msg-assistant { align-self: flex-start; align-items: flex-start; }
.msg-system { align-self: center; align-items: center; max-width: 100%; }
.message-bubble { padding: 10px 14px; border-radius: 12px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.msg-user .message-bubble { background: var(--color-accent); color: #fff; border-bottom-right-radius: 2px; }
.msg-assistant .message-bubble { background: var(--color-bg-input); border: 1px solid var(--color-border); border-bottom-left-radius: 2px; }
.msg-system .message-bubble { background: rgba(255,255,255,0.05); color: var(--color-text-dim); border-radius: 6px; font-style: italic; }

.thinking-sub-block { margin-top: 12px; padding-left: 12px; border-left: 2px solid rgba(168, 85, 247, 0.3); }
.sub-label { font-size: 10px; font-weight: 600; color: #a855f7; text-transform: uppercase; margin-bottom: 6px; }
.thinking-text { background: rgba(168, 85, 247, 0.02); border-color: rgba(168, 85, 247, 0.1); color: var(--color-text-dim); font-style: italic; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
