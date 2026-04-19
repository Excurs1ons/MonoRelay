<template>
  <div class="settings-page">
    <style>
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px 16px;
      border-radius: 8px;
      border: 1px solid var(--color-border);
      background: var(--color-bg-card);
      color: var(--color-text);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn:hover {
      border-color: var(--color-accent);
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .btn-primary {
      background: var(--color-accent);
      border-color: var(--color-accent);
      color: #fff;
    }
    .btn-primary:hover {
      background: var(--color-accent-hover);
    }
    .btn-danger {
      background: #ef4444;
      border-color: #ef4444;
      color: #fff;
    }
    .btn-danger:hover {
      background: #dc2626;
    }
    @media (max-width: 600px) {
      .btn {
        width: 100%;
        justify-content: center;
      }
    }
    </style>
    <div class="flex-between mb-4">
      <h2 class="section-title">系统设置</h2>
      <button class="btn btn-primary" :disabled="saving" @click="saveConfig" style="display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:8px;border:1px solid #fff3;background:var(--color-accent,#f97316);color:#fff;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s;">
        <Save :size="14" class="mr-1" />
        {{ saving ? '正在保存...' : '保存设置' }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-8">
      <RefreshCw class="spin text-dim" :size="24" />
    </div>

    <div v-else class="settings-grid">
      <!-- Server Settings -->
      <div class="card">
        <h3 class="card-title">服务器配置</h3>
        <div class="form-group">
          <label>公网地址 (Public Host)</label>
          <input v-model="config.server.public_host" type="text" class="form-input" placeholder="例如: relay.example.com" />
          <p class="help-text">用于生成对外展示的 API 地址，留空则自动检测。</p>
        </div>
        <div class="form-group">
          <div class="flex-between mb-2">
            <label class="m-0">访问密钥 (Access Key)</label>
            <label class="switch">
              <input type="checkbox" v-model="config.server.access_key_enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="input-with-toggle" v-if="config.server.access_key_enabled">
            <input v-model="config.server.access_key" :type="showAccessKey ? 'text' : 'password'" class="form-input mono" autocomplete="off" />
            <div class="input-actions">
              <button class="toggle-btn" @click="generateRandomKey" title="随机生成">
                <RefreshCw :size="14" />
              </button>
              <button class="toggle-btn" @click="showAccessKey = !showAccessKey">
                <Eye v-if="!showAccessKey" :size="14" />
                <EyeOff v-else :size="14" />
              </button>
            </div>
          </div>
          <p v-if="!config.server.access_key" class="help-text" style="color:#f59e0b">首次使用，请复制并妥善保管此 Key！</p>
          <p v-else class="help-text">用于 API 鉴权的密码。</p>
        </div>
        <div class="form-group border-t pt-4 mt-4">
          <div class="flex-between mb-2">
            <label class="m-0">Cloudflare Turnstile 验证</label>
            <label class="switch">
              <input type="checkbox" v-model="config.server.turnstile_enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div v-if="config.server && config.server.turnstile_enabled" class="space-y-3 mt-3">
            <div class="form-group">
              <label class="text-xs">Site Key</label>
              <input v-model="config.server.turnstile_site_key" type="text" class="form-input" placeholder="3x00000000000000000000FF" />
            </div>
            <div class="form-group">
              <label class="text-xs">Secret Key</label>
              <input v-model="config.server.turnstile_secret_key" type="password" class="form-input" placeholder="1x0000000000000000000000000000000AA" autocomplete="off" />
            </div>
            
            <div class="help-box">
              <div class="flex items-center gap-1 mb-1">
                <HelpCircle :size="12" />
                <span class="font-semibold">如何获取密钥？</span>
              </div>
              <ol class="help-list">
                <li>访问 <a href="https://dash.cloudflare.com/" target="_blank">Cloudflare 控制台</a></li>
                <li>进入 <strong>Turnstile</strong> 菜单，点击 <strong>Add Site</strong></li>
                <li>Domain 填写你的域名或 IP</li>
                <li>完成后即可获得 Site Key 和 Secret Key</li>
              </ol>
            </div>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>日志级别</label>
            <select v-model="config.server.log_level" class="form-input">
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>
          <div class="form-group flex-1">
            <label>端口</label>
            <input v-model.number="config.server.port" type="number" class="form-input" />
          </div>
        </div>
      </div>

      <!-- Key Selection & Tool Calling -->
      <div class="card">
        <h3 class="card-title">策略与工具</h3>
        <div class="form-group">
          <label>密钥选择策略</label>
          <select v-model="config.key_selection.strategy" class="form-input">
            <option value="round-robin">轮询 (Round Robin)</option>
            <option value="random">随机 (Random)</option>
            <option value="weighted">权重 (Weighted)</option>
          </select>
        </div>
        <div class="form-group border-t pt-4 mt-4">
          <div class="flex-between mb-2">
            <label class="m-0">工具调用自动降级</label>
            <label class="switch">
              <input type="checkbox" v-model="config.tool_calling.auto_downgrade" />
              <span class="slider"></span>
            </label>
          </div>
          <p class="help-text">当模型不支持 tool_calling 时，自动将工具转换为提示词注入。</p>
        </div>
      </div>

      <!-- Logging Settings -->
      <div class="card">
        <h3 class="card-title">日志与清理</h3>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>日志保留天数</label>
            <input v-model.number="config.logging.max_age_days" type="number" class="form-input" />
          </div>
          <div class="form-group flex-1">
            <label>预览长度</label>
            <input v-model.number="config.logging.content_preview_length" type="number" class="form-input" />
          </div>
        </div>
        <div class="form-group">
          <div class="flex-between">
            <label class="m-0">启用请求日志</label>
            <label class="switch">
              <input type="checkbox" v-model="config.logging.enabled" />
              <span class="slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- SSO Advanced -->
      <div class="card">
        <h3 class="card-title">SSO 高级设置</h3>
        <div class="form-group">
          <label>SSO Provider</label>
          <select v-model="config.sso.provider" class="auth-input">
            <option value="github">GitHub</option>
            <option value="google">Google</option>
            <option value="prismaauth">PrismaAuth</option>
          </select>
        </div>
        <div class="form-group" v-if="config.sso.provider === 'github'">
          <label>GitHub Client ID</label>
          <input v-model="config.sso.github_client_id" type="text" class="auth-input" placeholder="GitHub OAuth App Client ID" autocomplete="off" />
        </div>
        <div class="form-group" v-if="config.sso.provider === 'github'">
          <label>GitHub Client Secret</label>
          <input v-model="config.sso.github_client_secret" type="password" class="auth-input" placeholder="GitHub OAuth App Client Secret" autocomplete="off" />
        </div>
        <div class="form-group" v-if="config.sso.provider === 'google'">
          <label>Google Client ID</label>
          <input v-model="config.sso.google_client_id" type="text" class="auth-input" placeholder="Google OAuth Client ID" autocomplete="off" />
        </div>
        <div class="form-group" v-if="config.sso.provider === 'google'">
          <label>Google Client Secret</label>
          <input v-model="config.sso.google_client_secret" type="password" class="auth-input" placeholder="Google OAuth Client Secret" autocomplete="off" />
        </div>
        <div class="form-group" v-if="config.sso.provider === 'prismaauth'">
          <label>PrismaAuth URL</label>
          <input v-model="config.sso.prismaauth_url" type="text" class="auth-input" placeholder="http://localhost:8080" />
        </div>
        <div class="form-group">
          <div class="flex-between mb-2">
            <label class="m-0">强制 SSO 登录</label>
            <label class="switch">
              <input type="checkbox" v-model="config.sso.sso_only" />
              <span class="slider"></span>
            </label>
          </div>
          <p class="help-text">开启后将禁用普通的用户名密码登录。</p>
        </div>
        <div class="form-group">
          <label>管理员名单 (GitHub 用户名, 以逗号分隔)</label>
          <input 
            v-model="adminUsernamesText" 
            type="text" 
            class="input" 
            placeholder="username1,username2,username3"
            @blur="updateAdminUsernames"
          />
          <p class="help-text">当前管理员: {{ config.sso?.admin_usernames?.join(', ') || '(无)' }}</p>
        </div>
      </div>
    </div>

    <!-- Danger Zone -->
    <div class="mt-8 pt-8 border-t border-red-900/30">
      <h3 class="text-red-500 font-semibold mb-4 flex items-center gap-2">
        <AlertTriangle :size="18" /> 危险区域
      </h3>
      <div class="card border-red-900/50 bg-red-950/10 danger-card mb-4">
        <div class="danger-content">
          <div class="danger-text">
            <h4 class="font-medium text-sm mb-1">清空统计数据</h4>
            <p class="text-xs text-dim">此操作将删除所有请求统计、模型使用数据和费用估算。</p>
          </div>
          <button class="btn btn-danger" @click="confirmClearStats" style="display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:8px;border:1px solid #ef4444;background:#ef4444;color:#fff;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s;">
            <Trash2 :size="14" class="mr-1" />
            清空统计
          </button>
        </div>
      </div>
      <div class="card border-red-900/50 bg-red-950/10 danger-card">
        <div class="danger-content">
          <div class="danger-text">
            <h4 class="font-medium text-sm mb-1">清空所有数据</h4>
            <p class="text-xs text-dim">此操作将删除所有用户、密钥、日志和配置文件。MonoRelay 将恢复到初始状态并自动停止。</p>
          </div>
<button class="btn btn-danger" @click="confirmClearData" style="display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:8px;border:1px solid #ef4444;background:#ef4444;color:#fff;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s;">
        <Trash2 :size="14" class="mr-1" />
        清空数据
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
import { Save, RefreshCw, Eye, EyeOff, X, AlertTriangle, Trash2, HelpCircle } from 'lucide-vue-next'

const loading = ref(true)
const saving = ref(false)
const showAccessKey = ref(false)
const toast = useToastStore()
const newAdminName = ref('')
const adminUsernamesText = ref('')

const config = ref({
  server: {
    public_host: '',
    access_key: '',
    access_key_enabled: true,
    log_level: 'INFO',
    port: 8787,
    turnstile_enabled: false,
    turnstile_site_key: '',
    turnstile_secret_key: ''
  },
  key_selection: { strategy: 'round-robin' },
  tool_calling: { auto_downgrade: true, unsupported_models: [] },
  logging: { enabled: true, max_age_days: 30, content_preview_length: 200 },
  sso: {
    provider: 'github',
    sso_only: false,
    admin_usernames: [],
    github_client_id: '',
    github_client_secret: '',
    google_client_id: '',
    google_client_secret: '',
    prismaauth_url: 'http://localhost:8080'
  }
})

async function fetchFullConfig() {
  loading.value = true
  try {
    // We'll need to add a getFullConfig to api.js
    const data = await api.getFullConfig()
    config.value = data
    adminUsernamesText.value = (data.sso?.admin_usernames || []).join(',')
  } catch (e) {
    toast.error('获取配置失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const secrets = {
      sso_client_secret: config.value.sso.client_secret,
      github_client_secret: config.value.sso.github_client_secret,
      google_client_secret: config.value.sso.google_client_secret,
      local_sso_secret: config.value.sso.local_sso_secret,
      jwt_secret: config.value.server.jwt_secret,
      turnstile_secret_key: config.value.server.turnstile_secret_key,
    }
    await api.updateFullConfig({ ...config.value, secrets })
    toast.success('设置已保存并热重载')
  } catch (e) {
    toast.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function generateRandomKey() {
  const guid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
  config.value.server.access_key = guid
}

function updateAdminUsernames() {
  const names = adminUsernamesText.value.split(',').map(s => s.trim()).filter(s => s)
  config.value.sso.admin_usernames = names
}

function addAdmin() {
  const name = newAdminName.value.trim()
  if (name && !config.value.sso.admin_usernames.includes(name)) {
    config.value.sso.admin_usernames.push(name)
    newAdminName.value = ''
  }
}

function removeAdmin(index) {
  config.value.sso.admin_usernames.splice(index, 1)
}

async function confirmClearData() {
  const code = Math.floor(1000 + Math.random() * 9000)
  const input = prompt(`警告：此操作将永久删除所有本地数据！\n请输入验证码 [ ${code} ] 并点击确定以继续：`)
  
  if (input === String(code)) {
    try {
      // We'll need to add clearAllData to api.js
      await api.clearAllData()
      toast.success('数据已清空，服务正在关闭...')
      setTimeout(() => {
        window.location.href = '/'
      }, 2000)
    } catch (e) {
      toast.error('清空失败: ' + e.message)
    }
  } else if (input !== null) {
    toast.error('验证码错误')
  }
}

async function confirmClearStats() {
  if (!confirm('确定清空所有统计数据？')) return
  try {
    await api.resetStats()
    toast.success('统计数据已清空')
  } catch (e) {
    toast.error('清空失败: ' + e.message)
  }
}

onMounted(fetchFullConfig)
</script>

<style scoped>
.settings-page { padding: 0; }
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

.card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  padding: 20px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 20px;
  color: var(--color-accent);
  display: flex;
  align-items: center;
}

.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; margin-bottom: 6px; }
.form-row { display: flex; gap: 16px; }

.form-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text);
  font-size: 13px;
}

.help-text { font-size: 11px; color: var(--color-text-dim); mt: 4px; }

.help-box {
  background: rgba(99, 102, 241, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 11px;
}

.help-list {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-dim);
}

.help-list li {
  margin-bottom: 2px;
}

.help-list a {
  color: var(--color-accent);
  text-decoration: none;
}

.input-with-toggle { position: relative; display: flex; align-items: center; }
.input-with-toggle .form-input { padding-right: 72px; }
.input-actions {
  position: absolute;
  right: 8px;
  display: flex;
  gap: 4px;
}
.toggle-btn {
  background: none;
  border: none;
  color: var(--color-text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 4px;
}
.toggle-btn:hover {
  color: var(--color-accent);
}

.flex-1 { flex: 1; }
.mr-1 { margin-right: 4px; }
.m-0 { margin: 0; }

/* Switch Toggle */
.switch { position: relative; display: inline-block; width: 34px; height: 20px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(255,255,255,0.1); transition: .2s; border-radius: 20px;
}
.slider:before {
  position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px;
  background-color: white; transition: .2s; border-radius: 50%;
}
input:checked + .slider { background-color: var(--color-accent); }
input:checked + .slider:before { transform: translateX(14px); }

/* Tag Input */
.tag-input-container {
  display: flex; flex-wrap: wrap; gap: 6px; padding: 6px;
  border: 1px solid var(--color-border); background: var(--color-bg-input); border-radius: 6px; min-height: 38px;
}
.tag {
  display: flex; align-items: center; gap: 4px; padding: 2px 8px;
  background: rgba(99, 102, 241, 0.15); color: #818cf8; border-radius: 4px; font-size: 12px;
}
.tag-close { cursor: pointer; opacity: 0.7; }
.tag-close:hover { opacity: 1; }
.tag-input {
  border: none; background: transparent; color: var(--color-text); font-size: 13px; outline: none; flex: 1; min-width: 60px;
}

.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.btn-danger {
  background: #ef4444;
  color: #fff;
}
.btn-danger:hover {
  background: #dc2626;
}
.text-red-500 { color: #ef4444; }
.border-red-900\/30 { border-color: rgba(127, 29, 29, 0.3); }
.border-red-900\/50 { border-color: rgba(127, 29, 29, 0.5); }
.bg-red-950\/10 { background-color: rgba(69, 10, 10, 0.1); }

.danger-card { padding: 16px 20px; }
.danger-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.danger-text { flex: 1; min-width: 0; }
@media (max-width: 600px) {
  .settings-page {
    padding: 0;
  }
  .page-content {
    overflow-x: hidden;
  }
  .settings-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .card {
    overflow-x: hidden;
  }
  .danger-content { 
    flex-direction: column; 
    align-items: stretch; 
  }
  .danger-text { margin-bottom: 12px; }
}
</style>
