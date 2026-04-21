const BASE = ''

function getToken() {
  return localStorage.getItem('access_token') || localStorage.getItem('token') || ''
}

function setToken(token) {
  localStorage.setItem('access_token', token)
  localStorage.setItem('token', token)
}

async function request(url, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  }

  const response = await fetch(url, { ...options, headers })
  
  if (response.status === 401 && !url.includes('/api/auth/login')) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  const json = await response.json()
  if (json && json.success === true && json.data !== undefined) {
    return json.data
  }
  if (json && json.detail) {
    throw new Error(json.detail)
  }
  return json
}

export const api = {
  // Auth
  login: (username, password) => request('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username, password, email) => request('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password, email }) }),
  getMe: () => request('/api/auth/me'),
  hasUsers: () => request('/api/auth/has_users'),

  // Admin Config
  getFullConfig: () => request('/api/config/full'),
  updateFullConfig: (config) => request('/api/config/full', { method: 'POST', body: JSON.stringify(config) }),
  
  // Admin Stats & Logs
  getStats: () => request('/api/stats'),
  getLogs: (limit = 50) => request(`/api/logs?limit=${limit}`),
  getLogDetail: (id) => request(`/api/logs/${id}`),
  clearLogs: () => request('/api/logs/clear', { method: 'POST' }),
  resetStats: () => request('/api/stats/reset', { method: 'POST' }),
  
  // Admin Providers & Keys
  getProviders: () => request('/api/providers'),
  updateProvider: (name, config) => request(`/api/providers/${name}`, { method: 'POST', body: JSON.stringify(config) }),
  testProvider: (name) => request(`/api/providers/${name}/test`, { method: 'POST' }),
  deleteProvider: (name) => request(`/api/providers/${name}`, { method: 'DELETE' }),

  // Multi-tenant User API
  getUserKeys: () => request('/api/user/keys'),
  createUserKey: (label) => request('/api/user/keys', { method: 'POST', body: JSON.stringify({ label }) }),
  getUserStats: () => request('/api/user/stats'),
  getUserLogs: (limit = 50) => request(`/api/user/logs?limit=${limit}`),

  // Users Management (Admin)
  getUsers: () => request('/api/users'),
  
  // Enhanced Features
  getEnhancedStats: () => request('/api/stats/enhanced'),
  getModelsPricing: () => request('/api/models/pricing'),
  clearAllData: () => request('/api/config/clear', { method: 'POST' }),
}
