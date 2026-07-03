# 语音助手（数字人 Phase 1）设计文档

- 日期：2026-06-29
- 分支：`feat/sky-blue-cockpit-phase1`
- 范围：Phase 1 — 纯语音助手（点按说话 + 语音播报），不含数字人形象
- 引擎：阿里云百炼 DashScope（CosyVoice TTS + Paraformer ASR），官方 Python SDK
- 交互：点按说话（push-to-talk）

---

## 1. 目标与非目标

### 目标
- 用户在智能体对话界面**点按麦克风说话**，语音转文字后自动进入对话（复用现有 FloodMind 流式回答）。
- 智能体的回答**用语音播报**出来（CosyVoice 超拟人音色），边生成边按句播报。
- 全程走阿里云**官方 SDK**，不手搓 WebSocket 帧。

### 非目标（留给后续）
- 数字人形象 / 口型（Phase 2）。
- 双向流式 TTS 低延迟管道（Phase 1.5，可选）。
- 唤醒词常驻、VAD 自动断句（Phase 1 只做点按）。
- 实时"边说边出字"（Phase 1 ASR 用非流式整段识别）。

---

## 2. 架构总览

两端对称，均为**非流式 + 无状态 REST**，SDK 阻塞调用丢进 FastAPI 线程池。

```
① 听 → 说
  浏览器 MediaRecorder(webm/opus)
   └─ POST /api/voice/asr   ┐  后端：写临时文件 → ffmpeg 转 wav(16k/mono/pcm)
      ← { text }            ┘   → Recognition(paraformer-realtime-v2).call(wav)
                                  → result.get_sentence()['text']
  text 注入 AgentChatPanel.doSend()   ← 复用现有 SSE 流，底座零改动

② 读 → 念
  监听 answer，按句切分，剥 Markdown
   └─ POST /api/voice/tts { text }  ┐ 后端：SpeechSynthesizer(cosyvoice-v2).call(text)
      ← audio/mpeg                  ┘ → 前端队列串行播放（≤3 并发）
```

---

## 3. 后端设计（FastAPI gateway）

### 3.1 新增 `gateway/routes/voice.py`

模块加载时初始化 SDK（复用现有百炼 key）：

```python
import dashscope
from ..config import settings

if settings.dashscope_api_key:
    dashscope.api_key = settings.dashscope_api_key
# TTS（WebSocket）走业务空间专属域名，性能/稳定性更好
dashscope.base_websocket_api_url = (
    f"wss://{settings.dashscope_workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
)
```

#### ASR 端点 `POST /api/voice/asr`（FormData 上传音频）

```python
import os, tempfile, subprocess
from http import HTTPStatus
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from dashscope.audio.asr import Recognition
from ..auth.middleware import get_current_user

router = APIRouter(prefix="/api", tags=["voice"])

def _to_wav_16k_mono(src: str) -> str:
    """ffmpeg 把浏览器上传的 webm/opus 转成 Paraformer 能吃的 wav(16k/mono/pcm)。"""
    out = src + ".wav"
    subprocess.run(
        [settings.ffmpeg_path, "-y", "-i", src,
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out],
        check=True, capture_output=True,
    )
    return out

@router.post("/voice/asr")
def api_voice_asr(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    suffix = os.path.splitext(file.filename or ".webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(file.file.read()); src = tf.name
    wav = None
    try:
        wav = _to_wav_16k_mono(src)
        recog = Recognition(model=settings.asr_model, format="wav",
                            sample_rate=16000, language_hints=["zh", "en"],
                            callback=None)
        result = recog.call(wav)          # 阻塞，返回 RecognitionResult
        if result.status_code != HTTPStatus.OK:
            raise HTTPException(502, f"ASR 失败: {result.message}")
        text = (result.get_sentence() or {}).get("text", "")
        return {"text": text.strip()}
    finally:
        for p in (src, wav):
            if p and os.path.exists(p):
                try: os.unlink(p)
                except OSError: pass
```

#### TTS 端点 `POST /api/voice/tts`（JSON，返回 mp3）

```python
from dashscope.audio.tts_v2 import SpeechSynthesizer

@router.post("/voice/tts")
def api_voice_tts(body: dict, user: dict = Depends(get_current_user)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text 不能为空")
    synth = SpeechSynthesizer(model=settings.tts_model, voice=settings.tts_voice)
    audio = synth.call(text)              # 阻塞，返回 mp3 bytes（每次新建实例）
    if not audio:
        raise HTTPException(502, "TTS 返回空音频")
    return Response(audio, media_type="audio/mpeg")
```

要点：
- 两端都是**同步 `def`**，FastAPI 自动丢线程池；SDK 每次请求新建实例（SDK 要求）。
- **鉴权复用** `get_current_user`，与现有 `/api/*` 一致。
- ASR 的 `call()` 要**本地文件路径**，所以先写临时文件、转码、传路径，用完删除。
- ASR 报错（如格式/采样率不对）通过 502 返回，前端降级提示。

### 3.2 注册路由

`gateway/server.py`：

```python
from .routes import auth, data, forecast, agent, reports, system, notify, alerts, voice
# ...
app.include_router(voice.router)
```

### 3.3 配置（`gateway/config.py` 新增）

```python
# 百炼语音（复用现有 dashscope_api_key，不新增密钥）
dashscope_workspace_id: str = "llm-3kqn1siocgzbz9sp"   # TTS WebSocket 专属域名用
tts_model: str = "cosyvoice-v3-flash"
tts_voice: str = "longanyang"                           # v3-flash 系统音色（实测 v2 不接受公共音色，见下）
asr_model: str = "paraformer-realtime-v2"
ffmpeg_path: str = "ffmpeg"                              # conda 自带，PATH 可用
```

`dashscope_api_key` 已存在（agent 在用），直接复用。

> **模型/音色（实测修正）**：原计划 `cosyvoice-v2` 起步，但实测 **v2 对所有公共 `long*` 系统音色返回 `InvalidParameter / Engine error 418`**（v2 仅接受复刻/设计音色）。可用公共组合：**`cosyvoice-v3-flash` + `longanyang`**（官方示例、延迟最低，本期默认）或 `cosyvoice-v1` + `longxiaochun`。

> **IPv6 不可达（实测发现）**：本机与服务器 IPv6 路径不通，dashscope websocket-client 默认优先 IPv6 导致 WSS 5s 超时。`routes/voice.py` 模块加载时对 `aliyuncs.com`/`dashscope` 域名强制 IPv4 解析（monkeypatch `socket.getaddrinfo`，其余连接不受影响）。

> **ASR 结果形状**：非流式 `Recognition.call()` 的 `result.get_sentence()` 返回 **list[sentence]**（回调模式才是单句 dict），提取文字需兼容两种形状。

---

## 4. ffmpeg

**结论：本机与服务器（Windows + miniconda）已自带 ffmpeg，无需额外下载。**

已核实（`D:\chengs\7.miniconda\Library\bin\ffmpeg.exe`，4.3.1）：
- pcm_s16le 编码器 ✓、opus 解码器 ✓。
- 实跑 `webm → wav(16k/mono/pcm_s16le)` 转换成功。

该路径在 conda 的 `PATH` 上，所以代码用默认 `ffmpeg_path="ffmpeg"`、`subprocess.run(["ffmpeg", ...])` 即可被找到，无需配绝对路径。

> 若部署到**没有 miniconda** 的机器，再下载静态构建（gyan.dev / BtbN）的 `ffmpeg.exe`，把绝对路径配到 `ffmpeg_path`（`.env` 的 `FFMPEG_PATH=C:\...\ffmpeg.exe`）。`capture_output=True` + `check=True` 保证转码失败抛错带 stderr，便于诊断（常见错：上传格式与 `format` 不符、采样率不符）。

> 不引入额外 Python ffmpeg 封装库，直接 subprocess 调用官方二进制，符合"用标准工具、不手搓"原则。

---

## 5. 前端设计（Vue 3）

### 5.1 新增 `web/src/api/voice.js`

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
    const res = await fetch(`${BASE}/voice/asr`, { method: 'POST', headers: authHeaders(), body: form })
    if (!res.ok) throw new Error((await res.text()) || `ASR 失败 (${res.status})`)
    return (await res.json()).text
  },
  async speak(text) {
    const res = await fetch(`${BASE}/voice/tts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) throw new Error(`TTS 失败 (${res.status})`)
    return await res.blob()   // audio/mpeg
  },
}
```

### 5.2 新增 `web/src/composables/useVoice.js`

状态机：`idle | recording | transcribing | speaking | muted`。

职责：
- **录音**：`getUserMedia({ audio: true })` → `MediaRecorder`（默认 codec，通常 webm/opus）→ 收集 chunks → blob。
- **转写**：`stop()` 后 `voiceApi.transcribe(blob)` → 触发 `onResult(text)` 回调。
- **播报**：`enqueueSentences(textArray)` → worker 顺序播放；并发上限 3（守 TTS RPS=3）。每句 `voiceApi.speak` → `<audio>` 播放。
- **防回环（半双工）**：播报期间 `recordingEnabled=false`，麦克风按钮禁用；播报结束后恢复。
- **静音开关**：`muted` 状态，关闭时停止当前播放并禁止新播放。
- **Markdown 清洗**：进 TTS 前剥 ` ``` ` 代码块、表格行（含 `|`）、标题 `#`、`*`/`_` 强调、列表标记、链接 `[..](..)` → 纯文本。

### 5.3 新增 `web/src/components/VoiceButton.vue`

- 麦克风图标按钮 + 录音波纹动画；按 `useVoice` 状态切换样式（录制=红、转写=转圈、播报=声波、静音=划掉）。
- `@click` → idle 时 `start()`，recording 时 `stop()`。
- `@recognized="..."` 事件把文字抛给父组件。
- 旁边一个静音切换（喇叭/静音图标）。

### 5.4 改 `web/src/components/AgentChatPanel.vue`

- `.input-row` 挂入 `<VoiceButton @recognized="onVoiceText" />`（在 textarea 与发送按钮之间或最左）。
- `onVoiceText(text)`：`input.value = text; doSend()`（复用现有发送链路，零改动）。
- **播报触发**：watch 最后一条 assistant 消息的 `content`（answer 块纯文本，不含 CoT/工具），按 `。！？\n` 切句；每当出现新完整句，`useVoice.enqueueSentences([...new])`。避免重复入队（记录已播报偏移）。
- 暂停（`streaming` 中点暂停）时调用 `useVoice.stopSpeak()`。

### 5.5 Overview 弹窗里的 agent

Overview 的智能研判弹窗也用 `AgentChatPanel`，挂了 `VoiceButton` 即自动具备语音能力，无需额外改 OverviewPage。

---

## 6. 约束与坑（已并入设计）

| 约束 | 来源 | 应对 |
|---|---|---|
| CosyVoice RPS=3 | TTS 计费/限流文档 | 前端 TTS 队列 ≤3 并发 |
| `call()` 每次需新建实例 | TTS 文档 | 每请求新建（无状态 REST 天然满足） |
| `enable_markdown_filter` 仅 v3-flash 复刻音色支持 | TTS 文档 | 前端自做 Markdown 清洗 |
| ASR `call()` 要文件路径、不吃 webm | ASR 文档 | 后端写临时文件 + ffmpeg 转 wav 16k mono pcm |
| TTS WebSocket 需 WorkspaceId 专属域名 | TTS 文档 | `base_websocket_api_url` 用 `llm-3kqn1siocgzbz9sp` |
| GIL 高并发增延迟 | ASR 文档 | 单用户点按并发极低，线程池足够，不上进程池 |
| 自激回环 | 工程经验 | 播报期禁用麦克风（半双工） |
| 仅念 answer 自然语言 | 工程经验 | 只读 `content`（answer 块），剥 Markdown |

---

## 7. 依赖与改动面

### 后端
- `gateway/requirements.txt`：新增 `dashscope`。
- `gateway/config.py`：+5 个配置项（见 3.3）。
- `gateway/routes/voice.py`：**新增**。
- `gateway/server.py`：注册 `voice.router`。
- 部署：Windows 装 `ffmpeg.exe` + 配 `FFMPEG_PATH`；`.env` 配 `DASHSCOPE_WORKSPACE_ID`（默认已填）。

### 前端
- `web/src/api/voice.js`：**新增**。
- `web/src/composables/useVoice.js`：**新增**。
- `web/src/components/VoiceButton.vue`：**新增**。
- `web/src/components/AgentChatPanel.vue`：挂按钮 + `onVoiceText` + answer 播报触发 + 暂停停播。

---

## 8. 测试计划

- **后端单测/手测**
  - `/api/voice/tts`：固定中文短句 → 返回非空 mp3、`audio/mpeg`、可播放。
  - `/api/voice/asr`：用 ASR 文档示例 wav（或自录）→ 返回文字；传 webm 经 ffmpeg 转码后同样可用。
  - ffmpeg 缺失/路径错 → 502 带明确 stderr。
  - 未带 token → 401。
- **前端手测**
  - 点按录音 → 松开 → 文字进对话框并发送 → 收到流式回答并开口播报。
  - 长回答 → 多句顺序播报、不抢话。
  - 播报中麦克风禁用（防回环）。
  - 静音开关：关闭即时停播、新回答不播。
  - Chrome / Edge 通过（MediaRecorder + getUserMedia 需 https 或 localhost）。
- **回归**：现有文字对话、智能研判弹窗功能不受影响。

---

## 9. Phase 2 展望（不在本期）

- **数字人形象**：轻量动效形象（嘴型/眼神随音频幅度律动），先不追求真实对口型。
- **低延迟双向流式 TTS**：`streaming_call` 把 answer_delta 直接喂合成，首句 ~1s 内（需处理 23s 超时与代理 WS 管道）。
- **实时 ASR**：`Recognition.start()` + `send_audio_frame` 做"边说边出字"。
- **引擎可换**：`voice_provider` 抽象层，未来切私有化模型（FunASR/CosyVoice 本地）只换适配层。
