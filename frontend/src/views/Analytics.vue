<template>
  <div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">总请求数</span>
          <BarChart3 :size="18" class="stat-icon accent" />
        </div>
        <div class="stat-value accent">{{ formatNum(overview?.total_requests || 0) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">总成本</span>
          <DollarSign :size="18" class="stat-icon info" />
        </div>
        <div class="stat-value">${{ (overview?.total_cost || 0).toFixed(4) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">输入Token</span>
          <ArrowDown :size="18" class="stat-icon green" />
        </div>
        <div class="stat-value">{{ formatNum(overview?.total_tokens?.input || 0) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-label">输出Token</span>
          <ArrowUp :size="18" class="stat-icon yellow" />
        </div>
        <div class="stat-value">{{ formatNum(overview?.total_tokens?.output || 0) }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">提供商分布</div>
      <div v-if="overview?.by_provider" class="provider-chart">
        <div v-for="(data, name) in overview.by_provider" :key="name" class="provider-bar">
          <div class="bar-label">{{ name }}</div>
          <div class="bar-track">
            <div class="bar-fill" :style="{ width: getProviderPercent(data.requests) + '%' }"></div>
          </div>
          <div class="bar-value">{{ data.requests }} 次</div>
        </div>
      </div>
      <div v-else class="empty">暂无数据</div>
    </div>

    <div class="card">
      <div class="card-title">慢查询 (TOP 10)</div>
      <div v-if="slowQueries?.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>模型</th>
              <th>提供商</th>
              <th class="text-right">延迟</th>
              <th class="text-right">首Token</th>
              <th class="text-right">速度</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in slowQueries" :key="q.id">
              <td class="mono">{{ q.model }}</td>
              <td>{{ q.provider }}</td>
              <td class="text-right">{{ q.latency_ms?.toFixed(0) || '-' }}ms</td>
              <td class="text-right">{{ q.first_token_ms?.toFixed(0) || '-' }}ms</td>
              <td class="text-right">{{ q.speed_tps?.toFixed(1) || '-' }} t/s</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">暂无慢查询数据</div>
    </div>

    <div class="card">
      <div class="card-title">成本分布</div>
      <div v-if="costDist?.by_provider" class="cost-grid">
        <div v-for="item in costDist.by_provider" :key="item.provider" class="cost-item">
          <div class="cost-name">{{ item.provider }}</div>
          <div class="cost-value">${{ (item.cost || 0).toFixed(4) }}</div>
          <div class="cost-percent">{{ item.percentage }}%</div>
        </div>
      </div>
      <div v-else class="empty">暂无成本数据</div>
    </div>

    <div class="card">
      <div class="card-title">模型统计</div>
      <div v-if="overview?.by_model" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>模型</th>
              <th class="text-right">请求数</th>
              <th class="text-right">成本</th>
              <th class="text-right">Token</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(data, name) in overview.by_model" :key="name">
              <td class="mono">{{ name }}</td>
              <td class="text-right">{{ data.requests }}</td>
              <td class="text-right">${{ (data.cost || 0).toFixed(4) }}</td>
              <td class="text-right">{{ formatNum(data.tokens || 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">暂无模型数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/api'
import { BarChart3, DollarSign, ArrowDown, ArrowUp } from 'lucide-vue-next'

const loading = ref(true)
const overview = ref(null)
const slowQueries = ref([])
const costDist = ref(null)
let timer = null

function formatNum(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n?.toString() || '0'
}

function getProviderPercent(requests) {
  if (!overview.value?.total_requests) return 0
  return ((requests / overview.value.total_requests) * 100).toFixed(1)
}

function getCostPercent(cost) {
  if (!costDist.value?.total_cost) return 0
  return (cost / costDist.value.total_cost * 100).toFixed(1)
}

async function fetchData() {
  try {
    const [ov, sq, cd] = await Promise.all([
      api.getAnalyticsOverview(),
      api.getAnalyticsSlowQueries(10),
      api.getAnalyticsCostDistribution()
    ])
    overview.value = ov
    slowQueries.value = sq?.slow_queries || []
    costDist.value = cd
    console.log('API responses - overview:', ov, 'slowQueries:', sq, 'costDist:', cd)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => { fetchData(); timer = setInterval(fetchData, 60000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 16px; }
.stat-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.stat-label { font-size: 12px; color: var(--color-text-dim); }
.stat-icon { opacity: 0.6; }
.stat-icon.accent { color: var(--color-accent); }
.stat-icon.green { color: var(--color-green); }
.stat-icon.yellow { color: var(--color-yellow); }
.stat-icon.info { color: var(--color-info); }
.stat-value { font-size: 22px; font-weight: 700; }
.stat-value.accent { color: var(--color-accent); }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; margin-bottom: 16px; }
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
.provider-chart { display: flex; flex-direction: column; gap: 8px; }
.provider-bar { display: flex; align-items: center; gap: 12px; }
.bar-label { width: 80px; font-size: 12px; color: var(--color-text-dim); }
.bar-track { flex: 1; height: 8px; background: var(--color-bg-input); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--color-accent); border-radius: 4px; transition: width 0.3s; }
.bar-value { width: 60px; font-size: 12px; text-align: right; }
.cost-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.cost-item { background: var(--color-bg-input); border-radius: 8px; padding: 12px; text-align: center; }
.cost-name { font-size: 12px; color: var(--color-text-dim); margin-bottom: 4px; }
.cost-value { font-size: 18px; font-weight: 700; color: var(--color-accent); }
.cost-percent { font-size: 11px; color: var(--color-text-dim); margin-top: 2px; }
</style>
