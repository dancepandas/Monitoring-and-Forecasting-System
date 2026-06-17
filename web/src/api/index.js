const BASE = '/api'

async function _fetchOnce(path, options, timeout) {
  const url = `${BASE}${path}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => {
    console.warn(`[api] timeout after ${timeout}ms: ${url}`)
    ctrl.abort()
  }, timeout)

  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal })
    clearTimeout(timer)
    return res
  } catch (e) {
    clearTimeout(timer)
    throw e
  }
}

async function request(path, options = {}) {
  const token = localStorage.getItem('token')
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = `${BASE}${path}`
  const timeout = options.timeout || 30000
  const retries = options.retries ?? 1

  console.log(`[api] request -> ${options.method || 'GET'} ${url}`)
  let lastErr
  for (let i = 0; i <= retries; i++) {
    try {
      if (i > 0) console.log(`[api] retry ${i} -> ${url}`)
      const res = await _fetchOnce(path, { ...options, headers }, timeout)
      console.log(`[api] response <- ${url} status=${res.status}`)
      if (res.status === 401) {
        localStorage.removeItem('token')
        window.location.href = '/login'
        throw new Error('登录已过期')
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        console.error(`[api] error <- ${url} status=${res.status}`, err)
        throw new Error(err.detail || `请求失败 (${res.status})`)
      }
      const data = await res.json()
      console.log(`[api] data <- ${url}`, data)
      return data
    } catch (e) {
      lastErr = e
      if (e.name === 'AbortError') {
        console.error(`[api] aborted by timeout: ${url}`)
        lastErr = new Error(`请求超时 (${timeout}ms)`)
        if (i < retries) continue
      } else {
        console.error(`[api] fetch failed: ${url}`, e)
      }
      throw lastErr
    }
  }
  throw lastErr
}

export const api = {
  login: (username, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),

  getLatest: (stationCodes = '00106') =>
    request(`/data/latest?station_codes=${stationCodes}`),

  getLevel: (stationCode, begin = '', end = '') => {
    const params = new URLSearchParams({ station_code: stationCode })
    if (begin) { params.set('begin_time', begin); params.set('end_time', end || begin) }
    return request(`/data/level?${params}`)
  },

  getFlow: (stationCode, begin = '', end = '') => {
    const params = new URLSearchParams({ station_code: stationCode })
    if (begin) { params.set('begin_time', begin); params.set('end_time', end || begin) }
    return request(`/data/flow?${params}`)
  },

  getFlowRaw: (stationCode, deviceCode, begin = '', end = '') => {
    const params = new URLSearchParams({ station_code: stationCode, device_code: deviceCode })
    if (begin) { params.set('begin_time', begin); params.set('end_time', end || begin) }
    return request(`/data/flow-raw?${params}`)
  },

  runForecast: (stationCode, predictionLength = 72, mode = 'univariate', contextLength = 72) =>
    request('/forecast/run', {
      method: 'POST',
      body: JSON.stringify({ station_code: stationCode, prediction_length: predictionLength, context_length: contextLength, mode })
    }),

  getForecastResult: (stationCode) =>
    request(`/forecast/result?station_code=${stationCode}`),

  getWarnings: (stationCodes = '00106') =>
    request(`/data/warnings?station_codes=${stationCodes}`),

  getDisposal: (stationCode, level = 'yellow', metric = 'level') =>
    request(`/data/disposal?station_code=${stationCode}&level=${level}&metric=${metric}`),

  getVideoFeeds: (stationCodes = '00106,00107,00108') =>
    request(`/data/video-feeds?station_codes=${stationCodes}`),

  getDeviceStats: (stationCodes = '00106,00107,00108') =>
    request(`/data/device-stats?station_codes=${stationCodes}`),

  // ── 报告 ──
  listReports: (type = '') => {
    const params = type ? `?report_type=${encodeURIComponent(type)}` : ''
    return request(`/reports/list${params}`)
  },

  downloadReport: (filename) => `${BASE}/reports/download/${encodeURIComponent(filename)}`,

  previewReport: (filename) => request(`/reports/preview/${encodeURIComponent(filename)}`),

  generateReport: (data) => request('/reports/generate', { method: 'POST', body: JSON.stringify(data) }),

  // ── 系统状态 ──
  getSystemStatus: () => request('/system/status'),

  triggerSystemCheck: () => request('/system/check', { method: 'POST' }),

  // ── 对齐图表数据 ──
  getAlignedChart: (stationCode, field = 'virtualFlow') =>
    request(`/data/aligned/chart?station_code=${stationCode}&field=${field}`),

  getStats: (stationCode, field) =>
    request(`/data/stats?station_code=${stationCode}&field=${field}`),

  // ── 管理 ──
  getUsers: () => request('/auth/users'),

  getScheduledTasks: () => request('/scheduled-tasks'),

  getReportsList: (type = '') => {
    const params = type ? `?report_type=${encodeURIComponent(type)}` : ''
    return request(`/reports/list${params}`)
  },
}
