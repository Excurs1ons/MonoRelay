<template>
  <div>
    <h2 class="section-title mb-4">{{ $t('models.title') }}</h2>

    <div class="flex-between mb-4">
      <select v-model="selectedProvider" class="form-input" style="max-width:280px">
        <option value="">{{ $t('models.selectProvider') }}</option>
        <option v-for="p in providerList" :key="p" :value="p">{{ p }}</option>
      </select>
      <button v-if="selectedProvider" class="btn btn-ghost" :disabled="fetchingRemote" @click="fetchRemoteModels(true)">
        {{ fetchingRemote ? $t('common.loading') : '获取模型列表' }}
      </button>
    </div>

    <div v-if="selectedProvider && !remoteModels.length" class="empty mb-4">
      暂无模型数据，请点击"获取模型列表"
    </div>

    <div v-if="selectedProvider && remoteModels.length" class="models-grid">
      <div class="card">
        <div class="card-title flex-between">
          {{ $t('models.remoteModels') }}
          <span class="text-dim text-xs">{{ remoteModels.length }} 个</span>
          <div class="flex gap-2">
            <button class="btn btn-ghost btn-xs" @click="selectAll">{{ $t('models.selectAll') }}</button>
            <button class="btn btn-ghost btn-xs" @click="deselectAll">{{ $t('models.deselectAll') }}</button>
          </div>
        </div>
        <div class="model-list">
          <label v-for="m in remoteModels" :key="m.id" class="model-item">
            <input type="checkbox" :checked="selectedModels.includes(m.id)" @change="toggleModel(m.id)" />
            <span class="mono">{{ m.id }}</span>
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-title flex-between">
          {{ $t('models.enabledModels') }}
          <span class="text-dim text-xs">{{ $t('models.selected', { count: selectedModels.length }) }}</span>
        </div>
        <div class="model-list">
          <div v-for="m in selectedModels" :key="m" class="model-tag">
            <span class="mono">{{ m }}</span>
            <button class="model-remove" @click="toggleModel(m)">×</button>
          </div>
          <div v-if="!selectedModels.length" class="empty">{{ $t('dashboard.noData') }}</div>
        </div>
        <div class="mt-3">
          <button class="btn btn-primary btn-block" @click="saveModels">{{ $t('models.saveModels') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/api'
import { useToastStore } from '@/stores'

const toast = useToastStore()

const providers = ref({})
const selectedProvider = ref('')
const remoteModels = ref([])
const enabledModels = ref([])
const fetchingRemote = ref(false)

const providerList = computed(() => Object.keys(providers.value))
const selectedModels = computed({ get: () => enabledModels.value, set: (v) => { enabledModels.value = v } })

async function fetchProviders() {
  try {
    providers.value = await api.getProviders()
    if (!selectedProvider.value && providerList.value.length) selectedProvider.value = providerList.value[0]
  } catch (e) { console.error(e) }
}

async function fetchRemoteModels(force = false) {
  if (!selectedProvider.value) return
  fetchingRemote.value = true
  try {
    const data = await api.getRemoteModels(selectedProvider.value)
    remoteModels.value = data.data || []
    if (!force && !remoteModels.value.length) {
      toast.info('点击"获取模型列表"从上游加载')
    }
  } catch (e) { console.error(e) }
  finally { fetchingRemote.value = false }
}

async function fetchEnabledModels() {
  if (!selectedProvider.value) return
  try {
    const data = await api.getEnabledModels(selectedProvider.value)
    enabledModels.value = data.include || []
  } catch (e) { console.error(e) }
}

watch(selectedProvider, async (newVal) => {
  if (newVal) {
    await fetchRemoteModels()
    await fetchEnabledModels()
  }
})

function toggleModel(id) {
  const idx = enabledModels.value.indexOf(id)
  if (idx >= 0) enabledModels.value.splice(idx, 1)
  else enabledModels.value.push(id)
}

function selectAll() {
  remoteModels.value.forEach((m) => { if (!enabledModels.value.includes(m.id)) enabledModels.value.push(m.id) })
}

function deselectAll() { enabledModels.value = [] }

async function saveModels() {
  await api.updateModels(selectedProvider.value, { include: enabledModels.value })
  toast.success('模型配置已保存')
}

onMounted(async () => {
  await fetchProviders()
})
</script>

<style scoped>
.section-title { font-size: 16px; font-weight: 600; }
.mb-4 { margin-bottom: 16px; }
.mt-3 { margin-top: 12px; }
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.flex { display: flex; }
.gap-2 { gap: 8px; }
.models-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); padding: 20px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
.model-list { max-height: 400px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 6px; }
.model-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: background 0.15s; }
.model-item:hover { background: var(--color-bg-input); }
.model-tag { display: flex; align-items: center; gap: 8px; padding: 4px 10px; background: var(--color-bg-input); border-radius: 6px; font-size: 12px; }
.model-remove { background: none; border: none; color: var(--color-red); cursor: pointer; font-size: 16px; line-height: 1; padding: 0 2px; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.text-dim { color: var(--color-text-dim); }
.text-xs { font-size: 11px; }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { background: var(--color-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.btn-ghost:hover { border-color: var(--color-accent); color: var(--color-accent); }
.btn-xs { padding: 4px 10px; font-size: 11px; }
.btn-block { width: 100%; justify-content: center; }
.form-input { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.form-input:focus { outline: none; border-color: var(--color-accent); }
.empty { text-align: center; padding: 30px; color: var(--color-text-dim); font-size: 13px; width: 100%; }
</style>
