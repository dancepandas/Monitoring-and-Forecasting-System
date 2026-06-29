# 语音助手（数字人 Phase 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在智能体对话界面点按麦克风说话（Paraformer 识别），回答用 CosyVoice 语音播报，全部走阿里云官方 SDK。

**Architecture:** 后端新增无状态 REST 端点 `/api/voice/asr`、`/api/voice/tts`，阻塞调用 dashscope SDK（丢 FastAPI 线程池），复用现有 `dashscope_api_key`。前端新增 `useVoice` 组合式函数（录音/转写/播报状态机 + 防回环半双工 + Markdown 清洗 + 串行播报队列）+ `VoiceButton`，接入现有 `AgentChatPanel.doSend()`，底座零改动。

**Tech Stack:** FastAPI + dashscope Python SDK（`dashscope.audio.asr.Recognition` / `dashscope.audio.tts_v2.SpeechSynthesizer`）；ffmpeg（conda 自带，PATH 可用）；Vue 3 `<script setup>` + Composition API。

## Global Constraints

- **密钥**：复用 `settings.dashscope_api_key`（百炼 key，agent 在用），**不新增密钥**。TTS WebSocket 端点用业务空间专属域名 `wss://llm-3kqn1siocgzbz9sp.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference`。
- **TTS 模型/音色**：`cosyvoice-v2` + v2 兼容音色 `longxiaochun`（**禁用文档示例 `longanyang`——那是 v3 音色，v2 报错**）。
- **ASR 模型**：`paraformer-realtime-v2`，`format='wav'`、`sample_rate=16000`、`language_hints=['zh','en']`。
- **ffmpeg**：本机与服务器 conda 自带（`D:\chengs\7.miniconda\Library\bin\ffmpeg.exe`，4.3.1，PATH 可用），`ffmpeg_path` 默认 `"ffmpeg"`，无需额外安装。
- **并发**：TTS RPS=3 → 前端播报串行队列；单用户点按 ASR 并发极低 → 后端线程池足够。
- **防回环（半双工）**：播报期间禁用麦克风，避免把自己念的话又识别进去。
- **只念人话**：TTS 前剥 Markdown（`#`/表格/代码块/强调/链接/列表）。
- **非流式两端**：ASR 用 `Recognition.call(file)`，TTS 用 `SpeechSynthesizer.call(text)`；不碰双向流式（留 Phase 1.5）。
- **不主动 commit**：本任务实现期间**不提交**，改动累积，等用户确认后再统一 commit（用户常驻约束）。
- **测试约定**：项目无单测框架（runtime `requirements.txt` 无 pytest）。唯一纯函数（ffmpeg 转码）用 pytest 单测（临时 `pip install pytest`，测试放 `gateway/tests/`）；SDK 端点与 Vue 组件用集成/手测（curl + 浏览器），符合现有约定。

---

## File Structure

**后端**
- `gateway/config.py`（修改）— 新增 5 个语音配置项。
- `gateway/requirements.txt`（修改）— 加 `dashscope`。
- `gateway/routes/voice.py`（**新建**）— `_to_wav_16k_mono()` 纯函数 + `/api/voice/asr` + `/api/voice/tts` 两个端点 + SDK 初始化。
- `gateway/server.py`（修改）— 注册 `voice.router`。
- `gateway/tests/test_voice_ffmpeg.py`（**新建**）— ffmpeg 转码单测。

**前端**
- `web/src/api/voice.js`（**新建**）— `voiceApi.transcribe(blob)` / `voiceApi.speak(text)`。
- `web/src/composables/useVoice.js`（**新建**）— 录音/转写/播报状态机 + `stripMarkdown` / `splitSentences` / `enqueueSentences`。
- `web/src/components/VoiceButton.vue`（**新建**）— 麦克风按钮 + 静音开关 + 状态样式。
- `web/src/components/AgentChatPanel.vue`（修改）— 挂 `VoiceButton`、`onVoiceText` 注入 `doSend`、answer 流式触发播报、暂停/新轮停止播报。

---

## Task 1: 后端 — 配置与依赖

**Files:**
- Modify: `gateway/config.py`（Agent LLM 块后，约第 22 行后插入）
- Modify: `gateway/requirements.txt`（末尾追加）

**Interfaces:**
- Produces: `settings.dashscope_workspace_id`、`settings.tts_model`、`settings.tts_voice`、`settings.asr_model`、`settings.ffmpeg_path`（供 Task 2 使用）。

- [ ] **Step 1: 在 `gateway/config.py` 的 `agent_max_tokens` 行后新增语音配置**

在 `agent_max_tokens: int = 4096`（第 22 行）之后、`# Agent paths` 注释（第 24 行）之前插入：

```python

    # 百炼语音（CosyVoice TTS + Paraformer ASR），复用 dashscope_api_key，不新增密钥
    dashscope_workspace_id: str = "llm-3kqn1siocgzbz9sp"   # TTS WebSocket 业务空间专属域名
    tts_model: str = "cosyvoice-v2"
    tts_voice: str = "longxiaochun"                          # v2 兼容音色（勿用 v3 的 longanyang）
    asr_model: str = "paraformer-realtime-v2"
    ffmpeg_path: str = "ffmpeg"                              # conda 自带，PATH 可用
```

- [ ] **Step 2: 在 `gateway/requirements.txt` 末尾追加 dashscope**

```text
dashscope>=1.20.0
```

- [ ] **Step 3: 安装依赖并验证可导入**

Run: `pip install dashscope`
Expected: 安装成功（含 `dashscope.audio.asr`、`dashscope.audio.tts_v2`）。

Run: `python -c "from dashscope.audio.asr import Recognition; from dashscope.audio.tts_v2 import SpeechSynthesizer; print('ok')"`
Expected: 输出 `ok`。

Run: `python -c "from gateway.config import settings; print(settings.tts_model, settings.tts_voice, settings.asr_model, settings.ffmpeg_path, settings.dashscope_workspace_id)"`
Expected: 输出 `cosyvoice-v2 longxiaochun paraformer-realtime-v2 ffmpeg llm-3kqn1siocgzbz9sp`

- [ ] **Step 4:（本任务无代码提交——见 Global Constraints「不主动 commit」，改动随后续任务累积）**

记录：配置与依赖就绪。

---

## Task 2: 后端 — voice.py 路由（ffmpeg 转码 + ASR/TTS 端点）

**Files:**
- Create: `gateway/routes/voice.py`
- Modify: `gateway/server.py:17`（import）与 `gateway/server.py:97-104`（include_router 块）

**Interfaces:**
- Consumes: Task 1 的 `settings.*`、`get_current_user`（`gateway.auth.middleware`）。
- Produces: `POST /api/voice/asr`（FormData `file` → `{"text": str}`，401 未授权 / 502 转码或识别失败）、`POST /api/voice/tts`（JSON `{"text": str}` → `audio/mpeg` bytes，400 空文本 / 502 合成失败）；纯函数 `_to_wav_16k_mono(src: str) -> str`。

- [ ] **Step 1: 写 ffmpeg 转码函数的失败测试**

Create `gateway/tests/test_voice_ffmpeg.py`：

```python
import os
import struct
import subprocess
import tempfile

from gateway.routes.voice import _to_wav_16k_mono

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")


def _make_silent_webm(path: str, seconds: float = 1.0) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"anullsrc=r=48000:cl=mono", "-t", str(seconds), path],
        check=True,
    )


def test_to_wav_produces_16k_mono_pcm():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.webm")
        _make_silent_webm(src)
        wav = _to_wav_16k_mono(src)
        assert os.path.exists(wav)
        assert os.path.getsize(wav) > 44
        with open(wav, "rb") as f:
            assert f.read(4) == b"RIFF"
            assert f.read(4) == b"\x00\x00\x00\x00"
            assert f.read(4) == b"WAVE"
            f.seek(22)
            channels = struct.unpack("<H", f.read(2))[0]
            sample_rate = struct.unpack("<I", f.read(4))[0]
            assert channels == 1, channels
            assert sample_rate == 16000, sample_rate
```

- [ ] **Step 2: 运行测试，确认失败（模块不存在）**

Run: `python -m pytest gateway/tests/test_voice_ffmpeg.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'gateway.routes.voice'`）。

- [ ] **Step 3: 实现 `gateway/routes/voice.py`**

```python
import logging
import os
import subprocess
import tempfile
from http import HTTPStatus

import dashscope
from dashscope.audio.asr import Recognition
from dashscope.audio.tts_v2 import SpeechSynthesizer
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..auth.middleware import get_current_user
from ..config import settings

logger = logging.getLogger(__name__)

# 模块加载时初始化 SDK（复用 agent 的百炼 key，不新增密钥）
if settings.dashscope_api_key:
    dashscope.api_key = settings.dashscope_api_key
# TTS（WebSocket）走业务空间专属域名，性能/稳定性更好；ASR 用默认端点亦可
dashscope.base_websocket_api_url = (
    f"wss://{settings.dashscope_workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
)

router = APIRouter(prefix="/api", tags=["voice"])


def _to_wav_16k_mono(src: str) -> str:
    """ffmpeg 把浏览器上传的 webm/opus 转成 Paraformer 能吃的 wav(16k/mono/pcm_s16le)。

    返回输出 wav 的绝对路径。失败抛 RuntimeError 并带 stderr。
    """
    out = src + ".wav"
    proc = subprocess.run(
        [settings.ffmpeg_path, "-y", "-loglevel", "error", "-i", src,
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg 转码失败: " + proc.stderr.decode("utf-8", "ignore").strip()
        )
    return out


@router.post("/voice/asr")
def api_voice_asr(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    suffix = os.path.splitext(file.filename or ".webm")[1] or ".webm"
    src = wav = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            tf.write(file.file.read())
            src = tf.name
        try:
            wav = _to_wav_16k_mono(src)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        recognition = Recognition(
            model=settings.asr_model,
            format="wav",
            sample_rate=16000,
            language_hints=["zh", "en"],
            callback=None,
        )
        result = recognition.call(wav)  # 阻塞，返回 RecognitionResult
        if result.status_code != HTTPStatus.OK:
            raise HTTPException(status_code=502, detail=f"ASR 失败: {result.message}")
        text = (result.get_sentence() or {}).get("text", "")
        return {"text": text.strip()}
    finally:
        for p in (src, wav):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


@router.post("/voice/tts")
def api_voice_tts(body: dict, user: dict = Depends(get_current_user)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    synth = SpeechSynthesizer(model=settings.tts_model, voice=settings.tts_voice)
    audio = synth.call(text)  # 阻塞返回 mp3 bytes（每次新建实例，SDK 要求）
    if not audio:
        raise HTTPException(status_code=502, detail="TTS 返回空音频")
    return Response(audio, media_type="audio/mpeg")
```

- [ ] **Step 4: 注册路由**

Modify `gateway/server.py`：

第 17 行（现有 routes import）：

```python
from .routes import auth, data, forecast, agent, reports, system, notify, alerts, voice
```

在 `app.include_router(alerts.router)`（约第 104 行）之后追加：

```python
app.include_router(voice.router)
```

- [ ] **Step 5: 运行转码单测，确认通过**

Run: `python -m pytest gateway/tests/test_voice_ffmpeg.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 6: 验证服务能启动（导入无错、路由已挂载）**

Run: `python -c "from gateway.server import app; print(sorted(r.path for r in app.routes if r.path.startswith('/api/voice')))"`（在仓库根目录执行）
Expected: 输出包含 `['/api/voice/asr', '/api/voice/tts']`。

记录：后端语音端点就绪。

---

## Task 3: 后端 — 端到端验证（curl）

**Files:** 无（仅验证）。

- [ ] **Step 1: 启动 gateway**

Run（仓库根目录）: `python -m gateway.server`（或现有启动脚本，端口 15002）
Expected: 日志 `Gateway ready on port 15002`，无导入错误。

- [ ] **Step 2: 取一个 JWT token**

Run: `curl -s -X POST http://localhost:15002/api/login -H "Content-Type: application/json" -d '{"username":"<你的用户名>","password":"<你的密码>"}'`
Expected: 返回 `{"token":"...", "user":{...}}`。把 token 存到环境变量：

```bash
export TOKEN="<上一步的 token>"
```

- [ ] **Step 3: 验证 TTS 端点产出可播放 mp3**

Run:
```bash
curl -s -X POST http://localhost:15002/api/voice/tts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"当前仙桃站水位正常，无预警。"}' \
  -o /tmp/voice_tts.mp3 -w "HTTP %{http_code}, %{size_download} bytes\n"
```
Expected: `HTTP 200, <非零> bytes`；用系统播放器打开 `/tmp/voice_tts.mp3` 能听到中文播报。

> 若返回 502 + "TTS 返回空音频" 或鉴权错：检查 `dashscope_api_key` 是否有值（`.env`/`aiflow_profile.env`）、音色是否 v2 兼容。

- [ ] **Step 4: 验证 ASR 端点跑通（先用 TTS 产出的音频回灌）**

把 Step 3 的 mp3 转成 wav 喂给 ASR（绕开浏览器录音，先验管线）：

```bash
ffmpeg -y -loglevel error -i /tmp/voice_tts.mp3 -ar 16000 -ac 1 -c:a pcm_s16le /tmp/voice_asr_in.wav
curl -s -X POST http://localhost:15002/api/voice/asr \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/voice_asr_in.wav"
```
Expected: `{"text":"当前仙桃站水位正常，无预警。"}`（识别文字与原文近似，标点可不同）。HTTP 200。

记录：后端 ASR/TTS 端点端到端通过。停止 gateway。

---

## Task 4: 前端 — api/voice.js

**Files:**
- Create: `web/src/api/voice.js`

**Interfaces:**
- Produces: `voiceApi.transcribe(blob: Blob) -> Promise<string>`、`voiceApi.speak(text: string) -> Promise<Blob>`（供 Task 5 使用）。

- [ ] **Step 1: 新建 `web/src/api/voice.js`**

```js
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
```

- [ ] **Step 2: 验证构建通过**

Run（`web/` 目录）: `npm run build`
Expected: 构建成功，无 "could not resolve" 报错。

记录：voice API 就绪。

---

## Task 5: 前端 — composables/useVoice.js（状态机 + 录音/转写/播报）

**Files:**
- Create: `web/src/composables/useVoice.js`

**Interfaces:**
- Consumes: Task 4 的 `voiceApi`。
- Produces: `useVoice({ onResult })` 返回 `{ status, muted, canRecord, error, start, stop, setMuted, enqueueSentences, stopSpeak, stripMarkdown, splitSentences }`（供 Task 6/7 使用）。
  - `status: Ref<'idle'|'recording'|'transcribing'|'speaking'>`
  - `canRecord: Ref<bool>`（= status==='idle' && !muted，半双工防回环）
  - `start()` / `stop()`：点按录音控制
  - `enqueueSentences(string[])` / `stopSpeak()`：播报队列
  - `setMuted(bool)`、`stripMarkdown(str)→str`、`splitSentences(str)→string[]`

- [ ] **Step 1: 新建 `web/src/composables/useVoice.js`**

```js
import { ref, computed } from 'vue'
import { voiceApi } from '../api/voice.js'

// 剥 Markdown：只留自然语言给 TTS
export function stripMarkdown(text = '') {
  return text
    .replace(/```[\s\S]*?```/g, ' ')        // 代码块
    .replace(/`[^`]*`/g, ' ')                 // 行内代码
    .replace(/^\s*!\[[^\]]*\]\([^)]*\).*$/gm, ' ') // 图片行
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // 链接 → 文字
    .replace(/^\s*\|.*\|\s*$/gm, ' ')         // 表格行
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')       // 标题
    .replace(/^\s*[-*+]\s+/gm, '')            // 无序列表
    .replace(/^\s*\d+\.\s+/gm, '')            // 有序列表
    .replace(/^\s*>\s?/gm, '')                // 引用
    .replace(/[*_~]{1,3}/g, '')               // 强调/删除线
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
```

- [ ] **Step 2: 验证构建通过**

Run（`web/` 目录）: `npm run build`
Expected: 构建成功。

记录：useVoice 组合式函数就绪。

---

## Task 6: 前端 — VoiceButton.vue

**Files:**
- Create: `web/src/components/VoiceButton.vue`

**Interfaces:**
- Consumes: 父组件传入 `status`、`muted`、`canRecord`、`error`（来自 Task 5 的 useVoice 返回值）。
- Produces: emit `toggle-mic`（点麦克风）、`toggle-mute`（点静音）。

- [ ] **Step 1: 新建 `web/src/components/VoiceButton.vue`**

```vue
<template>
  <div class="voice-btns">
    <button
      class="vb mic"
      :class="[status]"
      :disabled="!canRecord && status === 'idle'"
      :title="micTitle"
      @click="$emit('toggle-mic')"
    >
      <span v-if="status === 'transcribing'" class="vb-spin">⟳</span>
      <span v-else-if="status === 'speaking'" class="vb-wave"><i></i><i></i><i></i></span>
      <span v-else class="vb-mic-ico">🎤</span>
    </button>
    <button
      class="vb mute"
      :class="{ on: muted }"
      :title="muted ? '已静音（点击开启语音播报）' : '点击静音语音播报'"
      @click="$emit('toggle-mute')"
    >
      {{ muted ? '🔇' : '🔊' }}
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  status: { type: String, default: 'idle' },
  muted: { type: Boolean, default: false },
  canRecord: { type: Boolean, default: true },
  error: { type: String, default: '' },
})
defineEmits(['toggle-mic', 'toggle-mute'])

const micTitle = computed(() => {
  if (props.error) return props.error
  if (props.status === 'recording') return '正在录音，点击结束'
  if (props.status === 'transcribing') return '识别中…'
  if (props.status === 'speaking') return '播报中（麦克风已禁用）'
  return '点按说话'
})
</script>

<style scoped>
.voice-btns { display: flex; align-items: flex-end; gap: 6px; flex-shrink: 0; }
.vb { min-height: 38px; width: 38px; border: 1px solid rgba(15,23,42,.12); border-radius: 18px; background: rgba(255,255,255,.72); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 16px; transition: all .15s; }
.vb:hover { border-color: var(--primary); }
.vb:disabled { opacity: .45; cursor: not-allowed; }
.vb.mic.recording { border-color: var(--danger); background: rgba(220,38,38,.12); animation: vbPulse 1.2s ease-in-out infinite; }
.vb.mic.speaking { border-color: var(--water); background: rgba(14,165,233,.1); }
.vb.mute.on { border-color: var(--muted); opacity: .7; }
.vb-spin { display: inline-block; animation: vbRot 1s linear infinite; }
@keyframes vbRot { to { transform: rotate(360deg); } }
@keyframes vbPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(220,38,38,.25); } 50% { box-shadow: 0 0 0 6px transparent; } }
.vb-wave { display: inline-flex; align-items: flex-end; gap: 2px; height: 16px; }
.vb-wave i { width: 3px; background: var(--water); border-radius: 2px; animation: vbBar .9s ease-in-out infinite; }
.vb-wave i:nth-child(1) { height: 8px; animation-delay: 0s; }
.vb-wave i:nth-child(2) { height: 16px; animation-delay: .2s; }
.vb-wave i:nth-child(3) { height: 10px; animation-delay: .4s; }
@keyframes vbBar { 0%,100% { transform: scaleY(.4); } 50% { transform: scaleY(1); } }
</style>
```

- [ ] **Step 2: 验证构建通过**

Run（`web/` 目录）: `npm run build`
Expected: 构建成功。

记录：VoiceButton 就绪。

---

## Task 7: 前端 — AgentChatPanel.vue 集成

**Files:**
- Modify: `web/src/components/AgentChatPanel.vue`
  - import（第 77-79 行附近）：加 `watch` 已存在；加 `useVoice`、`VoiceButton`。
  - 模板 `.input-row`（第 67-72 行）：插入 `<VoiceButton>`。
  - `doSend`（第 126 行）：新轮开始时停止旧播报 + 重置已念偏移。
  - 新增：`voice` 实例、`onVoiceText`、answer 播报 `watch`、`onUnmounted` 清理。

**Interfaces:**
- Consumes: Task 5 的 `useVoice`、Task 6 的 `VoiceButton`、现有 `doSend`/`msgs`/`input`/`streaming`。

- [ ] **Step 1: 在 import 区追加（第 79 行 `import { marked } from 'marked'` 后）**

```js
import VoiceButton from './VoiceButton.vue'
import { useVoice } from '../composables/useVoice.js'
```

> `watch` 已在第 77 行从 vue 导入，无需再加。

- [ ] **Step 2: 在 `<script setup>` 内（`const props = defineProps(...)` 之后，`const msgs = reactive([])` 之前）加 voice 实例与 onVoiceText**

```js
const lastSpokenLen = ref(0)

function onVoiceText(text) {
  // 识别文字直接进输入框并发送（用户要"直接语音提问"）
  input.value = text
  doSend()
}

const voice = useVoice({ onResult: onVoiceText })
// 模板要用到的响应式状态，解构成顶层绑定，模板里才能自动解包（嵌套在 voice 对象里的 ref 不会自动解包）
const { status: voiceStatus, muted: voiceMuted, canRecord: voiceCanRecord, error: voiceError } = voice
```

- [ ] **Step 3: 在 `doSend` 里新轮开始时停播 + 重置偏移**

定位 `doSend` 内 `streaming.value = true; reconnecting.value = false; retryCount.value = 0; permissionAsk.value = null; stepCounter = 0`（约第 132 行）那一行之后追加：

```js
  voice.stopSpeak()        // 新一轮提问，停止上一轮播报
  lastSpokenLen.value = 0  // 重置已念偏移
```

- [ ] **Step 4: 在 `finishMsg`（约第 218 行）函数体末尾、`scroll()` 之后追加，确保整段已念完**

```js
  // 整段回答结束后，把尚未成句的尾部也念掉
  if (aMsg.content && !voice.muted.value && aMsg.content.length > lastSpokenLen.value) {
    const fresh = voice.stripMarkdown(aMsg.content.slice(lastSpokenLen.value))
    const sentences = voice.splitSentences(fresh)
    if (sentences.length) voice.enqueueSentences(sentences)
    lastSpokenLen.value = aMsg.content.length
  }
```

- [ ] **Step 5: 加 answer 流式播报 watch（在 `onMounted(() => scroll())` 之前）**

```js
watch(
  () => {
    const last = msgs[msgs.length - 1]
    return last && last.role === 'assistant' ? last.content : ''
  },
  (content) => {
    // 仅当正在流式生成、且产生了新的完整句子时入队播报
    if (!content || voice.muted.value) return
    if (content.length <= lastSpokenLen.value) return
    const fresh = content.slice(lastSpokenLen.value)
    const sentences = voice.splitSentences(voice.stripMarkdown(fresh))
    // 只把以句号结尾的"已完整"句子念掉，未完句留给 finishMsg 兜底
    const complete = sentences.slice(0, sentences.length > 1 ? sentences.length - 1 : 0)
    if (complete.length) {
      lastSpokenLen.value += complete.join('').length + (fresh.match(/[。！？!\?\n]/g) || []).length
      voice.enqueueSentences(complete)
    }
  }
)
```

- [ ] **Step 6: 在模板 `.input-row` 挂入 VoiceButton（第 67 行 `<div class="input-row">` 之后、`<textarea>` 之前）**

```html
      <VoiceButton
        :status="voiceStatus" :muted="voiceMuted"
        :can-record="voiceCanRecord" :error="voiceError"
        @toggle-mic="voiceStatus === 'recording' ? voice.stop() : voice.start()"
        @toggle-mute="voice.setMuted(!voiceMuted)"
      />
```

- [ ] **Step 7: 在 `onMounted` 旁加 `onUnmounted` 清理（若已存在则合并）**

`onUnmounted` 已在第 77 行导入。在 `onMounted(() => scroll())` 之后追加：

```js
onUnmounted(() => {
  voice.stopSpeak()
})
```

- [ ] **Step 8: 验证构建通过**

Run（`web/` 目录）: `npm run build`
Expected: 构建成功，无 Vue 编译报错。

记录：AgentChatPanel 集成完成，语音助手已接入对话。

---

## Task 8: 前端 — 浏览器联调与生产构建

**Files:** 无（仅验证）。

- [ ] **Step 1: 启动后端 + 前端 dev**

后端：`python -m gateway.server`（端口 15002）。
前端（`web/` 目录）：`npm run dev`。
确认前端请求 `/api/voice/*` 能代理到 15002（复用现有 vite 代理配置）。

- [ ] **Step 2: 点按说话 → 文字进对话**

打开智能体对话页，点麦克风（变红）→ 说"仙桃站当前水位多少"→ 再点结束。
Expected：识别文字出现在输入框并自动发送；FloodMind 流式回答正常显示。

- [ ] **Step 3: 回答被语音播报**

Expected：回答逐句用 CosyVoice 播报；播报期间麦克风按钮变声波状态且**禁用**（防回环）；多句顺序播放不抢话。

- [ ] **Step 4: 静音开关**

点静音 → 当前播报立即停止、后续回答不播；再点恢复 → 下一轮回答恢复播报。

- [ ] **Step 5: 暂停 / 新轮停止旧播报**

回答生成中点"暂停"→ 停止播报；再次提问 → 上一轮未播完的不再播。

- [ ] **Step 6: 生产构建**

Run（`web/` 目录）: `npm run build`
Expected: 构建成功。

- [ ] **Step 7: 回归检查**

确认文字对话、CoT/工具卡片、智能研判弹窗（Overview）原有功能不受影响。

记录：Phase 1 语音助手端到端联调通过。

---

## Self-Review

**1. Spec coverage**
- 复用 dashscope_api_key → Task 1（config）+ Task 2（SDK init）。✓
- WorkspaceId 专属域名 → Task 2（base_websocket_api_url）。✓
- cosyvoice-v2 + v2 音色 → Task 1 config + Global Constraints 禁用 longanyang。✓
- paraformer-realtime-v2 + ffmpeg 转 wav → Task 2。✓
- 非流式两端 `call()` → Task 2。✓
- 半双工防回环 → Task 5 canRecord（speaking 时禁用）+ Task 6 禁用态。✓
- RPS=3 串行队列 → Task 5 串行 _playLoop。✓
- Markdown 清洗 → Task 5 stripMarkdown + Task 7 应用。✓
- 前端三件套 + AgentChatPanel 改动 → Task 4/5/6/7。✓
- Windows ffmpeg（conda PATH）→ Global Constraints + Task 2 默认 "ffmpeg" + Task 3 实跑。✓
- 测试计划（curl + 浏览器）→ Task 3 + Task 8。✓
- Phase 2 展望 → 本计划不含（正确，留待后续）。✓

**2. Placeholder scan**：无 TBD/TODO；每步含完整代码或具体命令。✓

**3. Type consistency**：`voice.status`/`muted`/`canRecord`/`error` 在 useVoice 返回（Task 5）、VoiceButton props（Task 6）、AgentChatPanel 解构为 `voiceStatus`/`voiceMuted`/`voiceCanRecord`/`voiceError`（Task 7）一致；`enqueueSentences`/`stopSpeak`/`stripMarkdown`/`splitSentences` 签名一致。✓

> **模板 ref 解包**：`voice` 是普通对象，模板里访问 `voice.status` 不会自动解包，故 Task 7 Step 2 已把模板要用的响应式状态解构为顶层绑定（`voiceStatus` 等），模板自动解包；方法仍用 `voice.stop()/start()/setMuted()`。脚本内（watch/finishMsg）访问 ref 仍用 `.value`。
