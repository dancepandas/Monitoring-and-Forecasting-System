const BASE = '/api'

function getToken() {
  return localStorage.getItem('token')
}

function authHeaders(extra = {}) {
  const token = getToken()
  const headers = { ...extra }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

async function _fetchWithTimeout(url, options, timeout) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal })
    return res
  } finally {
    clearTimeout(timer)
  }
}

/**
 * JSON 请求客户端 —— 自动重试 + 401 跳转 + JSON 错误提取。
 */
export async function apiRequest(path, options = {}) {
  const method = options.method || 'GET'
  const headers = authHeaders({ 'Content-Type': 'application/json', ...options.headers })
  const url = `${BASE}${path}`
  const timeout = options.timeout || 30000
  const retries = options.retries ?? 1

  let lastErr
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await _fetchWithTimeout(url, { ...options, headers }, timeout)
      if (res.status === 401) {
        localStorage.removeItem('token')
        window.location.href = '/login'
        throw new Error('登录已过期')
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `请求失败 (${res.status})`)
      }
      return res
    } catch (e) {
      lastErr = e
      if (e.name === 'AbortError') throw new Error(`请求超时 (${timeout / 1000}s)`)
      if (i >= retries) throw lastErr
    }
  }
}

/**
 * 流式请求客户端 —— 返回 Response 对象，不解析 JSON。
 * 用于 Agent SSE 流、文件下载等场景。
 */
export async function streamRequest(path, init = {}) {
  const headers = authHeaders(init.headers)
  if (!(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    throw new Error('登录已过期')
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `请求失败 (${res.status})`)
  }
  return res
}
