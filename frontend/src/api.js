const BASE = ''

export function getToken() {
  return localStorage.getItem('access_token') || localStorage.getItem('token') || ''
}

export function setToken(token) {
  localStorage.setItem('access_token', token)
  localStorage.setItem('token', token)
}

export function setAccessKey(key) {
  localStorage.setItem('access_key', key)
}

export function clearToken() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('token')
}

async function request(url, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
    ...(options.headers || {})
  }

  const resp = await fetch(url, { ...options, headers })
  
  if (resp.status === 401 && !url.includes('/api/auth/login')) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  const contentType = resp.headers.get('content-type') || ''
  let json
  if (!resp.ok || !contentType.includes('application/json')) {
    const text = await resp.text()
    if (!resp.ok) {
      throw new Error(text || `Error ${resp.status}`)
    }
    try {
      json = JSON.parse(text)
    } catch {
      json = {}
    }
  } else {
    json = await resp.json()
  }
  
  if (!resp.ok) {
    throw new Error(json?.detail || json?.message || json?.error?.message || `Error ${resp.status}`)
  }
  
  if (json && json.success === true && json.data !== undefined) {
    return json.data
  }
  if (json && json.detail) {
    throw new Error(json.detail)
  }
  return json
}

export const api = {
  login: (username, password) => request('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username, password, email) => request('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password, email }) }),
  getMe: () => request('/api/auth/me'),
  hasUsers: () => request('/api/auth/has_users'),
  getFullConfig: () => request('/api/config/full'),
  updateFullConfig: (config) => request('/api/config/full', { method: 'POST', body: JSON.stringify(config) }),
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
  getSystemInfo: () => request('/api/system/info'),
  health: (turnstileToken = '') => request('/health' + (turnstileToken ? `?turnstile_token=${turnstileToken}` : '')),

  // Stats
  getStats: () => request('/api/stats'),
  getLogs: (limit = 50) => request('/api/logs?limit=' + limit),
  getLogDetail: (id) => request('/api/logs/' + id),
  clearLogs: () => request('/api/logs/clear', { method: 'POST' }),
  resetStats: () => request('/api/stats/reset', { method: 'POST' }),
  getProviders: () => request('/api/providers'),
  updateProvider: (name, config) => request('/api/providers/' + name, { method: 'POST', body: JSON.stringify(config) }),
  testProvider: (name) => request('/api/providers/' + name + '/test', { method: 'POST' }),
  deleteProvider: (name) => request('/api/providers/' + name, { method: 'DELETE' }),
  getUserKeys: () => request('/api/user/keys'),
  createUserKey: (label) => request('/api/user/keys', { method: 'POST', body: JSON.stringify({ label }) }),
  getUserStats: () => request('/api/user/stats'),
  getUserLogs: (limit = 50) => request('/api/user/logs?limit=' + limit),
  getUsers: () => request('/api/admin/users'),
  updateUserBalance: (id, adjustment) => request('/api/admin/users/' + id + '/balance', { method: 'POST', body: JSON.stringify({ adjustment }) }),
  deleteUser: (id) => request('/api/admin/users/' + id, { method: 'DELETE' }),
  getEnhancedStats: () => request('/api/stats/enhanced'),
  getModelsPricing: () => request('/api/models/pricing'),
  clearAllData: () => request('/api/config/clear', { method: 'POST' }),

  // Billing & Redemption
  getRedemptionCodes: () => request('/api/admin/redemption-codes'),
  createRedemptionCodes: (amount, count, prefix) => request('/api/admin/redemption-codes', { method: 'POST', body: JSON.stringify({ amount, count, prefix }) }),
  redeemCode: (code) => request('/api/user/redeem', { method: 'POST', body: JSON.stringify({ code }) }),
}
