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
  const onEmpty = options.onEmpty || (() => {})   // 转写为空 / 失败时回调（避免卡在聆听态）

  const status = ref('idle') // idle | recording | transcribing | speaking
  const muted = ref(false)
  const error = ref('')
  const hearing = ref(false)  // VAD 实时检测到有声音（可选 UI 反馈）

  // 诊断"为什么不支持录音"——精确到缺失的哪一项，便于定位（而非笼统提示）
  const _supportReason = (() => {
    if (typeof window === 'undefined' || typeof navigator === 'undefined') return '运行环境无 window/navigator'
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
      return window.isSecureContext ? '浏览器缺少 mediaDevices API' : '非安全上下文（请用 localhost/HTTPS 打开）'
    }
    if (typeof window.MediaRecorder !== 'function') return '浏览器不支持 MediaRecorder（请升级 Chrome/Edge/Firefox）'
    return ''
  })()
  const supported = !_supportReason

  const canRecord = computed(() => status.value === 'idle' && !muted.value)

  // ── 录音 + VAD（音量端点检测，自动判断"说完了"）──
  let mediaRecorder = null
  let mediaStream = null
  let chunks = []
  let audioCtx = null
  let analyser = null
  let vadTimer = null
  let speechStarted = false   // 是否已检测到真正的人声（过滤环境噪声）
  let lastLoudTs = 0          // 最近一次"有声音"时间
  let startTs = 0

  // 阈值（RMS，归一化 0~1）。不同麦克风灵敏度不同，可调。
  const SPEECH_RMS = 0.018    // 高于此视为说话
  const SILENCE_RMS = 0.010   // 低于此视为静音
  const SILENCE_MS = 1500     // 开始说话后，连续静音超过此时长 → 自动结束
  const MAX_MS = 15000        // 录音硬上限（防无限录）

  function _rms() {
    if (!analyser) return 0
    const buf = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128
      sum += v * v
    }
    return Math.sqrt(sum / buf.length)
  }

  function _startVAD() {
    _stopVAD()
    vadTimer = setInterval(() => {
      const now = Date.now()
      const rms = _rms()
      if (rms > SPEECH_RMS) {
        speechStarted = true
        lastLoudTs = now
        hearing.value = true
      } else if (rms < SILENCE_RMS) {
        hearing.value = false
      }
      // 已开始说话 → 静音超过阈值 → 自动结束（核心：自动判断说完话）
      if (speechStarted && (now - lastLoudTs > SILENCE_MS)) { stop(); return }
      // 硬上限兜底
      if (now - startTs > MAX_MS) { stop(); return }
    }, 150)
  }

  function _stopVAD() {
    hearing.value = false
    if (vadTimer) { clearInterval(vadTimer); vadTimer = null }
  }

  // 清理一切残留：录音、VAD、流、播报队列 —— 确保每次 start 都从干净状态开始
  //（修复：打断播报后 _playLoop 会卡在 await、status 停在 speaking，导致后续 start() 被守卫静默拒收）
  function _reset() {
    _stopVAD()
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try { mediaRecorder.onstop = null; mediaRecorder.stop() } catch {}
    }
    mediaRecorder = null
    chunks = []
    _stopStream()
    stopSpeak()
    status.value = 'idle'
  }

  async function start() {
    error.value = ''
    if (!supported) {
      console.warn('[useVoice] 录音不可用：', _supportReason, {
        isSecureContext: window.isSecureContext,
        href: location.href,
        UA: navigator.userAgent,
      })
      error.value = '录音不可用：' + _supportReason
      return
    }
    if (muted.value) return
    _reset()
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      const name = e && e.name
      let hint = '（请用 localhost/HTTPS 打开，并允许麦克风权限）'
      if (name === 'NotAllowedError' || name === 'SecurityError') hint = '（权限被拒：点地址栏左侧的锁/麦克风图标→允许；并检查系统麦克风访问开关）'
      else if (name === 'NotFoundError' || name === 'OverconstrainedError') hint = '（未找到麦克风设备：请插入麦克风，或换到带麦克风的电脑/手机上测试）'
      else if (name === 'NotReadableError') hint = '（麦克风被其他程序占用或硬件故障）'
      error.value = '无法访问麦克风：' + (e.message || name || e) + hint
      status.value = 'idle'
      return
    }
    chunks = []
    speechStarted = false
    lastLoudTs = Date.now()
    startTs = Date.now()

    // VAD：分析音量曲线
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      if (audioCtx.state === 'suspended') audioCtx.resume()
      const src = audioCtx.createMediaStreamSource(mediaStream)
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 512
      src.connect(analyser)
    } catch (e) {
      analyser = null   // 分析失败不影响录音，只是失去自动端点
    }

    mediaRecorder = new MediaRecorder(mediaStream)
    mediaRecorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data) }
    mediaRecorder.onstop = () => { _stopVAD(); _stopStream(); _transcribe() }
    mediaRecorder.start()
    status.value = 'recording'
    _startVAD()
  }

  function stop() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
    else { _stopVAD(); _stopStream(); status.value = 'idle' }
  }

  function _stopStream() {
    _stopVAD()
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null }
    if (audioCtx) { try { audioCtx.close() } catch {} audioCtx = null; analyser = null }
  }

  async function _transcribe() {
    if (!chunks.length) { status.value = 'idle'; onEmpty(); return }
    status.value = 'transcribing'
    const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' })
    chunks = []
    let text = ''
    try {
      text = (await voiceApi.transcribe(blob)) || ''
    } catch (e) {
      error.value = e.message || '识别失败'
    } finally {
      status.value = 'idle'
      if (text && text.trim()) onResult(text)
      else onEmpty()
    }
  }

  // ── 播报队列（串行，自然满足 RPS=3） ──
  const queue = []
  let currentAudio = null
  let currentResolve = null
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
      const done = () => { currentResolve = null; URL.revokeObjectURL(url); resolve() }
      currentResolve = done
      audio.onended = done
      audio.onerror = done
      audio.play().catch(done)
    })
  }

  function stopSpeak() {
    queue.length = 0
    if (currentAudio) { try { currentAudio.pause() } catch {} }
    // 主动解除 _playLoop 里 await _playBlob 的阻塞，避免打断后 status 卡在 speaking
    if (currentResolve) { const r = currentResolve; currentResolve = null; r() }
  }

  function setMuted(v) {
    muted.value = !!v
    if (muted.value) {
      stopSpeak()
      status.value = 'idle'
    }
  }

  return {
    status, muted, canRecord, error, supported, hearing,
    start, stop,
    enqueueSentences, stopSpeak, setMuted,
    stripMarkdown, splitSentences,
  }
}
