import logging
import os
import socket
import subprocess
import tempfile
from http import HTTPStatus

# 本机/服务器 IPv6 不可达：dashscope websocket-client 默认会先尝试 IPv6 地址，
# 导致 WSS 握手在 5s 内超时。强制 aliyun/dashscope 域名只走 IPv4 解析（其余连接不受影响）。
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_for_dashscope(host, port, family=0, type=0, proto=0, flags=0):
    if family in (0, socket.AF_UNSPEC) and isinstance(host, str) and ("aliyuncs.com" in host or "dashscope" in host):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _ipv4_for_dashscope

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
        # get_sentence() 非流式返回 list[sentence]，回调模式返回单句 dict，两种都要兼容
        sentences = result.get_sentence()
        if isinstance(sentences, list):
            text = "".join((s or {}).get("text", "") for s in sentences)
        elif isinstance(sentences, dict):
            text = sentences.get("text", "")
        else:
            text = ""
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
