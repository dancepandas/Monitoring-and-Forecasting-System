// ── 郴州四站配置（与后端 station_names.STATIONS 保持一致）──
export const PRIMARY_STATION = '00125'
export const ALL_STATION_CODES = '00125,00230,00231,00234'

import { apiRequest } from './client.js'

async function request(path, options = {}) {
  const res = await apiRequest(path, options)
  return res.json()
}

export const api = {
  login: (username, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),

  getLatest: (stationCodes = ALL_STATION_CODES) =>
    request(`/data/latest?station_codes=${encodeURIComponent(stationCodes)}`),

  getLevel: (stationCode, begin = '', end = '', count = 200) => {
    const p = new URLSearchParams({ station_code: stationCode, begin_time: begin, end_time: end, count })
    return request(`/data/level?${p}`)
  },

  getFlow: (stationCode, begin = '', end = '', count = 200) => {
    const p = new URLSearchParams({ station_code: stationCode, begin_time: begin, end_time: end, count })
    return request(`/data/flow?${p}`)
  },

  getFlowRaw: (stationCode, deviceCode, begin = '', end = '', count = 200) => {
    const p = new URLSearchParams({ station_code: stationCode, device_code: deviceCode, begin_time: begin, end_time: end, count })
    return request(`/data/flow-raw?${p}`)
  },

  runForecast: (data) =>
    request('/forecast/run', { method: 'POST', body: JSON.stringify(data) }),

  getForecastResult: (stationCode) =>
    request(`/forecast/result?station_code=${encodeURIComponent(stationCode)}`),

  getForecastInterpret: (stationCode, field = 'virtualFlow') =>
    request(`/forecast/interpret?station_code=${encodeURIComponent(stationCode)}&field=${encodeURIComponent(field)}`),

  getWarnings: (stationCodes = ALL_STATION_CODES) =>
    request(`/data/warnings?station_codes=${encodeURIComponent(stationCodes)}`),

  getDisposal: (stationCode, level = 'yellow', metric = 'level') =>
    request(`/data/disposal?station_code=${encodeURIComponent(stationCode)}&level=${level}&metric=${metric}`),

  getDisposalAgent: (stationCode, level = 'yellow', metric = 'level', wlValue = 0, vfValue = 0) => {
    const p = new URLSearchParams({ station_code: stationCode, level, metric, wl_value: wlValue, vf_value: vfValue })
    return request(`/data/disposal/agent?${p}`)
  },

  getVideoFeeds: (stationCodes = ALL_STATION_CODES) =>
    request(`/data/video-feeds?station_codes=${encodeURIComponent(stationCodes)}`),

  getVideoSnapshots: (stationCode = '__all__', limit = 10) =>
    request(`/data/video-snapshots?station_code=${encodeURIComponent(stationCode)}&limit=${limit}`),

  getAllVideoSnapshots: (limit = 10) =>
    request(`/data/video-snapshots?station_code=__all__&limit=${limit}`),

  getDeviceStats: (stationCodes = ALL_STATION_CODES) =>
    request(`/data/device-stats?station_codes=${encodeURIComponent(stationCodes)}`),

  listReports: (type = '') => {
    const params = type ? `?report_type=${encodeURIComponent(type)}` : ''
    return request(`/reports/list${params}`)
  },

  downloadReport: (filename) =>
    `/api/reports/download/${encodeURIComponent(filename)}`,

  previewReport: (filename) =>
    request(`/reports/preview/${encodeURIComponent(filename)}`),

  generateReport: (data) =>
    request('/reports/generate', { method: 'POST', body: JSON.stringify(data) }),

  getSystemStatus: () =>
    request('/system/status'),

  triggerSystemCheck: () =>
    request('/system/check', { method: 'POST' }),

  getAlignedChart: (stationCode, field = 'virtualFlow') =>
    request(`/data/aligned/chart?station_code=${encodeURIComponent(stationCode)}&field=${encodeURIComponent(field)}`),

  getStats: (stationCode, field = 'virtualFlow') =>
    request(`/data/stats?station_code=${encodeURIComponent(stationCode)}&field=${encodeURIComponent(field)}`),

  getActiveAlerts: (stationCode = '', level = '') => {
    const p = new URLSearchParams()
    if (stationCode) p.set('station_code', stationCode)
    if (level) p.set('level', level)
    const qs = p.toString()
    return request(`/alerts/active${qs ? '?' + qs : ''}`)
  },

  getAlertHistory: (limit = 50) =>
    request(`/alerts/history?limit=${limit}`),

  acknowledgeAlert: (alertId) =>
    request(`/alerts/${encodeURIComponent(alertId)}/acknowledge`, { method: 'POST', body: JSON.stringify({ by: 'operator' }) }),

  resolveAlert: (alertId, resolution = '人工解除') =>
    request(`/alerts/${encodeURIComponent(alertId)}/resolve`, { method: 'POST', body: JSON.stringify({ resolution, by: 'operator' }) }),

  getUsers: () =>
    request('/auth/users'),

  getScheduledTasks: () =>
    request('/scheduled-tasks'),

  getWarningStandards: () =>
    request('/data/warning-standards'),
}
