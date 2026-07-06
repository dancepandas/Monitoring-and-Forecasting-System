import { streamRequest } from './client.js'

export const agentApi = {
  initSession(sessionId, config = {}) {
    return streamRequest('/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, ...config })
    }).then(r => r.json())
  },

  fetchModels() {
    return streamRequest('/models').then(r => r.json())
  },

  fetchSessions() {
    return streamRequest('/sessions').then(r => r.json())
  },

  fetchSession(sessionId) {
    return streamRequest(`/sessions/${encodeURIComponent(sessionId)}`).then(r => r.json())
  },

  fetchSessionMessages(sessionId) {
    return streamRequest(`/sessions/${encodeURIComponent(sessionId)}/messages`).then(r => r.json())
  },

  deleteSession(sessionId) {
    return streamRequest(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
  },

  saveSession(sessionId) {
    return streamRequest('/sessions/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    }).then(r => r.json())
  },

  createChatRequest(sessionId, message, uploadedFiles = [], assistantMessageId) {
    return streamRequest('/chat', {
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
    return streamRequest(`/stream/resume?session_id=${encodeURIComponent(sessionId)}&after_index=${afterIndex}`)
  },

  respondPermission(askId, approved, sessionId) {
    return streamRequest('/permission/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ask_id: askId, approved, session_id: sessionId })
    }).then(r => r.json())
  },

  uploadFile(sessionId, file) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('session_id', sessionId)
    return streamRequest('/upload', { method: 'POST', body: formData })
  },

  fetchScheduledTasks(sessionId) {
    const params = sessionId ? `session_id=${encodeURIComponent(sessionId)}` : 'include_all=1'
    return streamRequest(`/scheduled-tasks?${params}`).then(r => r.json())
  },

  deleteScheduledTask(taskId) {
    return streamRequest(`/scheduled-tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' })
  },

  createScheduledTask(sessionId, taskType, cron, params = {}) {
    return streamRequest('/scheduled-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, task_type: taskType, cron, params })
    }).then(r => r.json())
  }
}
