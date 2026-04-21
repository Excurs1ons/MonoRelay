<template>
  <div class="keys-page">
    <div class="flex-between mb-6">
      <div>
        <h2 class="section-title">{{ isAdmin ? '上游提供商密钥' : '我的 API 令牌' }}</h2>
        <p class="text-dim text-sm">{{ isAdmin ? '管理转发到上游大模型的授权密钥' : '生成并管理您用于调用接口的 sk-prisma 令牌' }}</p>
      </div>
      <button v-if="!isAdmin" class="btn btn-primary" @click="showCreateModal = true">
        <Plus :size="16" class="mr-1" /> 创建令牌
      </button>
    </div>

    <div v-if="loading" class="loading"><RefreshCw class="spin" /></div>
    
    <div v-else>
      <!-- User API Keys View -->
      <div v-if="!isAdmin" class="keys-grid">
        <div v-for="key in userKeys" :key="key.id" class="card key-card">
          <div class="flex-between mb-3">
            <div class="key-label-group">
              <div class="key-tag">sk-prisma</div>
              <h4 class="key-name">{{ key.label }}</h4>
            </div>
            <div class="status-indicator" :class="{ 'active': key.enabled }"></div>
          </div>
          <div class="key-value-box">
            <code class="mono">{{ key.key }}</code>
            <button class="copy-btn" @click="copyToClipboard(key.key)">
              <Copy :size="14" />
            </button>
          </div>
          <div class="key-meta">
            <span>创建于: {{ formatDate(key.created_at) }}</span>
            <span>已用额度: ${{ key.quota_used.toFixed(4) }}</span>
          </div>
        </div>
        <div v-if="!userKeys.length" class="empty-state">
          <Key :size="48" class="text-dim mb-2" />
          <p>您还没有创建任何 API 令牌</p>
        </div>
      </div>

      <!-- Admin Providers Keys View (Inherited logic) -->
      <div v-else class="providers-list">
        <div v-for="(provider, name) in providers" :key="name" class="card mb-4">
          <div class="flex-between mb-4">
            <div class="flex items-center gap-2">
              <Globe :size="18" class="text-accent" />
              <h3 class="font-bold">{{ name }}</h3>
            </div>
            <button class="btn btn-xs" @click="testProvider(name)">测试连通性</button>
          </div>
          <div class="keys-table">
            <div v-for="(k, idx) in provider.keys" :key="idx" class="key-row">
              <div class="key-info">
                <span class="label">{{ k.label }}</span>
                <span class="key-masked">••••••••{{ k.key.slice(-8) }}</span>
              </div>
              <div class="key-actions">
                <span class="badge" :class="k.enabled ? 'badge-green' : 'badge-red'">
                  {{ k.enabled ? '已启用' : '已禁用' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Modal for User -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-card">
        <h3>创建新令牌</h3>
        <div class="form-group mt-4">
          <label>令牌备注名称</label>
          <input v-model="newKeyLabel" type="text" class="form-input" placeholder="例如: 我的开发环境" @keyup.enter="createKey" />
        </div>
        <div class="modal-actions mt-6">
          <button class="btn btn-ghost" @click="showCreateModal = false">取消</button>
          <button class="btn btn-primary" :disabled="!newKeyLabel" @click="createKey">确认创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'
import { Plus, Key, RefreshCw, Copy, Globe, MoreVertical } from 'lucide-vue-next'

const loading = ref(true)
const user = ref(null)
const userKeys = ref([])
const providers = ref({})
const showCreateModal = ref(false)
const newKeyLabel = ref('')
const toast = useToastStore()

const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.is_admin)

async function fetchData() {
  loading.value = true
  try {
    user.value = await api.getMe()
    if (isAdmin.value) {
      const config = await api.getFullConfig()
      providers.value = config.providers
    } else {
      userKeys.value = await api.getUserKeys()
    }
  } catch (e) {
    toast.error('获取数据失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function createKey() {
  try {
    await api.createUserKey(newKeyLabel.value)
    toast.success('令牌创建成功')
    showCreateModal.value = false
    newKeyLabel.value = ''
    userKeys.value = await api.getUserKeys()
  } catch (e) {
    toast.error('创建失败: ' + e.message)
  }
}

async function testProvider(name) {
  try {
    const res = await api.testProvider(name)
    if (res.success) toast.success(`${name} 测试通过`)
    else toast.error(`${name} 测试失败: ${res.message}`)
  } catch (e) { toast.error('测试出错: ' + e.message) }
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text)
  toast.success('已复制到剪贴板')
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString()
}

onMounted(fetchData)
</script>

<style scoped>
.keys-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.key-card { padding: 16px; border: 1px solid var(--color-border); position: relative; }
.key-tag { font-size: 9px; font-weight: 800; background: var(--color-accent); color: #fff; padding: 1px 4px; border-radius: 4px; margin-right: 8px; }
.key-label-group { display: flex; align-items: center; }
.key-name { font-size: 14px; font-weight: 600; margin: 0; }
.status-indicator { width: 8px; height: 8px; border-radius: 50%; background: #4b5563; }
.status-indicator.active { background: #10b981; box-shadow: 0 0 8px rgba(16, 185, 129, 0.4); }

.key-value-box { margin: 12px 0; background: var(--color-bg-input); padding: 8px 12px; border-radius: 6px; display: flex; align-items: center; justify-content: space-between; border: 1px solid var(--color-border); }
.key-value-box code { font-size: 12px; color: var(--color-accent); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.copy-btn { background: none; border: none; color: var(--color-text-dim); cursor: pointer; padding: 4px; display: flex; align-items: center; }
.copy-btn:hover { color: var(--color-accent); }

.key-meta { display: flex; justify-content: space-between; font-size: 11px; color: var(--color-text-dim); }

.providers-list { display: flex; flex-direction: column; gap: 16px; }
.key-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.key-row:last-child { border-bottom: none; }
.key-info { display: flex; flex-direction: column; }
.key-info .label { font-size: 11px; color: var(--color-text-dim); }
.key-info .key-masked { font-family: monospace; font-size: 13px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 12px; padding: 24px; width: 100%; max-width: 400px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 12px; }

.empty-state { text-align: center; padding: 64px 0; color: var(--color-text-dim); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
