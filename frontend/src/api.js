const BASE = ''

function getToken() {
  return localStorage.getItem('access_token') || localStorage.getItem('token') || ''
}

function setToken(token) {
  localStorage.setItem('access_token', token)
  localStorage.setItem('token', token)
}

function clearToken() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('token')
}

function getAccessKey() {
  return localStorage.getItem('access_key') || ''
}

function setAccessKey(key) {
  localStorage.setItem('access_key', key)
}

async function request(url, options = {}) {
  const token = getToken()
  const accessKey = getAccessKey()
  const authHeader = token ? `Bearer ${token}` : (accessKey ? `Bearer ${accessKey}` : '')
  const headers = {
    'Content-Type': 'application/json',
    ...(authHeader ? { Authorization: authHeader } : {}),
    ...options.headers,
  }

  const resp = await fetch(BASE + url, { ...options, headers })

  if (resp.status === 401) {
    clearToken()
    throw new Error('Unauthorized')
  }

  const json = await resp.json()
  
  // Check for error status
  if (!resp.ok) {
    throw new Error(json.detail || json.message || `Error ${resp.status}`)
  }
  
  if (json && json.success === true && json.data !== undefined) {
    return json.data
  }
  return json
}

export { getToken, setToken, clearToken, getAccessKey, setAccessKey, request }

export const api = {
  // Auth
  checkSetupStatus: () => request('/api/setup/status'),
  register: (username, email, password) => request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password })
  }),
  login: (username, password) => request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  }),
  getMe: () => request('/api/auth/me'),
  changePassword: (oldPassword, newPassword) => request('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
  }),
  logout: () => {
    clearToken()
    return Promise.resolve({ ok: true })
  },

  // SSO
  getSSOStatus: () => request('/api/auth/sso/status'),
  getSSOLoginUrl: (redirectUri) => request('/api/auth/sso/login' + (redirectUri ? '?redirect_uri=' + encodeURIComponent(redirectUri) : '')),
  ssoLogout: (idToken) => request('/api/auth/sso/logout', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken })
  }),

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
  getFullConfig: () => request('/api/config/full'),
  updateFullConfig: (body) => request('/api/config/full', { method: 'PUT', body: JSON.stringify(body) }),

  // Providers
  getProviders: () => request('/api/providers'),
  addProvider: (name, config) => request('/api/providers', { method: 'POST', body: JSON.stringify({ name, config }) }),
  updateProvider: (name, config) => request(`/api/providers/${name}`, { method: 'PUT', body: JSON.stringify({ config }) }),
  deleteProvider: (name) => request(`/api/providers/${name}`, { method: 'DELETE' }),
  testProvider: (name, testModel) => request(`/api/providers/${name}/test`, { 
  method: 'POST',
  body: testModel ? JSON.stringify({ model: testModel }) : undefined
}),

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
  getGistInfo: () => request('/api/sync/gist-info'),
  findGist: (token) => request('/api/sync/find-gist', { method: 'POST', body: JSON.stringify({ gist_token: token }) }),
  setupSync: (token, gistId) => request('/api/sync/setup', { method: 'POST', body: JSON.stringify({ gist_token: token, gist_id: gistId || '' }) }),
  pushSync: () => request('/api/sync/push', { method: 'POST' }),
  pullSync: (token, force = false) => request('/api/sync/pull', { method: 'POST', body: JSON.stringify({ gist_token: token || '', force }) }),
  verifyToken: (token) => request('/api/sync/verify-token', { method: 'POST', body: JSON.stringify({ gist_token: token || '' }) }),
  getSyncHistory: () => request('/api/sync/history'),

  // Users (Admin Only)
  getUsers: () => request('/api/users'),
  updateUser: (id, data) => request(`/api/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteUser: (id) => request(`/api/users/${id}`, { method: 'DELETE' }),

  // Enhanced Features - Analytics
  getAnalyticsOverview: () => request('/api/analytics/overview'),
  getAnalyticsSlowQueries: (limit = 10) => request(`/api/analytics/slow-queries?limit=${limit}`),
  getAnalyticsCostDistribution: () => request('/api/analytics/cost-distribution'),

  // Enhanced Features - Health Check
  runHealthCheck: () => request('/api/health-check', { method: 'POST' }),

  // Enhanced Features - Model Verification
  verifyProvider: (name, model = null) => request(`/api/providers/${name}/verify`, {
    method: 'POST',
    body: JSON.stringify({ model })
  }),

  // Enhanced Features - Export
  exportProviderKeys: (providerName, format = 'openai') => request(`/api/export/keys/${providerName}?format=${format}`),

  // Enhanced Features - Enhanced Stats
  getEnhancedStats: () => request('/api/stats/enhanced'),
  getModelsPricing: () => request('/api/models/pricing'),
}
