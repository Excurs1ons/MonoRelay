<template>
  <div v-if="loading" class="loading"><div class="spinner"></div></div>
  <template v-else>
    <!-- API 地址卡片 -->
    <div class="api-cards">
      <div class="api-card">
        <div class="api-card-header">
          <span class="api-card-title">OpenAI API</span>
          <button class="btn-copy" @click="copyToClipboard(openaiUrl)" :class="{ copied: copiedOpenAI }">
            <Copy :size="14" v-if="!copiedOpenAI" />
            <Check :size="14" v-else />
            {{ copiedOpenAI ? $t('dashboard.copied') : $t('dashboard.copy') }}
          </button>
        </div>
        <div class="api-url">{{ openaiUrl }}</div>
        <div class="api-hint">/v1/chat/completions</div>
      </div>
      <div class="api-card">
        <div class="api-card-header">
          <span class="api-card-title">Anthropic API</span>
          <button class="btn-copy" @click="copyToClipboard(anthropicUrl, 'anthropic')" :class="{ copied: copiedAnthropic }">
            <Copy :size="14" v-if="!copiedAnthropic" />
            <Check :size="14" v-else />
            {{ copiedAnthropic ? $t('dashboard.copied') : $t('dashboard.copy') }}
          </button>
        </div>
        <div class="api-url">{{ anthropicUrl }}</div>
        <div class="api-hint">/v1/messages</div>
      </div>
    </div>

    <div class="flex-between mb-4">
      <h2 class="section-title">统计</h2>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">{{ $t('dashboard.totalRequests') }}</span>
          <TrendingUp :size="18" class="stat-icon accent" />
        </div>
        <div class="stat-value accent">{{ formatNum(stats.totalRequests) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">{{ $t('dashboard.errorRate') }}</span>
          <AlertTriangle :size="18" :class="['stat-icon', stats.errorRate > 0.1 ? 'red' : 'green']" />
        </div>
        <div class="stat-value" :class="stats.errorRate > 0.1 ? 'red' : 'green'">
          {{ (stats.errorRate * 100).toFixed(1) }}%
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">{{ $t('dashboard.tokenUsage') }}</span>
          <ArrowLeftRight :size="18" class="stat-icon info" />
        </div>
        <div class="stat-value">{{ formatToken(stats.inputTokens + stats.outputTokens) }}</div>
        <div class="stat-detail">{{ $t('dashboard.inputTokens') }}: {{ formatToken(stats.inputTokens) }} / {{ $t('dashboard.outputTokens') }}: {{ formatToken(stats.outputTokens) }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">{{ $t('dashboard.modelStats') }}</div>
      <div v-if="modelList.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ $t('dashboard.model') }}</th>
              <th class="text-right">{{ $t('dashboard.requests') }}</th>
              <th class="text-right">{{ $t('dashboard.inputTokens') }}</th>
              <th class="text-right">{{ $t('dashboard.outputTokens') }}</th>
              <th class="text-right">{{ $t('dashboard.firstToken') }}</th>
              <th class="text-right">{{ $t('dashboard.outputSpeed') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in modelList" :key="m.name">
              <td class="mono">{{ m.name }}</td>
              <td class="text-right">{{ m.requests }}</td>
              <td class="text-right">{{ formatToken(m.total_tokens_in || m.input_tokens) }}</td>
              <td class="text-right">{{ formatToken(m.total_tokens_out || m.output_tokens) }}</td>
              <td class="text-right">{{ m.avg_first_token_ms?.toFixed(0) || '-' }}ms</td>
              <td class="text-right">{{ m.avg_speed_tps?.toFixed(1) || '-' }} t/s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">{{ $t('dashboard.noData') }}</div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/api'
import { TrendingUp, AlertTriangle, ArrowLeftRight, BarChart3, Zap, Clock, Copy, Check } from 'lucide-vue-next'

const loading = ref(true)
const rawStats = ref(null)
const serverInfo = ref({ local_ip: '127.0.0.1', port: 8787 })
const copiedOpenAI = ref(false)
const copiedAnthropic = ref(false)

const openaiUrl = computed(() => serverInfo.value.base_url || `http://${serverInfo.value.local_ip}:${serverInfo.value.port}/v1`)
const anthropicUrl = computed(() => serverInfo.value.base_url?.replace('/v1', '') || `http://${serverInfo.value.local_ip}:${serverInfo.value.port}`)

async function copyToClipboard(text, type) {
  try {
    await navigator.clipboard.writeText(text)
    if (type === 'anthropic') {
      copiedAnthropic.value = true
      setTimeout(() => copiedAnthropic.value = false, 2000)
    } else {
      copiedOpenAI.value = true
      setTimeout(() => copiedOpenAI.value = false, 2000)
    }
  } catch (e) {
    console.error('Copy failed:', e)
  }
}
let timer = null

const stats = computed(() => {
  const s = rawStats.value
  if (!s) return { totalRequests: 0, errorRate: 0, inputTokens: 0, outputTokens: 0 }
  const p = s.persistent || {}
  const m = s.in_memory || {}
  return {
    totalRequests: p.total_requests || m.total_requests || 0,
    errorRate: p.error_rate ?? m.error_rate ?? 0,
    inputTokens: m.input_tokens || 0,
    outputTokens: m.output_tokens || 0,
  }
})

const modelList = computed(() => {
  const models = rawStats.value?.model_stats || rawStats.value?.models || {}
  return Object.entries(models).map(([name, data]) => ({ name, ...data }))
})

function formatNum(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n?.toString() || '0'
}

function formatToken(n) {
  if (!n) return '0'
  return n.toLocaleString()
}

async function fetch() {
  try {
    rawStats.value = await api.getStats()
    const info = await api.getInfo()
    serverInfo.value = { local_ip: info.local_ip || '127.0.0.1', port: info.port || 8787 }
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function resetStats() {
  if (!confirm('确定清空所有统计数据？')) return
  try {
    await api.resetStats()
    await fetch()
  } catch (e) { console.error(e) }
}

onMounted(() => { fetch(); timer = setInterval(fetch, 30000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.api-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
.api-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 16px; transition: all 0.2s; }
.api-card:hover { border-color: var(--color-accent); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.api-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.api-card-title { font-size: 14px; font-weight: 600; color: var(--color-text); }
.btn-copy { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-dim); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.btn-copy:hover { border-color: var(--color-accent); color: var(--color-accent); }
.btn-copy.copied { border-color: var(--color-green); color: var(--color-green); }
.api-url { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px; color: var(--color-accent); word-break: break-all; margin-bottom: 6px; }
.api-hint { font-size: 11px; color: var(--color-text-dim); }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 16px; transition: all 0.2s; }
.stat-card:hover { border-color: var(--color-accent); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.stat-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.stat-label { font-size: 12px; color: var(--color-text-dim); }
.stat-icon { opacity: 0.6; }
.stat-icon.accent { color: var(--color-accent); }
.stat-icon.green { color: var(--color-green); }
.stat-icon.red { color: var(--color-red); }
.stat-icon.info { color: var(--color-info); }
.stat-value { font-size: 24px; font-weight: 700; }
.stat-value.accent { color: var(--color-accent); }
.stat-value.green { color: var(--color-green); }
.stat-value.red { color: var(--color-red); }
.stat-detail { font-size: 11px; color: var(--color-text-dim); margin-top: 4px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--color-text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--color-border); }
th.text-right { text-align: right; }
td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
td.text-right { text-align: right; }
tr:last-child td { border-bottom: none; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
.empty { text-align: center; padding: 30px; color: var(--color-text-dim); font-size: 13px; }
.loading { text-align: center; padding: 40px; color: var(--color-text-dim); }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border); border-top-color: var(--color-accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
