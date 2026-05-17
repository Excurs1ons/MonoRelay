<template>
  <div class="logs-page">
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
      <div>
        <h2 class="text-xl font-bold" style="color: var(--color-text)">{{ $t('logs.title') }}</h2>
        <p class="text-dim text-sm mt-1">{{ isAdmin ? '全站请求记录' : '我的请求记录' }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="limit" class="select-sm" @change="fetchLogs">
          <option :value="20">最近 20 条</option>
          <option :value="50">最近 50 条</option>
          <option :value="100">最近 100 条</option>
          <option :value="200">最近 200 条</option>
        </select>
        <button v-if="isAdmin" class="btn btn-danger btn-sm" @click="clearLogs">清空日志</button>
        <button class="btn btn-primary btn-sm" @click="fetchLogs" :disabled="loading">
          <RefreshCw :size="14" :class="{ 'animate-spin': loading }" />
          刷新
        </button>
      </div>
    </div>

    <!-- Tabs for Upstream vs Downstream -->
    <div class="tabs mb-4">
      <button class="tab-btn" :class="{ active: activeTab === 'upstream' }" @click="activeTab = 'upstream'">中继日志 (Relay)</button>
      <button class="tab-btn" :class="{ active: activeTab === 'downstream' }" @click="activeTab = 'downstream'">客户端日志 (Client)</button>
    </div>

    <div v-if="loading && !logs.length" class="loading-state">
      <RefreshCw class="animate-spin mb-2" />
      加载中...
    </div>

    <div v-else class="card">
      <div v-if="logs.length" class="table-wrap">
        <table class="logs-table">
          <thead>
            <tr>
              <th class="col-expand"></th>
              <th class="col-time">{{ $t('logs.time') }}</th>
              <th class="col-model">{{ $t('logs.model') }}</th>
              <th class="col-provider" v-if="activeTab === 'upstream'">{{ $t('logs.provider') }}</th>
              <th class="col-client" v-else>客户端 IP</th>
              <th class="col-status text-center">{{ $t('logs.status') }}</th>
              <th class="col-ttft text-right">首字</th>
              <th class="col-latency text-right">耗时</th>
              <th class="col-tokens text-right">Token</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="log in logs" :key="log.id">
              <tr class="log-row" :class="{ 'row-expanded': expanded[log.id] }" @click="toggleExpand(log.id)">
                <td class="text-center">
                  <span class="expand-icon" :class="{ rotated: expanded[log.id] }">▶</span>
                </td>
                <td class="text-dim text-xs">{{ formatTime(log.timestamp) }}</td>
                <td class="mono text-xs truncate-cell">{{ log.model }}</td>
                <td class="text-dim truncate-cell" v-if="activeTab === 'upstream'">{{ log.provider }}</td>
                <td class="text-dim truncate-cell mono" v-else>{{ log.client_ip || '-' }}</td>
                <td class="text-center">
                  <span v-if="log.id < 0 && !log.status_code" class="badge badge-blue animate-pulse">处理中</span>
                  <span v-else class="badge" :class="log.status_code < 400 ? 'badge-green' : 'badge-red'">{{ log.status_code || '...' }}</span>
                </td>
                <td class="text-right mono text-xs" :class="getLatencyColor(log.first_token_ms)">
                  {{ formatMs(log.first_token_ms) }}
                </td>
                <td class="text-right mono text-xs">
                  {{ formatMs(log.id < 0 && !log.status_code ? tickingLatencies[log.id] : log.latency_ms) }}
                </td>
                <td class="text-right mono text-xs">
                  <div>{{ log.input_tokens || 0 }}/{{ log.output_tokens || 0 }}</div>
                  <div v-if="log.cache_hit_tokens" class="text-blue-400" style="font-size: 10px;">
                    ⚡ {{ log.cache_hit_tokens }}
                  </div>
                </td>
              </tr>
                <tr v-if="expanded[log.id]" class="expand-row">
                  <td colspan="100">
                    <div class="expand-content">
                      <!-- Summary Bar -->
                      <div class="expand-header-summary">
                        <span class="summary-item"><strong>{{ log.model }}</strong></span>
                        <span class="summary-item" v-if="activeTab === 'upstream'">提供商: {{ log.provider }}</span>
                        <span class="summary-item" v-else>客户端 IP: {{ log.client_ip || '未知' }}</span>
                        <span class="summary-item badge" :class="log.status_code < 400 ? 'badge-green' : 'badge-red'">{{ log.status_code || '...' }}</span>
                        <span class="summary-item">首字: {{ formatMs(log.first_token_ms) }}</span>
                        <span class="summary-item">全量: {{ formatMs(log.id < 0 && !log.status_code ? tickingLatencies[log.id] : log.latency_ms) }}</span>
                        <span class="summary-item">
                          Tokens: {{ log.input_tokens || 0 }}/{{ log.output_tokens || 0 }}
                          <span v-if="log.cache_hit_tokens" class="text-blue-400 ml-1">(⚡ {{ log.cache_hit_tokens }})</span>
                        </span>
                      </div>

                      <div v-if="log.user_agent" class="text-dim text-xs mb-3 truncate">UA: {{ log.user_agent }}</div>

                      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <!-- Request Block -->
                        <div class="content-block">
                          <div class="content-label">
                            <div class="flex items-center gap-2">
                              <button class="collapse-btn" @click.stop="toggleCollapseReq(log.id)">
                                {{ collapsedReq[log.id] ? '[+]' : '[-]' }}
                              </button>
                              {{ activeTab === 'upstream' ? 'Relay Request (Upstream)' : 'Client Request (Downstream)' }}
                            </div>
                            <button v-if="!collapsedReq[log.id]" class="content-toggle" @click.stop="toggleFullRequest(log.id)">
                              {{ isFullRequest(log.id) ? '对话式' : 'JSON' }}
                            </button>
                          </div>
                          <div v-if="!collapsedReq[log.id]">
                            <div v-if="!isFullRequest(log.id) && getParsedMessages(log.id)" class="text-body">
                              <div v-for="(msg, idx) in getParsedMessages(log.id)" :key="idx" class="text-msg">
                                <span class="text-role">{{ msg.role.toUpperCase() }}:</span>{{ msg.content }}
                              </div>
                            </div>
                            <pre v-else class="content-text">{{ getRequestContent(log.id) }}</pre>
                          </div>
                        </div>

                        <!-- Response Block -->
                        <div class="content-block">
                          <div class="content-label">
                            <div class="flex items-center gap-2">
                              <button class="collapse-btn" @click.stop="toggleCollapseRes(log.id)">
                                {{ collapsedRes[log.id] ? '[+]' : '[-]' }}
                              </button>
                              {{ activeTab === 'upstream' ? 'Relay Response (Upstream)' : 'Client Response (Downstream)' }}
                            </div>
                            <button v-if="!collapsedRes[log.id]" class="content-toggle" @click.stop="toggleFullResponse(log.id)">
                              {{ isFullResponse(log.id) ? '对话式' : 'JSON' }}
                            </button>
                          </div>
                          <div v-if="!collapsedRes[log.id]">
                            <!-- Thinking Sub-section -->
                            <div v-if="getThinkingContent(log.id) && !isFullResponse(log.id)" class="thinking-sub-block" style="margin-bottom: 12px;">
                              <div class="sub-label">Thinking Process</div>
                              <pre class="content-text thinking-text">{{ getThinkingContent(log.id) }}</pre>
                            </div>
                            <div v-if="!isFullResponse(log.id) && getParsedResponse(log.id)" class="text-body">
                              <div v-for="(msg, idx) in getParsedResponse(log.id)" :key="idx" class="text-msg">
                                <span class="text-role">{{ msg.role.toUpperCase() }}:</span>{{ msg.content }}
                              </div>
                            </div>
                            <pre v-else class="content-text">{{ getResponseContent(log.id) }}</pre>
                          </div>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state">暂无日志数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '@/api'
import { RefreshCw } from 'lucide-vue-next'

const logs = ref([])
const limit = ref(50)
const loading = ref(false)
const expanded = ref({})
const fullContent = ref({})
const showFullReqState = ref({})
const showFullResState = ref({})
const collapsedReq = ref({})
const collapsedRes = ref({})
const user = ref(null)
const activeTab = ref('upstream')
const tickingLatencies = ref({})

const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.is_admin)

let sseAbort = null
let tickTimer = null
let pollTimer = null

async function clearLogs() {
  if (!confirm('确定要清空所有日志吗？此操作不可恢复。')) return
  try {
    loading.value = true
    await api.clearLogs()
    logs.value = []
  } catch (e) {
    console.error('清空日志失败:', e)
    alert('清空日志失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function fetchLogs() {
  loading.value = true
  try {
    try { user.value = await api.getMe() } catch {}
    const data = await api.getLogs(limit.value)
    logs.value = (data.logs || data || []).map(l => ({ ...l, _start_time: l.timestamp * 1000 }))
  } catch (e) { console.error('刷新日志失败:', e) }
  finally { loading.value = false }
}

async function loadFullContent(id) {
  // Always re-fetch if response_full is missing for a finalized (positive ID) log
  if (fullContent.value[id] && fullContent.value[id].request_full && fullContent.value[id].response_full) return
  try {
    const data = await api.getLogDetail(id)
    if (!fullContent.value[id]) fullContent.value[id] = {}
    Object.assign(fullContent.value[id], data)
  } catch (e) { console.error(e) }
}

function toggleExpand(id) {
  expanded.value[id] = !expanded.value[id]
  if (expanded.value[id]) loadFullContent(id)
}

function toggleFullRequest(id) { showFullReqState.value[id] = !showFullReqState.value[id] }
function toggleFullResponse(id) { showFullResState.value[id] = !showFullResState.value[id] }
function isFullRequest(id) { return !!showFullReqState.value[id] }
function isFullResponse(id) { return !!showFullResState.value[id] }

function toggleCollapseReq(id) { collapsedReq.value[id] = !collapsedReq.value[id] }
function toggleCollapseRes(id) { collapsedRes.value[id] = !collapsedRes.value[id] }

function getRequestContent(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  if (activeTab.value === 'downstream' && (full?.downstream_request || log?.downstream_request)) {
    return full?.downstream_request || log?.downstream_request
  }
  return isFullRequest(id) ? (full?.request_full || '加载中...') : (log?.request_preview || '无预览')
}

function getResponseContent(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  if (activeTab.value === 'downstream' && (full?.downstream_response || log?.downstream_response)) {
    return full?.downstream_response || log?.downstream_response
  }
  if (isFullResponse(id)) return full?.response_full || '加载中...'
  return getCleanResponseContent(id) || '无预览'
}

function getCleanResponseContent(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  const preview = full?.response_preview || log?.response_preview
  if (preview && preview.includes('---')) {
    return preview.split('---').pop().trim()
  }
  return preview
}

function getThinkingContent(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  const preview = full?.response_preview || log?.response_preview
  if (preview && preview.startsWith('[Thinking]')) {
    const parts = preview.split('\n\n---\n\n')
    if (parts.length > 1) return parts[0].replace('[Thinking]\n', '')
  }
  return null
}

function getParsedMessages(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  const raw = full?.request_full || log?.request_preview
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed.messages || null
  } catch (e) { return null }
}

function getParsedResponse(id) {
  const log = logs.value.find(l => l.id === id)
  const full = fullContent.value[id]
  const raw = full?.response_full || log?.response_preview
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed.choices && parsed.choices[0]?.message) return [parsed.choices[0].message]
    return null
  } catch (e) { return null }
}

function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

function formatMs(ms) {
  if (ms == null) return '-'
  if (ms >= 1000) return (ms / 1000).toFixed(2) + 's'
  return ms.toFixed(0) + 'ms'
}

function getLatencyColor(ms) {
  if (!ms) return ''
  if (ms > 2000) return 'text-red-500'
  if (ms > 800) return 'text-orange-500'
  return 'text-green-500'
}

function startTicking() {
  tickTimer = setInterval(() => {
    const now = Date.now()
    logs.value.forEach(log => {
      // Only tick for entries still in processing (no status_code yet) and still pending
      if (log.id < 0 && !log.status_code && log._start_time) {
        tickingLatencies.value[log.id] = now - log._start_time
      }
    })
  }, 100)
}

// Fallback: periodic refresh to catch any events missed during SSE reconnection
function startPolling() {
  pollTimer = setInterval(() => {
    if (!loading.value) fetchLogs()
  }, 15000)
}

function subscribeSSE() {
  const authHeader = localStorage.getItem('access_token') ? 'Bearer ' + localStorage.getItem('access_token') : ''
  sseAbort = new AbortController()
  
  const fetchSSE = async () => {
    try {
      const resp = await fetch('/api/logs/stream?v=' + Date.now(), {
        headers: { Authorization: authHeader },
        signal: sseAbort.signal,
      })
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop()

        for (const line of lines) {
          const m = line.match(/^event: (.*)\ndata: (.*)$/s)
          if (!m) continue
          const data = JSON.parse(m[2])
          
          if (m[1] === 'log_new') {
            logs.value.unshift({ ...data, _start_time: Date.now() })
            if (logs.value.length > limit.value) logs.value.pop()
          } else if (m[1] === 'log_update') {
            const oldId = data.id
            const idx = logs.value.findIndex(l => l.id === oldId)
            if (idx >= 0) {
              const item = { ...logs.value[idx], ...data }
              if (data._real_id != null) {
                const newId = data._real_id
                item.id = newId
                // Migrate UI states
                if (expanded.value[oldId]) { expanded.value[newId] = true; delete expanded.value[oldId] }
                if (fullContent.value[oldId]) { fullContent.value[newId] = { ...fullContent.value[oldId], ...data, id: newId }; delete fullContent.value[oldId] }
                else { fullContent.value[newId] = { ...data, id: newId } }
                if (showFullReqState.value[oldId]) { showFullReqState.value[newId] = showFullReqState.value[oldId]; delete showFullReqState.value[oldId] }
                if (showFullResState.value[oldId]) { showFullResState.value[newId] = showFullResState.value[oldId]; delete showFullResState.value[oldId] }
                delete tickingLatencies.value[oldId]
              }
              logs.value[idx] = item
            }
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.warn('SSE disconnected, retrying in 3s...', e)
        setTimeout(subscribeSSE, 3000)
      }
    }
  }
  fetchSSE()
}

onMounted(() => {
  fetchLogs()
  subscribeSSE()
  startTicking()
  startPolling()
})

onUnmounted(() => {
  if (sseAbort) sseAbort.abort()
  if (tickTimer) clearInterval(tickTimer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.logs-page { animation: fade-in 0.3s ease-out; }

/* Tabs */
.tabs { display: flex; border-bottom: 1px solid var(--color-border); gap: 24px; }
.tab-btn { padding: 8px 4px; font-size: 14px; color: var(--color-text-dim); background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.2s; }
.tab-btn.active { color: var(--color-accent); border-bottom-color: var(--color-accent); font-weight: 600; }

/* Buttons & Inputs */
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-bg-card); color: var(--color-text); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); border-color: var(--color-accent); color: white; }
.btn-danger { color: #ef4444; border-color: rgba(239, 68, 68, 0.2); background: rgba(239, 68, 68, 0.05); }
.btn-danger:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }
.btn-sm { padding: 6px 10px; font-size: 12px; }
.select-sm { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text); font-size: 12px; padding: 4px 8px; outline: none; }

/* Card */
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 12px); padding: 20px; overflow: hidden; }

/* Table */
.table-wrap { overflow-x: auto; min-height: 400px; }
.logs-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
thead { position: sticky; top: 0; z-index: 10; background: var(--color-bg); }
th { text-align: left; padding: 12px; color: var(--color-text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; white-space: nowrap; border-bottom: 1px solid var(--color-border-strong); }
td { padding: 12px; border-bottom: 1px solid var(--color-border); white-space: nowrap; }

.col-expand { width: 35px; min-width: 35px; }
.col-time { width: 150px; min-width: 120px; }
.col-model { min-width: 80px; max-width: 100%; }
.col-provider, .col-client { width: 110px; min-width: 90px; }
.col-status { width: 80px; min-width: 60px; }
.col-ttft, .col-latency { width: 75px; min-width: 60px; }
.col-tokens { width: 90px; min-width: 70px; }

.log-row { cursor: pointer; transition: background 0.15s; }
.log-row:hover { background: rgba(255,255,255,0.02); }
.row-expanded { background: rgba(255,255,255,0.03); }

.expand-icon { display: inline-block; font-size: 10px; transition: transform 0.2s; color: var(--color-text-dim); }
.expand-icon.rotated { transform: rotate(90deg); color: var(--color-accent); }

.expand-row td { white-space: normal; padding: 0; }
.expand-content { padding: 20px; background: var(--color-bg-card); border-bottom: 1px solid var(--color-border); width: 100%; max-width: 100%; box-sizing: border-box; overflow-x: auto; }
.expand-header-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; padding: 10px 14px; background: var(--color-bg-input); border-radius: 6px; border: 1px solid var(--color-border); }
.summary-item { font-size: 12px; color: var(--color-text-dim); }

.content-block { min-height: 60px; }
.content-label { font-size: 11px; font-weight: 700; color: var(--color-accent); text-transform: uppercase; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; }
.collapse-btn { background: transparent; border: none; color: var(--color-text-dim); cursor: pointer; padding: 2px 4px; font-family: monospace; }
.content-toggle { font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--color-border); background: var(--color-bg-card); color: var(--color-text-dim); cursor: pointer; }

.content-text { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 6px; padding: 14px; font-family: 'Fira Code', monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--color-text); opacity: 0.9; min-height: 40px; }
.text-body { background: var(--color-bg-input); border: 1px solid var(--color-border); border-radius: 6px; padding: 14px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--color-text); min-height: 40px; }
.text-msg { margin-bottom: 12px; }
.text-role { font-weight: 700; color: var(--color-accent); margin-right: 8px; }

/* Utilities & Badges */
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid transparent; }
.badge-green { background: rgba(34, 197, 94, 0.1); color: #4ade80; border-color: rgba(34, 197, 94, 0.2); }
.badge-red { background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239, 68, 68, 0.2); }
.badge-blue { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }

.text-dim { color: var(--color-text-dim); }
.mono { font-family: var(--font-mono); }
.truncate-cell { overflow: hidden; text-overflow: ellipsis; }

.loading-state { text-align: center; padding: 40px; color: var(--color-text-dim); }
.empty-state { text-align: center; padding: 40px; color: var(--color-text-dim); font-size: 14px; }

@keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 768px) {
  .logs-table { font-size: 11px; }
  .col-time, .col-provider, .col-client { display: none; }
}
</style>
