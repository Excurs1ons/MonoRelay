<template>
  <div class="dashboard">
    <div v-if="loading" class="loading-state">
      <RefreshCw class="spin" :size="32" />
    </div>

    <template v-else>
      <!-- Stats Overview -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon"><Activity :size="20" /></div>
          <div class="stat-info">
            <div class="label">{{ isAdmin ? '全站请求总数' : '我的请求总数' }}</div>
            <div class="value">{{ stats.total_requests || 0 }}</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon success"><CheckCircle :size="20" /></div>
          <div class="stat-info">
            <div class="label">平均成功率</div>
            <div class="value">{{ ((1 - (stats.total_errors / (stats.total_requests || 1))) * 100).toFixed(1) }}%</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon warning"><CreditCard :size="20" /></div>
          <div class="stat-info">
            <div class="label">{{ isAdmin ? '全站预估支出' : '当前余额' }}</div>
            <div class="value">{{ isAdmin ? '$' + (stats.estimated_total_cost || 0).toFixed(4) : '$' + (userBalance || 0).toFixed(2) }}</div>
          </div>
        </div>
        <div v-if="isAdmin" class="stat-card">
          <div class="stat-icon"><Globe :size="20" /></div>
          <div class="stat-info">
            <div class="label">活跃提供商</div>
            <div class="value">{{ Object.keys(stats.requests_by_provider || {}).length }}</div>
          </div>
        </div>
      </div>

      <div class="dashboard-grid">
        <!-- Model Usage Chart (Placeholder or List) -->
        <div class="card chart-card">
          <h3 class="card-title">热门模型分布</h3>
          <div v-if="Object.keys(stats.requests_by_model || {}).length" class="model-list">
            <div v-for="(count, model) in sortedModels" :key="model" class="model-item">
              <div class="model-info">
                <span class="model-name mono">{{ model }}</span>
                <span class="model-count">{{ count }} 次</span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: (count / stats.total_requests * 100) + '%' }"></div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">暂无模型使用数据</div>
        </div>

        <!-- Provider Status (Admin Only) -->
        <div v-if="isAdmin" class="card">
          <h3 class="card-title">提供商健康度</h3>
          <div class="provider-grid">
            <div v-for="(count, provider) in stats.requests_by_provider" :key="provider" class="provider-status-item">
              <div class="flex-between mb-1">
                <span class="font-bold">{{ provider }}</span>
                <span class="text-xs text-dim">{{ count }} reqs</span>
              </div>
              <div class="text-xs">
                错误率: 
                <span :class="getErrorClass(provider)">
                  {{ ((stats.errors_by_provider[provider] || 0) / count * 100).toFixed(1) }}%
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Quick Access for User -->
        <div v-if="!isAdmin" class="card">
          <h3 class="card-title">快捷操作</h3>
          <div class="quick-actions">
            <router-link to="/keys" class="action-btn">
              <Plus :size="16" /> 创建新令牌
            </router-link>
            <router-link to="/logs" class="action-btn secondary">
              <Activity :size="16" /> 查看最近日志
            </router-link>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api'
import { 
  Activity, CheckCircle, CreditCard, Globe, 
  RefreshCw, Plus 
} from 'lucide-vue-next'

const loading = ref(true)
const stats = ref({})
const user = ref(null)
const userBalance = ref(0)

const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.is_admin)

const sortedModels = computed(() => {
  const m = stats.value.requests_by_model || {}
  return Object.fromEntries(
    Object.entries(m).sort(([,a],[,b]) => b - a).slice(0, 5)
  )
})

async function fetchData() {
  loading.value = true
  try {
    user.value = await api.getMe()
    if (isAdmin.value) {
      stats.value = await api.getStats()
    } else {
      const userStats = await api.getUserStats()
      stats.value = {
        total_requests: userStats.total_requests,
        total_errors: 0, # To be improved in backend
        requests_by_model: userStats.requests_by_model || {}
      }
      userBalance.value = userStats.balance
    }
  } catch (e) {
    console.error('Fetch dashboard data failed:', e)
  } finally {
    loading.value = false
  }
}

function getErrorClass(provider) {
  const rate = (stats.value.errors_by_provider[provider] || 0) / stats.value.requests_by_provider[provider]
  if (rate > 0.2) return 'text-red-500'
  if (rate > 0.05) return 'text-orange-500'
  return 'text-green-500'
}

onMounted(fetchData)
</script>

<style scoped>
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 24px; }
.stat-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; padding: 20px; display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 40px; height: 40px; border-radius: 10px; background: rgba(249, 115, 22, 0.1); color: var(--color-accent); display: flex; align-items: center; justify-content: center; }
.stat-icon.success { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.stat-icon.warning { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }

.stat-info .label { font-size: 12px; color: var(--color-text-dim); margin-bottom: 4px; }
.stat-info .value { font-size: 20px; font-weight: 700; }

.dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
@media (max-width: 1024px) { .dashboard-grid { grid-template-columns: 1fr; } }

.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; padding: 20px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 20px; color: var(--color-accent); }

.model-list { display: flex; flex-direction: column; gap: 16px; }
.model-item { display: flex; flex-direction: column; gap: 6px; }
.model-info { display: flex; justify-content: space-between; font-size: 12px; }
.progress-bar { height: 6px; background: var(--color-bg-input); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-accent); border-radius: 3px; transition: width 0.3s; }

.provider-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
.provider-status-item { padding: 10px; background: var(--color-bg-input); border-radius: 8px; border: 1px solid var(--color-border); }

.quick-actions { display: flex; flex-direction: column; gap: 10px; }
.action-btn { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; border-radius: 8px; background: var(--color-accent); color: #fff; text-decoration: none; font-weight: 600; font-size: 13px; transition: all 0.2s; }
.action-btn.secondary { background: var(--color-bg-input); border: 1px solid var(--color-border); color: var(--color-text); }
.action-btn:hover { transform: translateY(-1px); filter: brightness(1.1); }

.loading-state { display: flex; align-items: center; justify-content: center; padding: 100px; color: var(--color-text-dim); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.empty-state { text-align: center; padding: 40px; color: var(--color-text-dim); font-size: 13px; }
</style>
