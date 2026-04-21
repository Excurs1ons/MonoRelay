<template>
  <div class="redemptions-page">
    <div class="flex-between mb-6">
      <div>
        <h2 class="section-title">兑换码管理</h2>
        <p class="text-dim text-sm">生成并管理用于账户充值的兑换码</p>
      </div>
      <button class="btn btn-primary" @click="showCreateModal = true">
        <Plus :size="16" class="mr-1" /> 生成兑换码
      </button>
    </div>

    <div v-if="loading" class="loading"><RefreshCw class="spin" /></div>

    <div v-else class="card overflow-hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>兑换码</th>
              <th class="text-right">金额 (Credits)</th>
              <th class="text-center">状态</th>
              <th>使用者</th>
              <th>使用时间</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="code in codes" :key="code.id">
              <td class="mono font-bold">{{ code.code }}</td>
              <td class="text-right mono text-accent">${{ code.amount.toFixed(2) }}</td>
              <td class="text-center">
                <span class="badge" :class="code.is_used ? 'badge-gray' : 'badge-green'">
                  {{ code.is_used ? '已使用' : '未使用' }}
                </span>
              </td>
              <td><span v-if="code.used_by" class="badge badge-outline">#{{ code.used_by }}</span><span v-else>-</span></td>
              <td class="text-xs text-dim">{{ code.used_at ? formatDate(code.used_at) : '-' }}</td>
              <td class="text-xs text-dim">{{ formatDate(code.created_at) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!codes.length" class="empty-state">暂无兑换码记录</div>
      </div>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-card">
        <h3 class="mb-4">批量生成兑换码</h3>
        <div class="form-group">
          <label>单个金额 (Credits)</label>
          <input v-model.number="form.amount" type="number" step="0.01" class="form-input" placeholder="例如: 10.00" />
        </div>
        <div class="form-group">
          <label>生成数量</label>
          <input v-model.number="form.count" type="number" class="form-input" placeholder="例如: 5" />
        </div>
        <div class="form-group">
          <label>前缀</label>
          <input v-model="form.prefix" type="text" class="form-input" placeholder="PRISMA-" />
        </div>
        <div class="modal-actions mt-6">
          <button class="btn btn-ghost" @click="showCreateModal = false">取消</button>
          <button class="btn btn-primary" :disabled="creating || !form.amount" @click="handleCreate">
            {{ creating ? '正在生成...' : '立即生成' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { Plus, RefreshCw, Ticket } from 'lucide-vue-next'

const loading = ref(true)
const creating = ref(false)
const codes = ref([])
const showCreateModal = ref(false)
const toast = useToastStore()

const form = ref({
  amount: 5.0,
  count: 1,
  prefix: 'PRISMA-'
})

async function fetchCodes() {
  loading.value = true
  try {
    codes.value = await api.getRedemptionCodes()
  } catch (e) {
    toast.error('获取列表失败')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  creating.value = true
  try {
    await api.createRedemptionCodes(form.value.amount, form.value.count, form.value.prefix)
    toast.success(`成功生成 ${form.value.count} 个兑换码`)
    showCreateModal.value = false
    fetchCodes()
  } catch (e) {
    toast.error('生成失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleString()
}

onMounted(fetchCodes)
</script>

<style scoped>
.redemptions-page { padding: 0; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 14px 16px; border-bottom: 1px solid var(--color-border); color: var(--color-text-dim); font-size: 11px; text-transform: uppercase; }
td { padding: 14px 16px; border-bottom: 1px solid var(--color-border); }
tr:last-child td { border-bottom: none; }
.badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; }
.badge-green { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.badge-gray { background: rgba(255, 255, 255, 0.05); color: var(--color-text-dim); }
.badge-outline { border: 1px solid var(--color-border); color: var(--color-text-dim); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 16px; padding: 24px; width: 100%; max-width: 400px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 12px; }
.overflow-hidden { overflow: hidden; }
.empty-state { text-align: center; padding: 40px; color: var(--color-text-dim); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
