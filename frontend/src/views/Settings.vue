<template>
  <div class="settings-page">
    <style>
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 16px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-bg-card); color: var(--color-text); font-size: 14px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
    .btn:hover { border-color: var(--color-accent); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; }
    .btn-primary:hover { background: var(--color-accent-hover); }
    .btn-danger { background: #ef4444; border-color: #ef4444; color: #fff; }
    .btn-danger:hover { background: #dc2626; }
    .param-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
    .param-input { background: var(--color-bg-input); border: 1px solid var(--color-border); color: var(--color-text); border-radius: 4px; padding: 6px 10px; font-size: 12px; }
    @media (max-width: 600px) { .btn { width: 100%; justify-content: center; } }
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

      <!-- Global Request Params -->
      <div class="card">
        <h3 class="card-title">全局请求参数</h3>
        <div class="form-group">
          <div class="flex-between mb-2">
            <label class="m-0">启用全局参数控制</label>
            <label class="switch">
              <input type="checkbox" v-model="config.model_routing.global_params.enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <p class="help-text">在路由层统一补齐、组合或覆写请求参数。</p>
        </div>
        <div v-if="config.model_routing.global_params.enabled">
          <div class="form-group">
            <label>应用模式</label>
            <select v-model="config.model_routing.global_params.mode" class="form-input">
              <option value="default">组合模式 (与请求内容合并/补齐)</option>
              <option value="override">覆写模式 (强制替换为全局设置)</option>
            </select>
            <p class="help-text" v-if="config.model_routing.global_params.mode === 'default'">
              <b>组合模式</b>：注入 System Prompt 到开头，补齐缺失的其他参数。
            </p>
            <p class="help-text" v-else>
              <b>覆写模式</b>：强制替换所有 System 消息和其他对应参数。
            </p>
          </div>

          <div class="form-group">
            <label>全局 System Prompt</label>
            <textarea v-model="config.model_routing.global_params.system_prompt" class="form-input" rows="3" placeholder="注入到所有请求的系统提示词..."></textarea>
          </div>

          <div class="form-group">
            <label>其他参数列表</label>
            <div v-for="(val, key) in config.model_routing.global_params.params" :key="key" class="param-row">
              <input :value="key" @change="updateParamKey(key, $event.target.value)" class="param-input flex-1" placeholder="键 (如 max_tokens)" />
              <input :value="val" @change="updateParamValue(key, $event.target.value)" class="param-input flex-1" placeholder="值 (如 4096)" />
              <button class="btn btn-icon text-red-500" @click="removeParam(key)" style="padding:4px;border:none;background:none;cursor:pointer;"><X :size="14" /></button>
            </div>
            <button class="btn btn-xs mt-2" @click="addParam" style="padding: 4px 8px; font-size: 11px; border-style: dashed; width: 100%;">+ 添加参数</button>
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
          <select v-model="config.sso.provider" class="form-input">
            <option value="github">GitHub</option>
            <option value="google">Google</option>
            <option value="prismaauth">PrismaAuth</option>
          </select>
        </div>
        <div class="form-group">
          <div class="flex-between mb-2">
            <label class="m-0">强制 SSO 登录</label>
            <label class="switch">
              <input type="checkbox" v-model="config.sso.sso_only" />
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <div class="form-group">
          <label>管理员名单 (GitHub 用户名, 以逗号分隔)</label>
          <input v-model="adminUsernamesText" type="text" class="form-input" placeholder="username1,username2" @blur="updateAdminUsernames" />
        </div>
      </div>
    </div>

    <!-- Danger Zone -->
    <div class="mt-8 pt-8 border-t border-red-900/30">
      <h3 class="text-red-500 font-semibold mb-4 flex items-center gap-2"><AlertTriangle :size="18" /> 危险区域</h3>
      <div class="card border-red-900/50 bg-red-950/10 danger-card mb-4">
        <div class="danger-content">
          <div class="danger-text">
            <h4 class="font-medium text-sm mb-1">清空统计数据</h4>
            <p class="text-xs text-dim">此操作将删除所有请求统计、模型使用数据和数据库请求日志。</p>
          </div>
          <button class="btn btn-danger" @click="confirmClearStats" style="display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:8px;border:1px solid #ef4444;background:#ef4444;color:#fff;font-size:14px;font-weight:500;cursor:pointer;transition:all .15s;">
            <Trash2 :size="14" class="mr-1" /> 清空统计
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
import { Save, RefreshCw, Eye, EyeOff, X, AlertTriangle, Trash2 } from 'lucide-vue-next'

const loading = ref(true)
const saving = ref(false)
const showAccessKey = ref(false)
const toast = useToastStore()
const adminUsernamesText = ref('')

const config = ref({
  server: { public_host: '', access_key: '', access_key_enabled: true, log_level: 'INFO', port: 8787 },
  model_routing: { global_params: { enabled: false, mode: 'default', params: {}, system_prompt: '' } },
  key_selection: { strategy: 'round-robin' },
  tool_calling: { auto_downgrade: true },
  logging: { enabled: true, max_age_days: 30, content_preview_length: 200 },
  sso: { provider: 'github', sso_only: false, admin_usernames: [] }
})

async function fetchFullConfig() {
  loading.value = true
  try {
    const data = await api.getFullConfig()
    if (!data.model_routing.global_params) data.model_routing.global_params = { enabled: false, mode: 'default', params: {}, system_prompt: '' }
    config.value = data
    adminUsernamesText.value = (data.sso?.admin_usernames || []).join(',')
  } catch (e) { toast.error('获取配置失败: ' + e.message) } finally { loading.value = false }
}

async function saveConfig() {
  saving.value = true
  try {
    await api.updateFullConfig(config.value)
    toast.success('设置已保存并热重载')
  } catch (e) { toast.error('保存失败: ' + e.message) } finally { saving.value = false }
}

function updateParamKey(oldKey, newKey) {
  if (oldKey === newKey) return
  const val = config.value.model_routing.global_params.params[oldKey]
  delete config.value.model_routing.global_params.params[oldKey]
  config.value.model_routing.global_params.params[newKey] = val
}

function updateParamValue(key, newVal) {
  let parsed = newVal
  if (!isNaN(newVal) && newVal !== '') parsed = Number(newVal)
  else if (newVal.toLowerCase() === 'true') parsed = true
  else if (newVal.toLowerCase() === 'false') parsed = false
  config.value.model_routing.global_params.params[key] = parsed
}

function addParam() { config.value.model_routing.global_params.params['new_param_' + Date.now()] = '' }
function removeParam(key) { delete config.value.model_routing.global_params.params[key] }
function updateAdminUsernames() { config.value.sso.admin_usernames = adminUsernamesText.value.split(',').map(s => s.trim()).filter(s => s) }
function generateRandomKey() { config.value.server.access_key = crypto.randomUUID() }

async function confirmClearStats() {
  if (!confirm('确定彻底清空所有统计数据和请求日志？')) return
  try {
    await api.resetStats()
    toast.success('数据已彻底清空')
  } catch (e) { toast.error('清空失败: ' + e.message) }
}

onMounted(fetchLogs)

// Fix confirmClearData mock or missing
async function confirmClearData() {
  const code = Math.floor(1000 + Math.random() * 9000);
  const input = prompt(`警告：此操作将永久删除所有数据！\n请输入验证码 [ ${code} ] 以继续：`);
  if (input === String(code)) {
    try {
      await api.clearAllData();
      toast.success('数据已清空');
    } catch (e) { toast.error('清空失败: ' + e.message); }
  }
}
</script>

<style scoped>
.settings-page { padding: 0; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 10px; padding: 20px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 20px; color: var(--color-accent); display: flex; align-items: center; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; margin-bottom: 6px; }
.form-input { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.help-text { font-size: 11px; color: var(--color-text-dim); margin-top: 4px; }
.input-with-toggle { position: relative; display: flex; align-items: center; }
.input-with-toggle .form-input { padding-right: 72px; }
.input-actions { position: absolute; right: 8px; display: flex; gap: 4px; }
.toggle-btn { background: none; border: none; color: var(--color-text-dim); cursor: pointer; display: flex; align-items: center; padding: 4px; }
.toggle-btn:hover { color: var(--color-accent); }
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.mb-4 { margin-bottom: 16px; }
.mb-2 { margin-bottom: 8px; }
.m-0 { margin: 0; }
.form-row { display: flex; gap: 16px; }
.flex-1 { flex: 1; }
.mr-1 { margin-right: 4px; }
.mt-2 { margin-top: 8px; }
.mt-8 { margin-top: 32px; }
.pt-8 { padding-top: 32px; }
.border-t { border-top: 1px solid var(--color-border); }
.text-red-500 { color: #ef4444; }
.text-dim { color: var(--color-text-dim); }
.text-xs { font-size: 11px; }
.font-medium { font-weight: 500; }
.font-semibold { font-weight: 600; }
.items-center { align-items: center; }
.gap-2 { gap: 8px; }
.danger-card { border-color: rgba(239, 68, 68, 0.2); background: rgba(239, 68, 68, 0.02); }
.danger-content { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.danger-text { flex: 1; }

.switch { position: relative; display: inline-block; width: 34px; height: 20px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(255,255,255,0.1); transition: .2s; border-radius: 20px; }
.slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }
input:checked + .slider { background-color: var(--color-accent); }
input:checked + .slider:before { transform: translateX(14px); }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

@media (max-width: 600px) {
  .settings-grid { grid-template-columns: 1fr; gap: 12px; }
  .danger-content { flex-direction: column; align-items: stretch; }
  .danger-text { margin-bottom: 12px; }
}
</style>
