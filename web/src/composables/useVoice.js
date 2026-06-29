import { ref, computed } from 'vue'
import { voiceApi } from '../api/voice.js'

// 剥 Markdown：只留自然语言给 TTS
export function stripMarkdown(text = '') {
  return text
    .replace(/```[\s\S]*?```/g, ' ')            // 代码块
    .replace(/`[^`]*`/g, ' ')                     // 行内代码
    .replace(/^\s*!\[[^\]]*\]\([^)]*\).*$/gm, ' ') // 图片行
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')      // 链接 → 文字
    .replace(/^\s*\|.*\|\s*$/gm, ' ')             // 表格行
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')           // 标题
    .replace(/^\s*[-*+]\s+/gm, '')                // 无序列表
    .replace(/^\s*\d+\.\s+/gm, '')                // 有序列表
    .replace(/^\s*>\s?/gm, '')                    // 引用
    .replace(/[*_~]{1,3}/g, '')                   // 强调/删除线
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// 按句切分：中文标点 。！？ + 英文 .!? + 换行
export function splitSentences(text = '') {
  const parts = text.replace(/\r/g, '').replace(/\n+/g, '\n').split(/(?<=[。！？!?])|\n/)
  return parts.map(s => s.trim()).filter(s => s.length > 0)
}

export function useVoice(options = {}) {
  const onResult = options.onResult || (() => {})

  const status = ref('idle') // idle | recording | transcribing | speaking
  const muted = ref(false)
  const error = ref('')

  const supported = typeof window !== 'undefined'
    && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)

  const canRecord = computed(() => status.value === 'idle' && !muted.value)

  // ── 录音 ──
  let mediaRecorder = null
  let mediaStream = null
  let chunks = []

  async function start() {
    error.value = ''
    if (!supported) { error.value = '当前浏览器不支持录音'; return }
    if (status.value !== 'idle' || muted.value) return
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      error.value = '无法访问麦克风：' + (e.message || e)
      return
    }
    chunks = []
    mediaRecorder = new MediaRecorder(mediaStream)
    mediaRecorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data) }
    mediaRecorder.onstop = () => { _stopStream(); _transcribe() }
    mediaRecorder.start()
    status.value = 'recording'
  }

  function stop() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
    else { _stopStream(); status.value = 'idle' }
  }

  function _stopStream() {
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null }
  }

  async function _transcribe() {
    if (!chunks.length) { status.value = 'idle'; return }
    status.value = 'transcribing'
    const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' })
    chunks = []
    try {
      const text = await voiceApi.transcribe(blob)
      if (text) onResult(text)
    } catch (e) {
      error.value = e.message || '识别失败'
    } finally {
      status.value = 'idle'
    }
  }

  // ── 播报队列（串行，自然满足 RPS=3） ──
  const queue = []
  let currentAudio = null
  let playing = false

  function enqueueSentences(sentences) {
    if (muted.value) return
    const arr = (sentences || []).filter(Boolean)
    if (!arr.length) return
    const wasIdle = !playing && queue.length === 0
    queue.push(...arr)
    if (wasIdle) _playLoop()
  }

  async function _playLoop() {
    if (playing) return
    playing = true
    try {
      while (queue.length && !muted.value) {
        status.value = 'speaking'
        const sentence = queue.shift()
        try {
          const blob = await voiceApi.speak(sentence)
          if (muted.value) break
          await _playBlob(blob)
        } catch (e) {
          // 单句失败跳过，继续下一句
        }
      }
    } finally {
      currentAudio = null
      playing = false
      if (!muted.value) status.value = 'idle'
    }
  }

  function _playBlob(blob) {
    return new Promise(resolve => {
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      currentAudio = audio
      const done = () => { URL.revokeObjectURL(url); resolve() }
      audio.onended = done
      audio.onerror = done
      audio.play().catch(done)
    })
  }

  function stopSpeak() {
    queue.length = 0
    if (currentAudio) { try { currentAudio.pause() } catch {} }
    // 若正在播报循环里，循环会因 queue 为空自然结束
  }

  function setMuted(v) {
    muted.value = !!v
    if (muted.value) {
      stopSpeak()
      status.value = 'idle'
    }
  }

  return {
    status, muted, canRecord, error, supported,
    start, stop,
    enqueueSentences, stopSpeak, setMuted,
    stripMarkdown, splitSentences,
  }
}
