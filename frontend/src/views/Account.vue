<template>
  <div class="account-page">
    <h2 class="section-title">账户管理</h2>

    <div class="account-content" v-if="user">
      <!-- Balance Card -->
      <div class="card balance-card mb-4">
        <div class="flex-between">
          <div>
            <div class="card-title">可用余额 (Credits)</div>
            <div class="balance-value mono">${{ user.balance?.toFixed(2) || '0.00' }}</div>
          </div>
          <div class="balance-icon">
            <CreditCard :size="32" />
          </div>
        </div>
      </div>

      <!-- Redemption Card -->
      <div class="card mb-4">
        <h3 class="card-title flex items-center gap-2">
          <Ticket :size="16" /> 额度兑换
        </h3>
        <div class="flex gap-2">
          <input 
            v-model="redemptionCode" 
            type="text" 
            class="form-input mono" 
            placeholder="输入兑换码 (PRISMA-XXXX...)"
            @keyup.enter="handleRedeem"
          />
          <button 
            class="btn btn-primary" 
            :disabled="redeeming || !redemptionCode" 
            @click="handleRedeem"
          >
            {{ redeeming ? '正在兑换...' : '确认兑换' }}
          </button>
        </div>
        <p class="help-text mt-2">兑换成功后，额度将立即添加到您的账户余额。</p>
      </div>

      <!-- Profile Card -->
      <div class="card mb-4">
        <h3 class="card-title">基本信息</h3>
        <div class="profile-header">
          <div class="avatar-large">{{ user.username[0].toUpperCase() }}</div>
          <div class="profile-info">
            <div class="username">{{ user.username }}</div>
            <div class="email">{{ user.email || '未绑定邮箱' }}</div>
            <div class="badges">
              <span v-if="user.role === 'admin'" class="badge badge-admin">
                <Shield :size="10" class="mr-1" /> 管理员
              </span>
              <span v-else class="badge badge-user">
                <UserIcon :size="10" class="mr-1" /> 普通用户
              </span>
              <span class="badge badge-success" v-if="user.sso_provider">
                已关联 {{ user.sso_provider }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Security Card -->
      <div class="card mb-4">
        <h3 class="card-title">修改密码</h3>
        <div class="form-group">
          <label>当前密码</label>
          <input v-model="pwdForm.oldPassword" type="password" class="form-input" placeholder="输入当前密码" autocomplete="current-password" />
        </div>
        <div class="form-group">
          <label>新密码</label>
          <input v-model="pwdForm.newPassword" type="password" class="form-input" placeholder="至少8位" autocomplete="new-password" />
        </div>
        <div class="form-group">
          <label>确认新密码</label>
          <input v-model="pwdForm.confirmPassword" type="password" class="form-input" placeholder="再次输入新密码" autocomplete="new-password" />
        </div>
        <button class="btn btn-primary" :disabled="updating" @click="changePassword">
          {{ updating ? '正在保存...' : '修改密码' }}
        </button>
        
        <div class="logout-section mt-4 pt-4 border-t">
          <button class="btn btn-logout" @click="handleLogout">
            <LogOut :size="14" class="mr-1" />
            注销登录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { Shield, User as UserIcon, LogOut, CreditCard, Ticket } from 'lucide-vue-next'

const user = ref(null)
const updating = ref(false)
const redeeming = ref(false)
const redemptionCode = ref('')
const toast = useToastStore()
const router = useRouter()

const pwdForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

async function fetchMe() {
  try {
    user.value = await api.getMe()
  } catch (e) {
    toast.error('获取用户信息失败')
  }
}

async function handleRedeem() {
  if (!redemptionCode.value) return
  redeeming.value = true
  try {
    const res = await api.redeemCode(redemptionCode.value)
    toast.success(res.message || '兑换成功')
    redemptionCode.value = ''
    await fetchMe() // Refresh balance
  } catch (e) {
    toast.error(e.message || '兑换失败')
  } finally {
    redeeming.value = false
  }
}

async function changePassword() {
  if (!pwdForm.value.oldPassword || !pwdForm.value.newPassword) {
    toast.error('请填写完整密码信息')
    return
  }
  if (pwdForm.value.newPassword !== pwdForm.value.confirmPassword) {
    toast.error('两次输入的新密码不一致')
    return
  }
  updating.value = true
  try {
    // API to be implemented
    toast.info('密码修改 API 暂未开放')
  } catch (e) {
    toast.error(e.message || '修改密码失败')
  } finally {
    updating.value = false
  }
}

function handleLogout() {
  localStorage.removeItem('access_token')
  router.push('/login')
}

onMounted(fetchMe)
</script>

<style scoped>
.account-page { padding: 20px; max-width: 600px; margin: 0 auto; }
.section-title { font-size: 20px; font-weight: 600; margin-bottom: 24px; }
.mb-4 { margin-bottom: 16px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; padding: 24px; }
.card-title { font-size: 13px; font-weight: 700; margin-bottom: 16px; color: var(--color-text-dim); text-transform: uppercase; letter-spacing: 0.05em; }

.balance-card { background: linear-gradient(135deg, rgba(249, 115, 22, 0.2), rgba(249, 115, 22, 0.05)); border-color: rgba(249, 115, 22, 0.3); }
.balance-value { font-size: 32px; font-weight: 800; color: var(--color-accent); }
.balance-icon { color: var(--color-accent); opacity: 0.5; }

.profile-header { display: flex; align-items: center; gap: 20px; }
.avatar-large { width: 64px; height: 64px; border-radius: 50%; background: var(--color-accent); color: white; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 600; }
.username { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
.email { font-size: 13px; color: var(--color-text-dim); margin-bottom: 12px; }

.badges { display: flex; gap: 8px; }
.badge { padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 700; border: 1px solid var(--color-border); display: inline-flex; align-items: center; }
.badge-admin { background: rgba(168, 85, 247, 0.1); color: #a855f7; border-color: rgba(168, 85, 247, 0.2); }
.badge-user { background: rgba(255, 255, 255, 0.05); color: var(--color-text-dim); }
.badge-success { background: rgba(16, 185, 129, 0.1); color: #10b981; border-color: rgba(16, 185, 129, 0.2); }

.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--color-text-dim); }
.form-input { width: 100%; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.help-text { font-size: 11px; color: var(--color-text-dim); }

.btn { display: inline-flex; align-items: center; justify-content: center; padding: 10px 20px; border-radius: 8px; border: none; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { background: var(--color-accent-hover); transform: translateY(-1px); }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }

.logout-section { margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--color-border); }
.btn-logout { background: rgba(239, 68, 68, 0.05); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
.btn-logout:hover { background: #ef4444; color: #fff; }

.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.gap-2 { gap: 8px; }
.mt-2 { margin-top: 8px; }
</style>
