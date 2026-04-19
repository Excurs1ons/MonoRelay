<template>
  <div class="users-page">
    <div class="flex-between mb-4">
      <h2 class="section-title">{{ $t('users.title', '用户管理') }}</h2>
      <button class="btn btn-ghost btn-sm" @click="fetchUsers">
        <RefreshCw :size="14" :class="{ 'spin': loading }" />
      </button>
    </div>

    <div v-if="error" class="error-msg mb-4">
      {{ error }}
    </div>

    <div class="card overflow-hidden">
      <table class="users-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>{{ $t('users.username', '用户名') }}</th>
            <th>{{ $t('users.email', '邮箱') }}</th>
            <th>{{ $t('users.status', '状态') }}</th>
            <th>{{ $t('users.role', '角色') }}</th>
            <th>{{ $t('users.created', '注册时间') }}</th>
            <th>{{ $t('users.actions', '操作') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td class="mono">{{ user.username }}</td>
            <td>{{ user.email }}</td>
            <td>
              <span :class="['badge', user.is_active ? 'badge-success' : 'badge-danger']">
                {{ user.is_active ? $t('users.active', '活跃') : $t('users.disabled', '禁用') }}
              </span>
            </td>
            <td>
              <span v-if="user.is_admin" class="badge badge-admin">
                <Shield :size="10" class="mr-1" /> 管理员
              </span>
              <span v-else class="badge badge-user">
                <User :size="10" class="mr-1" /> 普通用户
              </span>
            </td>
            <td class="text-xs text-dim">{{ formatDate(user.created_at) }}</td>
            <td>
              <div class="flex gap-2">
                <button 
                  class="btn btn-ghost btn-xs" 
                  @click="toggleActive(user)"
                  :title="user.is_active ? '禁用' : '启用'"
                >
                  <UserX v-if="user.is_active" :size="14" />
                  <UserCheck v-else :size="14" />
                </button>
                <button 
                  class="btn btn-ghost btn-xs" 
                  @click="toggleAdmin(user)"
                  :title="user.is_admin ? '取消管理员' : '设为管理员'"
                >
                  <ShieldOff v-if="user.is_admin" :size="14" />
                  <Shield v-else :size="14" />
                </button>
                <button 
                  v-if="user.id !== currentUserId"
                  class="btn btn-ghost btn-xs text-red" 
                  @click="confirmDelete(user)"
                  title="删除"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="users.length === 0 && !loading">
            <td colspan="7" class="text-center py-8 text-dim">
              {{ $t('common.noData', '暂无数据') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { RefreshCw, UserX, UserCheck, Shield, ShieldOff, Trash2, User } from 'lucide-vue-next'

const users = ref([])
const loading = ref(false)
const error = ref('')
const currentUserId = ref(null)
const toast = useToastStore()

async function fetchMe() {
  try {
    const me = await api.getMe()
    currentUserId.value = me.id
  } catch (e) {
    console.error(e)
  }
}

async function fetchUsers() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getUsers()
    users.value = data.users || []
  } catch (e) {
    error.value = e.message || '获取用户列表失败'
    if (e.message === 'Unauthorized') {
      window.location.href = '/'
    }
  } finally {
    loading.value = false
  }
}

async function toggleActive(user) {
  try {
    await api.updateUser(user.id, { is_active: !user.is_active })
    user.is_active = !user.is_active
    toast.success(`${user.username} 已${user.is_active ? '启用' : '禁用'}`)
  } catch (e) {
    toast.error(e.message)
  }
}

async function toggleAdmin(user) {
  try {
    await api.updateUser(user.id, { is_admin: !user.is_admin })
    user.is_admin = !user.is_admin
    toast.success(`${user.username} 角色已更新`)
  } catch (e) {
    toast.error(e.message)
  }
}

async function confirmDelete(user) {
  if (!confirm(`确定要删除用户 ${user.username} 吗？此操作不可逆。`)) return
  
  try {
    await api.deleteUser(user.id)
    users.value = users.value.filter(u => u.id !== user.id)
    toast.success(`用户 ${user.username} 已删除`)
  } catch (e) {
    toast.error(e.message)
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString()
}

onMounted(async () => {
  await fetchMe()
  await fetchUsers()
})
</script>

<style scoped>
.users-page {
  padding: 0;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.users-table th {
  text-align: left;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
}

.users-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.users-table tr:last-child td {
  border-bottom: none;
}

.users-table tr:hover {
  background: rgba(255, 255, 255, 0.01);
}

.badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-success { background: rgba(34, 197, 94, 0.15); color: #4ade80; }
.badge-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.badge-admin { 
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2)); 
  color: #a78bfa; 
  border: 1px solid rgba(139, 92, 246, 0.3);
}
.badge-user { 
  background: rgba(255, 255, 255, 0.05); 
  color: var(--color-text-dim);
  border: 1px solid var(--color-border);
}

.mr-1 {
  margin-right: 4px;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.text-red {
  color: #ef4444;
}

.text-red:hover {
  color: #f87171;
  border-color: #f87171;
}

.overflow-hidden {
  overflow: hidden;
}

@media (max-width: 600px) {
  .users-page {
    padding: 0;
  }
  .users-table {
    display: block;
    overflow-x: auto;
  }
}
</style>
