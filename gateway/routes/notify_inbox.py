"""钉钉 outgoing 机器人回调 — 接收群里 @机器人 的消息，转发给智能体并回推。"""

import base64
import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_429_TOO_MANY_REQUESTS

from ..services import warning_config, notifier
from ..services.agent_service import stream_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify-inbox"])

# ── 简单限流：单 conversation 每分钟 10 条 ──
_rate: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds


def _check_rate(conversation_id: str) -> bool:
    now = time.time()
    dq = _rate[conversation_id]
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        return False
    dq.append(now)
    return True


def _verify_dingtalk_sign(timestamp: Optional[str], sign: Optional[str], token: str) -> bool:
    """钉钉 outgoing 签名校验：sign = base64(HMAC-SHA256(timestamp + '\n' + token, ''))"""
    if not timestamp or not sign or not token:
        return False
    # 防重放：timestamp 超过 1 小时拒绝
    try:
        ts = int(timestamp)
        if abs(time.time() * 1000 - ts) > 3600_000:
            return False
    except (ValueError, TypeError):
        return False
    string_to_sign = f"{timestamp}\n{token}"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, sign)


@router.post("/dingtalk/inbox")
async def dingtalk_inbox(request: Request, timestamp: Optional[str] = Header(None), sign: Optional[str] = Header(None)):
    """钉钉 outgoing 机器人回调入口。不走 JWT 鉴权，用签名校验。"""
    body = await request.json()

    # 1. 签名校验
    standards = warning_config.get_standards()
    outgoing_token = standards.get("dingtalk_outgoing_token", "")
    if not outgoing_token:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="未配置 dingtalk_outgoing_token")
    if not _verify_dingtalk_sign(timestamp, sign, outgoing_token):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="签名校验失败")

    # 2. 解析消息
    text = body.get("text", {}).get("content", "").strip()
    sender_id = body.get("senderId", "unknown")
    conversation_id = body.get("conversationId", "default")
    if not text:
        return {"ok": True, "msg": "空消息，忽略"}

    # 3. 限流
    if not _check_rate(conversation_id):
        raise HTTPException(status_code=HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试")

    # 4. 调用 Agent（复用 stream_agent，用独立 session 避免混入前端会话）
    session_id = f"dingtalk-{conversation_id}"
    answer_text = ""
    try:
        async for event in stream_agent(session_id, text):
            t = event.get("type", "")
            if t == "answer_delta":
                answer_text += event.get("content", "")
            elif t == "error":
                answer_text = f"智能体出错：{event.get('content', '未知错误')}"
                break
    except Exception as e:
        logger.exception("dingtalk inbox agent error")
        answer_text = f"智能体处理失败：{e}"

    if not answer_text.strip():
        answer_text = "抱歉，我没能理解这条消息。"

    # 5. 回推到钉钉群
    webhook_url = standards.get("dingtalk_webhook", "")
    secret = standards.get("dingtalk_secret", "")
    if webhook_url:
        try:
            await notifier.send_dingtalk_markdown(
                webhook_url, "智能体回复",
                f"**问：** {text}\n\n**答：** {answer_text}",
                secret,
            )
        except Exception as e:
            logger.exception("dingtalk inbox reply push failed")

    return {"ok": True, "answer": answer_text}