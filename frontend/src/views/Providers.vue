<template>
  <div>
    <!-- Provider list -->
    <div class="card mb-4">
      <div class="card-title-row">
        <div class="card-title">{{ $t('providers.title') }}</div>
        <button class="btn btn-primary btn-sm" @click="openAddModal">
          <Plus :size="14" />
          添加
        </button>
      </div>
      <div v-if="loading" class="loading"><div class="spinner"></div></div>
      <div v-else class="provider-list">
        <div v-for="(pc, name) in providers" :key="name" class="provider-item">
          <div class="provider-header" @click="toggleExpand(name)">
            <div class="provider-info">
              <ChevronRight class="provider-arrow" :class="{ expanded: expanded[name] }" :size="16" />
              <span class="badge" :class="getTypeBadgeClass(pc)">
                {{ pc.provider_type === 'web_reverse' ? '网页反代' : (pc.provider_type === 'anthropic' ? 'Anthropic' : 'API') }}
              </span>
              <div class="provider-text">
                <div class="provider-name">{{ name }}</div>
                <div class="provider-url">{{ pc.provider_type === 'web_reverse' ? (pc.web_reverse?.chatgpt_base_url || 'chatgpt.com') : pc.base_url }}</div>
              </div>
            </div>
            <span class="provider-keys desktop-only">{{ pc.keys?.length || 0 }} 个密钥</span>
          </div>
          <div v-show="expanded[name]" class="provider-details">
            <div class="detail-section mobile-only">
              <div class="detail-label">密钥</div>
              <div class="detail-value">{{ pc.keys?.length || 0 }} 个</div>
            </div>
            <div class="detail-section">
              <div class="detail-label">模型库</div>
              <div class="detail-value mono">{{ getModelCount(name) }} 个模型</div>
            </div>
            <div class="detail-section">
              <div class="detail-label">外部链接</div>
              <div class="detail-value mono">{{ pc.provider_type === 'web_reverse' ? (pc.web_reverse?.chatgpt_base_url || 'chatgpt.com') : pc.base_url }}</div>
            </div>
            <div class="provider-actions">
              <button class="btn btn-ghost btn-sm" @click.stop="openTestModal(name)">
                <Zap :size="14" />
                测试
              </button>
              <button class="btn btn-ghost btn-sm" @click.stop="openTestModal(name)">
                <ListChecks :size="14" />
                批量
              </button>
              <button class="btn btn-ghost btn-sm" :disabled="verifying[name]" @click.stop="verifyProvider(name)">
                <ShieldCheck :size="14" :class="{ 'animate-pulse': verifying[name] }" />
                {{ verifying[name] ? '验证中...' : '验证' }}
              </button>
              <button class="btn btn-ghost btn-sm" @click.stop="exportKeys(name)">
                <Download :size="14" />
                导出
              </button>
              <button class="btn btn-ghost btn-sm" @click.stop="openModelsModal(name)">
                <BookOpen :size="14" />
                模型
              </button>
              <button class="btn btn-ghost btn-sm" @click.stop="openEditModal(name, pc)">
                <Pencil :size="14" />
                编辑
              </button>
              <button class="btn btn-sm danger-btn" @click.stop="deleteProvider(name)">
                <Trash2 :size="14" />
                删除
              </button>
            </div>
            <div v-if="verifyResults[name]" class="verify-result">
              <div class="verify-header">
                <span class="verify-badge" :class="verifyResults[name].overall_status === 'pass' ? 'badge-green' : 'badge-red'">
                  {{ verifyResults[name].overall_status === 'pass' ? '验证通过' : '验证失败' }}
                </span>
                <span class="verify-model">{{ verifyResults[name].model }}</span>
              </div>
              <div class="verify-probes">
                <div v-for="(probe, key) in verifyResults[name].probes" :key="key" class="probe-item">
                  <CheckCircle v-if="probe.status === 'pass'" :size="12" class="probe-ok" />
                  <XCircle v-else :size="12" class="probe-error" />
                  <span class="probe-name">{{ getProbeLabel(key) }}</span>
                  <span class="probe-latency">{{ probe.latency_ms?.toFixed(0) }}ms</span>
                </div>
              </div>
            </div>
            <div v-if="testResults[name]" class="test-result" :class="testResults[name].ok ? 'test-ok' : 'test-error'">
              {{ testResults[name].message }}
            </div>
          </div>
        </div>
        <div v-if="!Object.keys(providers).length" class="empty">{{ $t('dashboard.noData') }}</div>
      </div>
    </div>

    <!-- Key status table -->
    <div class="card">
      <div class="card-title">{{ $t('keys.title') }}</div>
      <div v-if="loading" class="loading"><div class="spinner"></div></div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>提供商</th>
              <th>标签</th>
              <th>请求数</th>
              <th>失败数</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in keyList" :key="k.key">
              <td>{{ k.provider }}</td>
              <td class="mono">{{ k.label }}</td>
              <td>{{ k.total_requests || 0 }}</td>
              <td>{{ k.total_failures || 0 }}</td>
              <td>
                <span class="badge" :class="k.available ? 'badge-green' : 'badge-red'">
                  {{ k.available ? '可用' : '冷却中' }}
                </span>
              </td>
            </tr>
            <tr v-if="!keyList.length">
              <td colspan="5" class="empty">暂无密钥数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Edit Modal -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal">
        <div class="modal-header">{{ $t('providers.editProvider') }}</div>
        <div class="modal-body">
          <div class="form-group">
            <label>{{ $t('providers.name') }}</label>
            <input v-model="editForm.name" type="text" class="form-input" disabled />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.baseUrl') }}</label>
            <input v-model="editForm.base_url" type="text" class="form-input mono" />
          </div>
          <div class="form-group">
            <label>API Key <span class="text-dim text-xs">({{ editingProviderKeys }} 个已存储)</span></label>
            <input v-model="editForm.api_key" type="password" class="form-input mono" placeholder="留空保持不变" />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.type') }}</label>
            <select v-model="editForm.provider_type" class="form-input">
              <option value="api">API</option>
              <option value="anthropic">Anthropic</option>
              <option value="web_reverse">Web Reverse</option>
            </select>
          </div>
          <div class="form-group">
            <label>{{ $t('providers.timeout') }}</label>
            <input v-model.number="editForm.timeout" type="number" class="form-input" />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.rateLimitCooldown') }}</label>
            <input v-model.number="editForm.rate_limit_cooldown" type="number" class="form-input" />
          </div>
          <div class="form-group">
            <label>输入价格（$/1M tokens）</label>
            <input v-model.number="editForm.cost_per_m_input" type="number" step="0.01" class="form-input mono" placeholder="0.00" />
          </div>
          <div class="form-group">
            <label>输出价格（$/1M tokens）</label>
            <input v-model.number="editForm.cost_per_m_output" type="number" step="0.01" class="form-input mono" placeholder="0.00" />
          </div>
          <label class="checkbox-label">
            <input v-model="editForm.enabled" type="checkbox" />
            {{ $t('common.enabled') }}
          </label>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showEditModal = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveProvider">{{ $t('common.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Add Provider Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">添加提供商</div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="addForm.name" type="text" class="form-input mono" placeholder="例如: openrouter" />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.baseUrl') }}</label>
            <input v-model="addForm.base_url" type="text" class="form-input mono" placeholder="https://api.example.com/v1" />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.type') }}</label>
            <select v-model="addForm.provider_type" class="form-input">
              <option value="api">API</option>
              <option value="anthropic">Anthropic</option>
              <option value="web_reverse">Web Reverse</option>
            </select>
          </div>
          <div class="form-group">
            <label>{{ $t('providers.timeout') }}</label>
            <input v-model.number="addForm.timeout" type="number" class="form-input" />
          </div>
          <div class="form-group">
            <label>{{ $t('providers.rateLimitCooldown') }}</label>
            <input v-model.number="addForm.rate_limit_cooldown" type="number" class="form-input" />
          </div>
          <div class="form-group">
            <label>输入价格（$/1M tokens）</label>
            <input v-model.number="addForm.cost_per_m_input" type="number" step="0.01" class="form-input mono" placeholder="0.00" />
          </div>
          <div class="form-group">
            <label>输出价格（$/1M tokens）</label>
            <input v-model.number="addForm.cost_per_m_output" type="number" step="0.01" class="form-input mono" placeholder="0.00" />
          </div>
          <label class="checkbox-label">
            <input v-model="addForm.enabled" type="checkbox" />
            {{ $t('common.enabled') }}
          </label>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showAddModal = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveAddProvider">添加</button>
        </div>
      </div>
    </div>

    <!-- Models Modal -->
    <div v-if="showModelsModal" class="modal-overlay" @click.self="showModelsModal = false">
      <div class="modal modal-lg">
        <div class="modal-header">
          {{ modelsProvider }} - 模型库
          <span class="model-count" v-if="remoteModels.length">({{ selectedModels.length }}/{{ remoteModels.length }})</span>
        </div>
        <div class="modal-body">
          <div class="models-toolbar">
            <button class="btn btn-ghost btn-sm" @click="fetchRemoteModels" :disabled="fetchingRemote">
              {{ fetchingRemote ? '获取中...' : '获取模型列表' }}
            </button>
            <div class="models-search">
              <Search :size="14" class="search-icon" />
              <input v-model="modelSearch" type="text" class="form-input form-input-sm" placeholder="搜索模型..." />
            </div>
            <div class="models-select">
              <button class="btn btn-ghost btn-xs" @click="selectAll">全选</button>
              <button class="btn btn-ghost btn-xs" @click="deselectAll">取消全选</button>
            </div>
          </div>
          <div v-if="fetchingRemote" class="loading-sm"><div class="spinner"></div></div>
          <div v-else-if="remoteModels.length" class="models-grid">
            <label v-for="m in filteredModels" :key="m.id" class="model-item" :class="{ selected: selectedModels.includes(m.id) }">
              <input type="checkbox" :checked="selectedModels.includes(m.id)" @change="toggleModel(m.id)" />
              <Check v-if="selectedModels.includes(m.id)" :size="14" class="model-check" />
              <span class="model-id">{{ m.id }}</span>
            </label>
          </div>
          <div v-else class="empty">点击"获取模型列表"加载上游模型</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showModelsModal = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveModels">{{ $t('common.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Test Modal -->
    <div v-if="showTestModal" class="modal-overlay" @click.self="showTestModal = false">
      <div class="modal">
        <div class="modal-header">测试 - {{ testProviderName }}</div>
        <div class="modal-body">
          <div class="form-group">
            <label>测试模型</label>
            <select v-model="testForm.test_model" class="form-input">
              <option value="">-- 选择模型 --</option>
              <option v-for="m in testModels" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
          <div v-if="testModels.length > 1" class="mt-3">
            <button class="btn btn-ghost" :disabled="batchTesting" @click="runBatchTest">
              {{ batchTesting ? `测试中 ${batchProgress}/${testModels.length}...` : `批量测试 (${testModels.length} 个模型)` }}
            </button>
          </div>
          <div v-if="batchResults.length" class="mt-3 batch-results">
            <div v-for="r in batchResults" :key="r.model" class="batch-result-item" :class="r.ok ? 'batch-ok' : 'batch-error'">
              <span class="batch-model mono">{{ r.model }}</span>
              <span class="batch-status">{{ r.ok ? '✓' : '✗' }}</span>
              <span class="batch-msg">{{ r.message }}</span>
            </div>
          </div>
          <div v-if="testResults[testProviderName]" class="test-result mt-3" :class="testResults[testProviderName].ok ? 'test-ok' : 'test-error'">
            {{ testResults[testProviderName].message }}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showTestModal = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" :disabled="testing[testProviderName]" @click="runTest">
            {{ testing[testProviderName] ? '测试中...' : '开始测试' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api'
import { ChevronRight, Zap, BookOpen, Pencil, Trash2, Search, Check, X, ShieldCheck, Download, CheckCircle, XCircle, Plus, ListChecks } from 'lucide-vue-next'

const loading = ref(true)
const providers = ref({})
const expanded = ref({})
const testing = ref({})
const testResults = ref({})
const verifying = ref({})
const verifyResults = ref({})
const stats = ref(null)

// Edit modal
const showEditModal = ref(false)
const editingName = ref('')
const editingProviderKeys = ref(0)
const editForm = ref({ name: '', base_url: '', api_key: '', provider_type: 'api', enabled: true, test_model: '', timeout: 30, rate_limit_cooldown: 60, cost_per_m_input: 0, cost_per_m_output: 0 })

// Add modal
const showAddModal = ref(false)
const addForm = ref({ name: '', base_url: '', provider_type: 'api', enabled: true, test_model: '', timeout: 30, rate_limit_cooldown: 60, cost_per_m_input: 0, cost_per_m_output: 0 })

// Test modal
const showTestModal = ref(false)
const testProviderName = ref('')
const testForm = ref({ test_model: '' })
const testModels = ref([])
const batchTesting = ref(false)
const batchProgress = ref(0)
const batchResults = ref([])

// Models modal
const showModelsModal = ref(false)
const modelsProvider = ref('')
const remoteModels = ref([])
const selectedModels = ref([])
const fetchingRemote = ref(false)
const modelSearch = ref('')

const keyList = computed(() => {
  const keys = stats.value?.keys || {}
  const result = []
  Object.entries(keys).forEach(([prov, data]) => {
    (data.keys || []).forEach(k => {
      result.push({ provider: prov, ...k })
    })
  })
  return result
})

const filteredModels = computed(() => {
  if (!modelSearch.value) return remoteModels.value
  const q = modelSearch.value.toLowerCase()
  return remoteModels.value.filter(m => m.id.toLowerCase().includes(q))
})

function getTypeBadgeClass(pc) {
  if (!pc.enabled) return 'badge-red'
  return pc.provider_type === 'web_reverse' ? 'badge-yellow' : 'badge-green'
}

function getModelCount(name) {
  const pc = providers.value[name]
  if (!pc || !pc.models) return 0
  return pc.models.include?.length || Object.keys(pc.models).length || 0
}

function getProbeLabel(key) {
  const labels = { 'text-gen': '文本生成', 'tool-call': '工具调用', 'streaming': '流式输出' }
  return labels[key] || key
}

async function fetchData() {
  try {
    const [p, s] = await Promise.all([api.getProviders(), api.getStats()])
    providers.value = p
    stats.value = s
    Object.keys(p).forEach((name) => { if (!(name in expanded.value)) expanded.value[name] = false })
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function toggleExpand(name) {
  expanded.value[name] = !expanded.value[name]
}

// Edit
function openEditModal(name, pc) {
  editingName.value = name
  editingProviderKeys.value = pc.keys?.length || 0
  editForm.value = { ...pc, name }
  showEditModal.value = true
}

function openAddModal() {
  addForm.value = { name: '', base_url: '', provider_type: 'api', enabled: true, test_model: '', timeout: 30, rate_limit_cooldown: 60, cost_per_m_input: 0, cost_per_m_output: 0 }
  showAddModal.value = true
}

async function saveAddProvider() {
  const { name, ...config } = addForm.value
  if (!name) { alert('请输入提供商名称'); return }
  try {
    await api.addProvider(name, config)
    showAddModal.value = false
    await fetchData()
  } catch (e) { alert(e.message) }
}

async function saveProvider() {
  const { name, ...config } = editForm.value
  try {
    await api.updateProvider(editingName.value, config)
    showEditModal.value = false
    await fetchData()
  } catch (e) { alert(e.message) }
}

async function deleteProvider(name) {
  if (!confirm(`确定要删除提供商 "${name}" 吗？`)) return
  await api.deleteProvider(name)
  await fetchData()
}

// Test
async function testProvider(name) {
  testing.value[name] = true
  try {
    const result = await api.testProvider(name)
    testResults.value[name] = { ok: result.status === 'ok', message: result.message }
  } catch (e) {
    testResults.value[name] = { ok: false, message: e.message }
  } finally {
    testing.value[name] = false
  }
}

async function verifyProvider(name) {
  verifying.value[name] = true
  verifyResults.value[name] = null
  try {
    const result = await api.verifyProvider(name)
    verifyResults.value[name] = result
  } catch (e) {
    verifyResults.value[name] = { overall_status: 'fail', message: e.message }
  } finally {
    verifying.value[name] = false
  }
}

function exportKeys(name) {
  window.open(`/api/export/keys/${name}?format=openai`, '_blank')
}

// Models
function openModelsModal(name) {
  modelsProvider.value = name
  selectedModels.value = []
  modelSearch.value = ''
  showModelsModal.value = true
  // Load cached remote models and enabled models in parallel
  api.getRemoteModels(name).then(data => {
    remoteModels.value = data.data || []
  }).catch(() => { remoteModels.value = [] })
  api.getEnabledModels(name).then(data => {
    selectedModels.value = data.include || []
  }).catch(() => {})
}

// Test modal
function openTestModal(name) {
  testProviderName.value = name
  testForm.value.test_model = ''
  testResults.value[name] = null
  showTestModal.value = true
  // Load enabled models for this provider
  api.getEnabledModels(name).then(data => {
    testModels.value = data.include || []
  }).catch(() => {
    testModels.value = []
  })
}

async function runTest() {
  if (!testForm.value.test_model) {
    testResults.value[testProviderName.value] = { ok: false, message: '请选择测试模型' }
    return
  }
  testing.value[testProviderName.value] = true
  try {
    const result = await api.testProvider(testProviderName.value, testForm.value.test_model)
    if (!result) {
      testResults.value[testProviderName.value] = { ok: false, message: '无响应' }
      return
    }
    testResults.value[testProviderName.value] = { 
      ok: result.status === 'ok', 
      message: result.message || result.error?.message || JSON.stringify(result) 
    }
  } catch (e) {
    testResults.value[testProviderName.value] = { ok: false, message: e.message }
  } finally {
    testing.value[testProviderName.value] = false
  }
}

async function runBatchTest() {
  if (!testModels.value.length) return
  batchTesting.value = true
  batchProgress.value = 0
  batchResults.value = []
  
  for (let i = 0; i < testModels.value.length; i++) {
    const model = testModels.value[i]
    batchProgress.value = i + 1
    try {
      const result = await api.testProvider(testProviderName.value, model)
      batchResults.value.push({
        model,
        ok: result?.status === 'ok',
        message: result?.message || result?.error?.message || '未知错误'
      })
    } catch (e) {
      batchResults.value.push({
        model,
        ok: false,
        message: e.message
      })
    }
  }
  
  batchTesting.value = false
}

async function fetchRemoteModels() {
  fetchingRemote.value = true
  try {
    const data = await api.getRemoteModels(modelsProvider.value)
    remoteModels.value = data.data || []
  } catch (e) { console.error(e) }
  finally { fetchingRemote.value = false }
}

function toggleModel(id) {
  const idx = selectedModels.value.indexOf(id)
  if (idx >= 0) selectedModels.value.splice(idx, 1)
  else selectedModels.value.push(id)
}

function selectAll() {
  filteredModels.value.forEach(m => {
    if (!selectedModels.value.includes(m.id)) selectedModels.value.push(m.id)
  })
}

function deselectAll() {
  selectedModels.value = []
}

async function saveModels() {
  try {
    await api.updateModels(modelsProvider.value, { include: selectedModels.value })
    showModelsModal.value = false
    await fetchData()
  } catch (e) { alert(e.message) }
}

onMounted(fetchData)
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
.card-title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.provider-list { display: flex; flex-direction: column; gap: 10px; }
.provider-item {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 10px);
  overflow: hidden;
}
.provider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.provider-header:hover { background: var(--color-bg-input); }
.provider-info { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.provider-text { min-width: 0; }
.provider-arrow {
  width: 16px;
  height: 16px;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--color-text-dim);
  flex-shrink: 0;
}
.provider-arrow.expanded { transform: rotate(90deg); }
.provider-name { font-weight: 600; font-size: 14px; white-space: nowrap; }
.provider-url { font-size: 12px; color: var(--color-text-dim); font-family: 'SF Mono', 'Fira Code', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; }
.provider-keys { font-size: 12px; color: var(--color-text-dim); flex-shrink: 0; white-space: nowrap; }
.provider-details { padding: 0 16px 16px; }
.detail-section { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--color-border); }
.detail-section:last-of-type { border-bottom: none; }
.detail-label { font-size: 12px; color: var(--color-text-dim); min-width: 80px; }
.detail-value { font-size: 12px; color: var(--color-text); }
.provider-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.danger-btn { color: var(--color-red); }
.danger-btn:hover { background: rgba(231,76,60,0.1); border-color: var(--color-red); color: var(--color-red); }
.test-result { margin-top: 12px; padding: 8px 12px; border-radius: 6px; font-size: 12px; }
.test-ok { background: rgba(0,184,148,0.1); border: 1px solid rgba(0,184,148,0.2); color: var(--color-green); }
.test-error { background: rgba(231,76,60,0.1); border: 1px solid rgba(231,76,60,0.2); color: var(--color-red); }
.verify-result { margin-top: 12px; padding: 12px; background: var(--color-bg-input); border-radius: 6px; }
.verify-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.verify-badge { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.verify-model { font-size: 12px; color: var(--color-text-dim); font-family: 'SF Mono', monospace; }
.verify-probes { display: flex; flex-direction: column; gap: 4px; }
.probe-item { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.probe-ok { color: var(--color-green); }
.probe-error { color: var(--color-red); }
.probe-name { color: var(--color-text); }
.probe-latency { color: var(--color-text-dim); margin-left: auto; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green { background: rgba(0,184,148,0.15); color: var(--color-green); }
.badge-red { background: rgba(231,76,60,0.15); color: var(--color-red); }
.badge-yellow { background: rgba(253,203,110,0.15); color: var(--color-yellow); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: var(--color-text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--color-border); }
td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
tr:last-child td { border-bottom: none; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { background: var(--color-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.btn-ghost:hover { border-color: var(--color-accent); color: var(--color-accent); }
.btn-sm { padding: 5px 10px; font-size: 11px; }
.btn-xs { padding: 3px 8px; font-size: 10px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 100; }
.light .modal-overlay { background: rgba(0,0,0,0.3); }
.modal { background: rgba(24, 24, 27, 0.75); backdrop-filter: blur(20px) saturate(180%); -webkit-backdrop-filter: blur(20px) saturate(180%); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; width: 100%; max-width: 440px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.04); }
.light .modal { background: rgba(255, 255, 255, 0.75); border: 1px solid rgba(0, 0, 0, 0.08); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.8); }
.modal-lg { max-width: 700px; }
.modal-header { padding: 16px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.light .modal-header { border-bottom: 1px solid rgba(0, 0, 0, 0.06); }
.modal-body { padding: 20px; overflow-y: auto; flex: 1; }
.modal-footer { padding: 16px 20px; border-top: 1px solid rgba(255, 255, 255, 0.06); display: flex; justify-content: flex-end; gap: 8px; }
.light .modal-footer { border-top: 1px solid rgba(0, 0, 0, 0.06); }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--color-text-dim); margin-bottom: 6px; }
.form-input { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.form-input:focus { outline: none; border-color: var(--color-accent); }
.form-input.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.form-input-sm { padding: 5px 10px; font-size: 12px; }
.checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }
.empty { text-align: center; padding: 30px; color: var(--color-text-dim); font-size: 13px; }
.loading { text-align: center; padding: 40px; color: var(--color-text-dim); }
.loading-sm { text-align: center; padding: 20px; }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border); border-top-color: var(--color-accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
.model-count { font-size: 12px; color: var(--color-text-dim); font-weight: 400; }
.models-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.models-search { flex: 1; min-width: 120px; position: relative; }
.models-search .search-icon { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); color: var(--color-text-dim); pointer-events: none; }
.models-search .form-input-sm { padding-left: 28px; }
.models-select { display: flex; gap: 4px; }
.models-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 4px; max-height: 400px; overflow-y: auto; }
.model-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: all 0.15s; }
.model-item:hover { background: var(--color-bg-input); transform: translateX(2px); }
.model-item.selected { background: rgba(108,92,231,0.1); border: 1px solid rgba(108,92,231,0.2); }
.model-check { color: var(--color-green); flex-shrink: 0; }
.model-id { font-family: 'SF Mono', 'Fira Code', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 768px) {
  .provider-header { flex-direction: column; align-items: flex-start; gap: 6px; }
  .provider-keys { align-self: flex-start; }
  .desktop-only { display: none; }
  .mobile-only { display: flex; }
}
@media (min-width: 769px) {
  .mobile-only { display: none; }
}
.mt-3 { margin-top: 12px; }
.batch-results { max-height: 200px; overflow-y: auto; }
.batch-result-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 4px; font-size: 12px; margin-bottom: 4px; }
.batch-ok { background: rgba(0,184,148,0.1); color: var(--color-green); }
.batch-error { background: rgba(231,76,60,0.1); color: var(--color-red); }
.batch-model { font-size: 11px; }
.batch-status { font-weight: bold; }
.batch-msg { color: var(--color-text-dim); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
</style>
