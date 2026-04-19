<template>
  <div class="account-page">
    <h2 class="section-title">账户管理</h2>

    <div class="account-content" v-if="user">
      <!-- Profile Card -->
      <div class="card mb-4">
        <h3 class="card-title">基本信息</h3>
        <div class="profile-header">
          <div class="avatar-large">{{ user.username[0].toUpperCase() }}</div>
          <div class="profile-info">
            <div class="username">{{ user.username }}</div>
            <div class="email">{{ user.email }}</div>
            <div class="badges">
              <span v-if="user.is_admin" class="badge badge-admin">
                <Shield :size="10" class="mr-1" /> 管理员
              </span>
              <span v-else class="badge badge-user">
                <User :size="10" class="mr-1" /> 普通用户
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
        <h3 class="card-title">安全设置</h3>
        <div class="form-group">
          <label>当前密码</label>
          <input 
            v-model="pwdForm.oldPassword" 
            type="password" 
            class="form-input" 
            placeholder="输入当前密码"
            autocomplete="current-password"
          />
        </div>
        <div class="form-group">
          <label>新密码</label>
          <input 
            v-model="pwdForm.newPassword" 
            type="password" 
            class="form-input" 
            placeholder="至少8位"
            autocomplete="new-password"
          />
        </div>
        <div class="form-group">
          <label>确认新密码</label>
          <input 
            v-model="pwdForm.confirmPassword" 
            type="password" 
            class="form-input" 
            placeholder="再次输入新密码"
            autocomplete="new-password"
          />
        </div>
        <button 
          class="btn btn-primary" 
          :disabled="updating" 
          @click="changePassword"
        >
          {{ updating ? '正在保存...' : '修改密码' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { Shield, User } from 'lucide-vue-next'

const user = ref(null)
const updating = ref(false)
const toast = useToastStore()

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

async function changePassword() {
  if (!pwdForm.value.oldPassword || !pwdForm.value.newPassword) {
    toast.error('请填写完整密码信息')
    return
  }
  if (pwdForm.value.newPassword !== pwdForm.value.confirmPassword) {
    toast.error('两次输入的新密码不一致')
    return
  }
  if (pwdForm.value.newPassword.length < 8) {
    toast.error('新密码长度至少8位')
    return
  }

  updating.value = true
  try {
    // We'll need to add changePassword to api.js and backend
    await api.changePassword(pwdForm.value.oldPassword, pwdForm.value.newPassword)
    toast.success('密码修改成功')
    pwdForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  } catch (e) {
    toast.error(e.message || '修改密码失败')
  } finally {
    updating.value = false
  }
}

onMounted(fetchMe)
</script>

<style scoped>
.account-page {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 24px;
}

.mb-4 { margin-bottom: 16px; }

.card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  padding: 20px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--color-text-dim);
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.avatar-large {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 600;
}

.username {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.email {
  font-size: 14px;
  color: var(--color-text-dim);
  margin-bottom: 8px;
}

.badges {
  display: flex;
  gap: 8px;
}

.badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-primary { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
.badge-ghost { background: rgba(255, 255, 255, 0.05); color: var(--color-text-dim); }
.badge-success { background: rgba(34, 197, 94, 0.15); color: #4ade80; }
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

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--color-text);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text);
  font-size: 13px;
}

.form-input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--color-accent);
  color: #fff;
}

.btn-primary:hover {
  background: var(--color-accent-hover);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
