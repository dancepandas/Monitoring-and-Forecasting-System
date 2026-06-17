const BASE = '/api'

async function agentFetch(path, init = {}) {
  const token = localStorage.getItem('token')
  const headers = { ...init.headers }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (!(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `请求失败 (${res.status})`)
  }
  return res
}

export const agentApi = {
  initSession(sessionId, config = {}) {
    return agentFetch('/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, ...config })
    }).then(r => r.json())
  },

  fetchModels() {
    return agentFetch('/models').then(r => r.json())
  },

  fetchSessions() {
    return agentFetch('/sessions').then(r => r.json())
  },

  fetchSession(sessionId) {
    return agentFetch(`/sessions/${encodeURIComponent(sessionId)}`).then(r => r.json())
  },

  fetchSessionMessages(sessionId) {
    return agentFetch(`/sessions/${encodeURIComponent(sessionId)}/messages`).then(r => r.json())
  },

  deleteSession(sessionId) {
    return agentFetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
  },

  saveSession(sessionId) {
    return agentFetch('/sessions/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    }).then(r => r.json())
  },

  createChatRequest(sessionId, message, uploadedFiles = [], assistantMessageId) {
    return agentFetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        uploaded_files: uploadedFiles,
        assistant_message_id: assistantMessageId
      })
    })
  },

  resumeStream(sessionId, afterIndex = 0) {
    return agentFetch(`/stream/resume?session_id=${encodeURIComponent(sessionId)}&after_index=${afterIndex}`)
  },

  fetchSessionStatus(sessionId) {
    return agentFetch(`/session/status?session_id=${encodeURIComponent(sessionId)}`).then(r => r.json())
  },

  pauseSession(sessionId) {
    return agentFetch('/session/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    })
  },

  resumeSession(sessionId) {
    return agentFetch('/session/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    })
  },

  respondPermission(askId, approved, sessionId) {
    return agentFetch('/permission/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ask_id: askId, approved, session_id: sessionId })
    }).then(r => r.json())
  },

  uploadFile(sessionId, file) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('session_id', sessionId)
    return agentFetch('/upload', { method: 'POST', body: formData })
  },

  fetchScheduledTasks(sessionId) {
    const params = sessionId ? `session_id=${encodeURIComponent(sessionId)}` : 'include_all=1'
    return agentFetch(`/scheduled-tasks?${params}`).then(r => r.json())
  },

  deleteScheduledTask(taskId) {
    return agentFetch(`/scheduled-tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' })
  },

  createScheduledTask(sessionId, taskType, cron, params = {}) {
    return agentFetch('/scheduled-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, task_type: taskType, cron, params })
    }).then(r => r.json())
  }
}
