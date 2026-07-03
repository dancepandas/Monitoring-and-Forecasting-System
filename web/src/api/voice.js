const BASE = '/api'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const voiceApi = {
  async transcribe(blob) {
    const form = new FormData()
    form.append('file', blob, 'voice.webm')
    const res = await fetch(`${BASE}/voice/asr`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    })
    if (!res.ok) throw new Error((await res.text().catch(() => '')) || `ASR 失败 (${res.status})`)
    const data = await res.json()
    return data.text || ''
  },

  async speak(text) {
    const res = await fetch(`${BASE}/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) throw new Error(`TTS 失败 (${res.status})`)
    return res.blob() // audio/mpeg
  },
}
