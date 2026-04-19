<template>
  <div>
    <div class="flex-between mb-4">
      <h2 class="section-title">{{ $t('keys.title') }}</h2>
      <button v-if="selectedProvider" class="btn btn-primary" @click="openModal()">{{ $t('common.add') }}</button>
    </div>

    <div v-if="providerList.length" class="mb-4">
      <select v-model="selectedProvider" class="form-input" style="max-width:280px">
        <option value="">{{ $t('keys.selectProvider') }}</option>
        <option v-for="p in providerList" :key="p" :value="p">{{ p }}</option>
      </select>
    </div>
    <div v-else class="empty">{{ $t('keys.noProvider') }}</div>

    <div v-if="selectedProvider" class="key-list">
      <div v-for="(k, idx) in currentKeys" :key="idx" class="key-item">
        <div class="key-info">
          <span class="key-label">{{ k.label || `Key #${idx + 1}` }}</span>
          <span class="badge" :class="k.enabled ? 'badge-green' : 'badge-red'">
            {{ k.enabled ? $t('common.enabled') : $t('common.disabled') }}
          </span>
          <span class="key-value mono">{{ maskKey(k.key) }}</span>
          <span v-if="k.weight > 1" class="key-weight">{{ $t('keys.weight') }}: {{ k.weight }}</span>
        </div>
        <div class="key-actions">
          <button class="btn btn-ghost btn-sm" @click="openModal(idx, k)">{{ $t('common.edit') }}</button>
          <button class="btn btn-sm" style="color:var(--color-red)" @click="deleteKey(idx)">{{ $t('common.delete') }}</button>
        </div>
      </div>
      <div v-if="!currentKeys.length" class="empty">{{ $t('dashboard.noData') }}</div>
    </div>

    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal">
        <div class="modal-header">{{ editingIndex >= 0 ? $t('keys.editKey') : $t('keys.addKey') }}</div>
        <div class="modal-body">
          <div class="form-group">
            <label>{{ $t('keys.key') }}</label>
            <input v-model="form.key" type="text" class="form-input mono" />
          </div>
          <div class="form-group">
            <label>{{ $t('keys.label') }}</label>
            <input v-model="form.label" type="text" class="form-input" />
          </div>
          <div class="form-group">
            <label>{{ $t('keys.weight') }}</label>
            <input v-model.number="form.weight" type="number" min="1" class="form-input" />
          </div>
          <label class="checkbox-label">
            <input v-model="form.enabled" type="checkbox" />
            {{ $t('common.enabled') }}
          </label>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showModal = false">{{ $t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveKey">{{ $t('common.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import { useToastStore } from '@/stores'

const { t } = useI18n()
const toast = useToastStore()

const providers = ref({})
const selectedProvider = ref('')
const showModal = ref(false)
const editingIndex = ref(-1)
const form = ref({ key: '', label: '', weight: 1, enabled: true })

const providerList = computed(() => Object.keys(providers.value))
const currentKeys = computed(() => providers.value[selectedProvider.value]?.keys || [])

function maskKey(key) {
  if (!key) return ''
  return key.length > 16 ? key.slice(0, 8) + '...' + key.slice(-4) : key
}

async function fetchProviders() {
  try {
    providers.value = await api.getProviders()
    if (!selectedProvider.value && providerList.value.length) selectedProvider.value = providerList.value[0]
  } catch (e) { console.error(e) }
}

function openModal(idx, k) {
  editingIndex.value = idx ?? -1
  form.value = k ? { ...k } : { key: '', label: '', weight: 1, enabled: true }
  showModal.value = true
}

async function saveKey() {
  try {
    if (editingIndex.value >= 0) await api.updateKey(selectedProvider.value, editingIndex.value, form.value)
    else await api.addKey(selectedProvider.value, form.value)
    showModal.value = false
    toast.success('保存成功')
    await fetchProviders()
  } catch (e) { 
    toast.error(e.message || '保存失败')
  }
}

async function deleteKey(idx) {
  if (!confirm(t('keys.deleteConfirm'))) return
  try {
    await api.deleteKey(selectedProvider.value, idx)
    toast.success('删除成功')
    await fetchProviders()
  } catch (e) { 
    toast.error(e.message || '删除失败')
  }
}

onMounted(fetchProviders)
</script>

<style scoped>
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 16px; font-weight: 600; }
.mb-4 { margin-bottom: 16px; }
.key-list { display: flex; flex-direction: column; gap: 8px; }
.key-item { display: flex; align-items: center; justify-content: space-between; background: var(--color-bg-input); padding: 12px 16px; border-radius: 8px; }
.key-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.key-label { font-weight: 600; font-size: 13px; }
.key-value { font-size: 12px; color: var(--color-text-dim); }
.key-weight { font-size: 11px; color: var(--color-text-dim); }
.key-actions { display: flex; gap: 6px; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green { background: rgba(0,184,148,0.15); color: var(--color-green); }
.badge-red { background: rgba(231,76,60,0.15); color: var(--color-red); }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.btn-primary { background: var(--color-accent); color: #fff; }
.btn-primary:hover { background: var(--color-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-text-dim); border: 1px solid var(--color-border); }
.btn-ghost:hover { border-color: var(--color-accent); color: var(--color-accent); }
.btn-sm { padding: 5px 10px; font-size: 11px; }
.form-input { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--color-border); background: var(--color-bg-input); color: var(--color-text); font-size: 13px; }
.form-input:focus { outline: none; border-color: var(--color-accent); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
.light .modal-overlay { background: rgba(0,0,0,0.3); }
.modal { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius, 10px); width: 100%; max-width: 440px; }
.modal-header { padding: 16px 20px; border-bottom: 1px solid var(--color-border); font-weight: 600; font-size: 14px; }
.modal-body { padding: 20px; }
.modal-footer { padding: 16px 20px; border-top: 1px solid var(--color-border); display: flex; justify-content: flex-end; gap: 8px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--color-text-dim); margin-bottom: 6px; }
.checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }
.empty { text-align: center; padding: 30px; color: var(--color-text-dim); font-size: 13px; }
.toast-error { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 8px; padding: 12px 16px; font-size: 13px; }
.toast-success { background: rgba(34,197,94,0.15); border: 1px solid rgba(34,197,94,0.3); color: #22c55e; border-radius: 8px; padding: 12px 16px; font-size: 13px; }
</style>
