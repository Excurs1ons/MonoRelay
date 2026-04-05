const BASE = ''

function getToken() {
  return localStorage.getItem('access_token') || ''
}

async function request(url, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const resp = await fetch(BASE + url, { ...options, headers })

  if (resp.status === 401) {
    localStorage.removeItem('access_token')
    throw new Error('Unauthorized')
  }

  return resp.json()
}

export const api = {
  // Info & Health
  getInfo: () => request('/api/info'),
  health: () => request('/health'),

  // Stats
  getStats: () => request('/api/stats'),
  getStatsFile: () => request('/api/stats/file'),
  updateStatsFile: (content) => request('/api/stats/file', { method: 'PUT', body: JSON.stringify({ content }) }),

  // Logs
  getLogs: (limit = 50) => request(`/api/logs?limit=${limit}`),

  // Config
  getConfig: () => request('/api/config'),
  updateConfig: (body) => request('/api/config', { method: 'PUT', body: JSON.stringify(body) }),

  // Providers
  getProviders: () => request('/api/providers'),
  addProvider: (name, config) => request('/api/providers', { method: 'POST', body: JSON.stringify({ name, config }) }),
  updateProvider: (name, config) => request(`/api/providers/${name}`, { method: 'PUT', body: JSON.stringify({ config }) }),
  deleteProvider: (name) => request(`/api/providers/${name}`, { method: 'DELETE' }),
  testProvider: (name) => request(`/api/providers/${name}/test`, { method: 'POST' }),

  // Keys
  addKey: (name, keyData) => request(`/api/providers/${name}/keys`, { method: 'POST', body: JSON.stringify(keyData) }),
  updateKey: (name, index, keyData) => request(`/api/providers/${name}/keys/${index}`, { method: 'PUT', body: JSON.stringify(keyData) }),
  deleteKey: (name, index) => request(`/api/providers/${name}/keys/${index}`, { method: 'DELETE' }),

  // Models
  getRemoteModels: (name) => request(`/api/providers/${name}/models/remote`),
  getEnabledModels: (name) => request(`/api/providers/${name}/models/enabled`),
  updateModels: (name, data) => request(`/api/providers/${name}/models`, { method: 'PUT', body: JSON.stringify(data) }),

  // Router
  getRouterInfo: () => request('/api/router'),

  // Sync
  getSyncStatus: () => request('/api/sync'),
  findGist: (token) => request('/api/sync/find-gist', { method: 'POST', body: JSON.stringify({ gist_token: token }) }),
  setupSync: (token, gistId) => request('/api/sync/setup', { method: 'POST', body: JSON.stringify({ gist_token: token, gist_id: gistId || '' }) }),
  pushSync: () => request('/api/sync/push', { method: 'POST' }),
  pullSync: (token) => request('/api/sync/pull', { method: 'POST', body: JSON.stringify({ gist_token: token || '' }) }),
  verifyToken: (token) => request('/api/sync/verify-token', { method: 'POST', body: JSON.stringify({ gist_token: token || '' }) }),
  getSyncHistory: () => request('/api/sync/history'),
}
