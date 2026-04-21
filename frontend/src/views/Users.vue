<template>
  <div class="users-page">
    <div class="flex-between mb-6">
      <div>
        <h2 class="section-title">用户管理</h2>
        <p class="text-dim text-sm">管理平台租户、分配额度及调整权限</p>
      </div>
      <button class="btn btn-primary" @click="toast.info('手动注册暂未开放，请引导用户自助注册')">
        <UserPlus :size="16" class="mr-1" /> 手动新增用户
      </button>
    </div>

    <div v-if="loading" class="loading"><RefreshCw class="spin" /></div>

    <div v-else class="card overflow-hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>角色</th>
              <th class="text-right">余额</th>
              <th>创建时间</th>
              <th class="text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td class="text-dim mono">#{{ user.id }}</td>
              <td class="font-bold">{{ user.username }}</td>
              <td><span class="badge" :class="user.role === 'admin' ? 'badge-purple' : 'badge-gray'">{{ user.role }}</span></td>
              <td class="text-right mono font-bold text-accent">${{ user.balance.toFixed(2) }}</td>
              <td class="text-xs text-dim">{{ formatDate(user.created_at) }}</td>
              <td class="text-right">
                <div class="flex justify-end gap-2">
                  <button class="btn btn-xs" @click="editBalance(user)" title="充值/扣费"><CreditCard :size="12" /></button>
                  <button class="btn btn-xs btn-danger" @click="confirmDelete(user)" title="删除用户"><Trash2 :size="12" /></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Edit Balance Modal -->
    <div v-if="showBalanceModal" class="modal-overlay" @click.self="showBalanceModal = false">
      <div class="modal-card">
        <h3 class="mb-2">调整余额: {{ selectedUser?.username }}</h3>
        <p class="text-xs text-dim mb-4">正数为增加额度，负数为扣除额度。</p>
        <div class="form-group">
          <label>当前余额: ${{ selectedUser?.balance.toFixed(2) }}</label>
          <input v-model.number="balanceAdjustment" type="number" step="0.01" class="form-input" placeholder="输入调整金额" @keyup.enter="updateBalance" />
        </div>
        <div class="modal-actions mt-6">
          <button class="btn btn-ghost" @click="showBalanceModal = false">取消</button>
          <button class="btn btn-primary" :disabled="!balanceAdjustment" @click="updateBalance">确认调整</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { UserPlus, RefreshCw, CreditCard, Trash2 } from 'lucide-vue-next'

const loading = ref(true)
const users = ref([])
const showBalanceModal = ref(false)
const selectedUser = ref(null)
const balanceAdjustment = ref(0)
const toast = useToastStore()

async function fetchUsers() {
  loading.value = true
  try {
    users.value = await api.getUsers()
  } catch (e) {
    toast.error('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

function editBalance(user) {
  selectedUser.value = user
  balanceAdjustment.value = 0
  showBalanceModal.value = true
}

async function updateBalance() {
  try {
    await api.updateUserBalance(selectedUser.value.id, balanceAdjustment.value)
    toast.success('余额调整成功')
    showBalanceModal.value = false
    fetchUsers()
  } catch (e) {
    toast.error('操作失败: ' + e.message)
  }
}

async function confirmDelete(user) {
  if (!confirm(`警告：确定彻底删除用户 ${user.username} (ID: ${user.id})？\n该用户的所有 API 令牌和记录将无法再通过控制台管理。`)) return
  try {
    await api.deleteUser(user.id)
    toast.success('用户已删除')
    fetchUsers()
  } catch (e) {
    toast.error('删除失败: ' + e.message)
  }
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleString()
}

onMounted(fetchUsers)
</script>

<style scoped>
.users-page { padding: 0; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 14px 16px; border-bottom: 1px solid var(--color-border); color: var(--color-text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
td { padding: 14px 16px; border-bottom: 1px solid var(--color-border); }
tr:last-child td { border-bottom: none; }
.badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase; }
.badge-purple { background: rgba(168, 85, 247, 0.15); color: #a855f7; }
.badge-gray { background: rgba(255,255,255,0.05); color: var(--color-text-dim); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 16px; padding: 24px; width: 100%; max-width: 400px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
.modal-actions { display: flex; justify-content: flex-end; gap: 12px; }
.overflow-hidden { overflow: hidden; }
.btn-xs { padding: 4px 8px; font-size: 11px; }
</style>
