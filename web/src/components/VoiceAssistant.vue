<template>
  <Teleport to="body">
    <div class="va-root" :class="mode">
      <!-- 字幕气泡 -->
      <transition name="va-pop">
        <div v-if="showBubble" class="va-bubble" @click="onBubbleClick">
          <span v-if="mode === 'listening'" class="va-status-line">
            <i class="va-dot"></i>{{ voice.status.value === 'transcribing' ? '识别中…' : '正在听…（再点结束）' }}
          </span>
          <span v-else-if="mode === 'thinking'" class="va-status-line">
            <i class="va-dot"></i>思考中…
          </span>
          <span v-else-if="mode === 'error'" class="va-err">{{ errMsg }}</span>
          <span v-else class="va-answer">{{ bubbleText }}</span>
        </div>
      </transition>

      <!-- 机器人主体 -->
      <button class="va-robot" :class="mode" @click="onRobotClick" :title="robotTitle" :aria-label="robotTitle">
        <svg viewBox="0 0 100 100" class="robot-svg" aria-hidden="true">
          <!-- 天线 -->
          <line class="r-ant" x1="50" y1="14" x2="50" y2="26" />
          <circle class="r-light" cx="50" cy="11" r="4.5" />
          <!-- 耳朵 -->
          <rect class="r-ear" x="15" y="40" width="7" height="16" rx="3" />
          <rect class="r-ear" x="78" y="40" width="7" height="16" rx="3" />
          <!-- 头 -->
          <rect class="r-head" x="22" y="24" width="56" height="44" rx="16" />
          <!-- 脸屏 -->
          <rect class="r-face" x="28" y="30" width="44" height="32" rx="11" />
          <!-- 眼睛 -->
          <g class="r-eyes">
            <circle class="r-eye" cx="40" cy="45" r="4.5" />
            <circle class="r-eye" cx="60" cy="45" r="4.5" />
          </g>
          <!-- 嘴 -->
          <g class="r-mouth-g">
            <rect class="r-mouth" x="43" y="55" width="14" height="3" rx="1.5" />
          </g>
          <!-- 身体 -->
          <rect class="r-body" x="32" y="68" width="36" height="20" rx="8" />
          <circle class="r-chest" cx="50" cy="78" r="3" />
        </svg>
      </button>

      <!-- 静音 -->
      <button class="va-mute" :class="{ on: muted }" @click="toggleMute" :title="muted ? '已静音，点开语音' : '点静音'">
        {{ muted ? '🔇' : '🔊' }}
      </button>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useVoice } from '../composables/useVoice.js'
import { agentApi } from '../api/agent.js'
import { voiceApi } from '../api/voice.js'

const SID = 'global-voice-assistant'

// mode: idle | listening | thinking | speaking | error
const mode = ref('idle')
const answer = ref('')
const errMsg = ref('')
const muted = ref(false)

const voice = useVoice({ onResult: handleQuestion })

const robotTitle = computed(() => {
  if (errMsg.value) return errMsg.value
  if (mode.value === 'greeting') return '打招呼中…（点机器人跳过，直接说）'
  if (mode.value === 'listening') return '正在听，点击结束'
  if (mode.value === 'thinking') return '思考中…（点机器人打断）'
  if (mode.value === 'speaking') return '回答中…（点机器人停止）'
  return '点我，语音提问'
})

const bubbleText = computed(() => answer.value)
const showBubble = computed(() =>
  ['greeting', 'listening', 'thinking', 'speaking', 'error'].includes(mode.value)
)

// useVoice.status → mode 映射（listening/transcribing/speaking）
watch(() => voice.status.value, (s) => {
  if (s === 'recording' || s === 'transcribing') {
    if (mode.value === 'idle') mode.value = 'listening'
  } else if (s === 'speaking') {
    mode.value = 'speaking'
  } else if (s === 'idle') {
    // 仅在播报结束后回待机；thinking 由 handleQuestion/askAgent 显式管理
    if (mode.value === 'speaking') mode.value = 'idle'
  }
})

function onRobotClick() {
  errMsg.value = ''
  if (mode.value === 'listening') { voice.stop(); return }            // 结束录音
  if (mode.value === 'greeting') { cancelGreeting(); startListening(); return } // 跳过招呼，直接听
  if (mode.value === 'thinking' || mode.value === 'speaking') {
    voice.stopSpeak(); mode.value = 'idle'; return                    // 打断
  }
  if (mode.value === 'idle') { greetAndListen() }                     // 打招呼再听
}
function onBubbleClick() { onRobotClick() }
function toggleMute() {
  muted.value = !muted.value
  voice.setMuted(muted.value)
}

// ── 打招呼 ──
const GREETINGS = [
  '你好，我是水文智能助手，请问有什么可以帮你？',
  '在的，说吧，我听着。',
  '你好，请问需要查询什么？',
  '嗨，想了解水位、流量还是预警？',
]
let greetAudio = null
const delay = (ms) => new Promise(r => setTimeout(r, ms))
function pickGreeting() { return GREETINGS[Math.floor(Math.random() * GREETINGS.length)] }
function cancelGreeting() { if (greetAudio) { try { greetAudio.pause() } catch {} greetAudio = null } }
function playOnce(blob) {
  return new Promise(res => {
    const url = URL.createObjectURL(blob)
    const a = new Audio(url); greetAudio = a
    const done = () => { URL.revokeObjectURL(url); res() }
    a.onended = done; a.onerror = done
    a.play().catch(done)
  })
}
function startListening() { answer.value = ''; voice.start() }
async function greetAndListen() {
  mode.value = 'greeting'
  answer.value = pickGreeting()
  if (!muted.value) {
    try {
      const blob = await voiceApi.speak(answer.value)
      if (mode.value !== 'greeting') return            // 已被打断
      await playOnce(blob)
    } catch { /* 合成失败则跳过，继续进入聆听 */ }
  } else {
    await delay(700)                                    // 静音：只做视觉招呼
  }
  if (mode.value === 'greeting') startListening()
}

async function handleQuestion(text) {
  answer.value = ''
  errMsg.value = ''
  mode.value = 'thinking'
  try {
    await askAgent(text)
  } catch (e) {
    errMsg.value = '出错了：' + (e.message || e)
    mode.value = 'error'
    setTimeout(() => { if (mode.value === 'error') mode.value = 'idle' }, 3500)
  }
}

let asking = false
async function askAgent(text) {
  asking = true
  let spoke = false
  const enqueue = (sents) => {
    if (sents.length && !voice.muted.value) { voice.enqueueSentences(sents); spoke = true }
  }
  try {
    const res = await agentApi.createChatRequest(SID, withTime(text), [], uid())
    if (!res.ok) throw new Error('请求失败 ' + res.status)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let answerBuf = ''
    let spokenLen = 0
    const flush = () => {
      if (answerBuf.length <= spokenLen) return
      const fresh = answerBuf.slice(spokenLen)
      const m = fresh.match(/.*[。！？!?]/s)
      if (!m) return
      const complete = m[0]
      spokenLen += complete.length
      enqueue(voice.splitSentences(voice.stripMarkdown(complete)))
    }
    while (asking) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop() || ''
      for (const raw of lines) {
        let s = raw.trim()
        if (s.startsWith('data: ')) s = s.slice(6).trim()
        if (!s || s === '[DONE]') continue
        let ev
        try { ev = JSON.parse(s) } catch { continue }
        const t = ev.type || ''
        if (t === 'answer_delta' || t === 'token') {
          answerBuf += ev.content || ev.delta || ''
          answer.value = answerBuf
          flush()
        } else if (t === 'final' || t === 'final_text') {
          if (ev.content) { answerBuf = ev.content; answer.value = answerBuf }
        }
        // thought_delta / action_* → 保持 thinking
      }
    }
    // 尾部兜底
    if (answerBuf.length > spokenLen) {
      enqueue(voice.splitSentences(voice.stripMarkdown(answerBuf.slice(spokenLen))))
    }
  } finally {
    asking = false
    // 静音或无内容可念 → 回待机；否则等播报结束 watch 把 speaking→idle
    if (!spoke) mode.value = 'idle'
  }
}

function uid() { try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 10) } }
function withTime(text) {
  const n = new Date()
  const p = x => String(x).padStart(2, '0')
  return `[当前系统时间: ${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())} ${p(n.getHours())}:${p(n.getMinutes())}]\n\n${text}`
}

onMounted(() => { agentApi.initSession(SID).catch(() => {}) })
</script>

<style scoped>
.va-root {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 9000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  --accent: #38bdf8;
}
.va-root.listening { --accent: #f87171; }
.va-root.thinking  { --accent: #fbbf24; }
.va-root.speaking  { --accent: #38bdf8; }
.va-root.greeting  { --accent: #34d399; }
.va-root.error     { --accent: #f87171; }

/* 气泡 */
.va-bubble {
  max-width: 300px;
  min-height: 34px;
  padding: 8px 12px;
  border-radius: 14px 14px 4px 14px;
  background: linear-gradient(180deg, rgba(16, 44, 74, .92), rgba(8, 28, 50, .88));
  border: 1px solid var(--line);
  color: #fff;
  font-size: 12.5px;
  line-height: 1.5;
  box-shadow: 0 8px 28px rgba(8, 96, 150, .28);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  cursor: pointer;
  overflow-wrap: break-word;
  max-height: 200px;
  overflow-y: auto;
}
.va-status-line { display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }
.va-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: vaPulse 1.1s ease-in-out infinite; flex-shrink: 0; }
.va-answer { white-space: pre-wrap; }
.va-err { color: #fecaca; }
.va-pop-enter-active, .va-pop-leave-active { transition: all .18s ease; }
.va-pop-enter-from, .va-pop-leave-to { opacity: 0; transform: translateY(6px) scale(.96); }
@keyframes vaPulse { 0%,100% { opacity: 1; box-shadow: 0 0 0 0 var(--accent); } 50% { opacity: .4; box-shadow: 0 0 0 6px transparent; } }

/* 机器人按钮 */
.va-robot {
  width: 72px; height: 72px;
  border: 0; background: transparent;
  cursor: pointer; padding: 0;
  filter: drop-shadow(0 8px 16px rgba(8, 96, 150, .28));
  transition: transform .15s ease;
}
.va-robot:hover { transform: translateY(-2px) scale(1.04); }
.va-robot:active { transform: scale(.96); }
.greeting .va-robot { animation: vaWave .55s ease-in-out infinite; }
.greeting .r-eye, .greeting .r-mouth { fill: #34d399; }
@keyframes vaWave { 0%,100% { transform: rotate(-7deg); } 50% { transform: rotate(7deg); } }
.robot-svg { width: 100%; height: 100%; display: block; overflow: visible; }

.r-ant { stroke: #94a3b8; stroke-width: 2.5; }
.r-light { fill: var(--accent); transition: fill .2s; }
.listening .r-light, .thinking .r-light, .speaking .r-light { animation: vaPulse 1.1s ease-in-out infinite; }

.r-ear { fill: #94a3b8; }
.r-head { fill: #e2e8f0; stroke: #cbd5e1; stroke-width: 1.5; }
.r-face { fill: #0f172a; }
.r-body { fill: #cbd5e1; stroke: #94a3b8; stroke-width: 1; }
.r-chest { fill: var(--accent); transition: fill .2s; }

.r-eyes { transform-box: fill-box; transform-origin: center; }
.r-eye { fill: #38bdf8; }
.idle .r-eyes { animation: vaBlink 4.2s infinite; }
.listening .r-eye { fill: #f87171; }
.thinking .r-eye { fill: #fbbf24; }
@keyframes vaBlink { 0%, 92%, 100% { transform: scaleY(1); } 96% { transform: scaleY(.1); } }

.r-mouth-g { transform-box: fill-box; transform-origin: center; }
.r-mouth { fill: #38bdf8; transition: fill .2s; }
.listening .r-mouth { fill: #f87171; }
.thinking .r-mouth { fill: #fbbf24; }
.speaking .r-mouth { fill: #38bdf8; animation: vaTalk .16s infinite alternate; }
@keyframes vaTalk { from { transform: scaleY(.6); } to { transform: scaleY(2.4); } }

/* 静音 */
.va-mute {
  width: 30px; height: 30px; border: 0; border-radius: 50%;
  background: rgba(8, 96, 150, .55); color: #fff; font-size: 14px;
  cursor: pointer; box-shadow: 0 4px 12px rgba(8, 96, 150, .25);
  display: flex; align-items: center; justify-content: center;
  transition: transform .15s;
}
.va-mute:hover { transform: scale(1.1); }
.va-mute.on { opacity: .6; }
</style>
