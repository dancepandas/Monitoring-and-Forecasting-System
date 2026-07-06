"""多渠道通知推送服务 — 已实现钉钉、企业微信 webhook，后续可扩展邮件/短信。

钉钉群机器人文档：
https://open.dingtalk.com/document/orgapp/robot-message-types-and-data-format

企业微信群机器人文档：
https://developer.work.weixin.qq.com/document/path/91770
"""

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Optional

import httpx

from . import warning_config
from .station_names import station_name

logger = logging.getLogger(__name__)


# ── 钉钉 ──

async def send_dingtalk_markdown(webhook_url: str, title: str, text: str, secret: Optional[str] = None) -> dict:
    """通过钉钉群机器人发送 markdown 消息。"""
    return await _send_dingtalk(webhook_url, {"msgtype": "markdown", "markdown": {"title": title, "text": text}}, secret)


async def _send_dingtalk(webhook_url: str, payload: dict, secret: Optional[str] = None) -> dict:
    if not webhook_url:
        return {"ok": False, "error": "webhook_url 为空"}

    url = webhook_url
    if secret:
        # 钉钉加签：timestamp + "\n" + secret 做 HMAC-SHA256，再 base64，再 URL encode
        ts = str(int(round(time.time() * 1000)))
        string_to_sign = f"{ts}\n{secret}"
        sign = base64.b64encode(hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()).decode("utf-8")
        sign_encoded = urllib.parse.quote_plus(sign)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={sign_encoded}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            body = r.json() if r.text else {}
            if r.status_code == 200 and body.get("errcode") == 0:
                logger.info("dingtalk push ok: %s", body)
                return {"ok": True, "dingtalk": body}
            logger.warning("dingtalk push failed: status=%s body=%s", r.status_code, body)
            return {"ok": False, "status": r.status_code, "dingtalk": body}
    except Exception as e:
        logger.exception("dingtalk push error")
        return {"ok": False, "error": str(e)}


# ── 企业微信 ──

async def send_wecom_markdown(webhook_url: str, content: str) -> dict:
    """通过企业微信机器人发送 markdown 消息。"""
    if not webhook_url:
        return {"ok": False, "error": "webhook_url 为空"}
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    return await _post_json(webhook_url, payload, channel="wecom")


async def _post_json(webhook_url: str, payload: dict, channel: str = "wecom") -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
            body = r.json() if r.text else {}
            if r.status_code == 200 and body.get("errcode") == 0:
                logger.info("%s push ok: %s", channel, body)
                return {"ok": True, channel: body}
            logger.warning("%s push failed: status=%s body=%s", channel, r.status_code, body)
            return {"ok": False, "status": r.status_code, channel: body}
    except Exception as e:
        logger.exception("%s push error", channel)
        return {"ok": False, "error": str(e)}


# ── 配置读取 ──

def _get_config() -> dict:
    return warning_config.get_standards()


def get_default_dingtalk_webhook() -> Optional[str]:
    return (_get_config().get("dingtalk_webhook") or "").strip() or None


def get_default_dingtalk_secret() -> Optional[str]:
    return (_get_config().get("dingtalk_secret") or "").strip() or None


def get_default_wecom_webhook() -> Optional[str]:
    return (_get_config().get("wecom_webhook") or "").strip() or None


# ── 统一告警推送 ──

async def push_alert(
    title: str,
    message: str,
    level: str = "提示",
    station_code: str = "",
    channel: str = "dingtalk",
    webhook_url: Optional[str] = None,
    secret: Optional[str] = None,
) -> dict:
    """推送一条告警消息。channel 支持 dingtalk / wecom。"""
    emoji = {"红色": "🚨", "橙色": "⚠️", "黄色": "🔶", "蓝色": "🔷", "提示": "ℹ️"}.get(level, "ℹ️")
    header = f"{emoji} **{title}** — {level}预警"
    station_line = f"\n**站点**：{station_name(station_code)}" if station_code else ""
    markdown = f"{header}{station_line}\n\n{message}\n\n— FloodMind 智能值守"

    if channel == "dingtalk":
        url = (webhook_url or "").strip() or get_default_dingtalk_webhook()
        if not url:
            return {"ok": False, "error": "未配置钉钉 webhook"}
        sec = (secret or "").strip() or get_default_dingtalk_secret()
        return await send_dingtalk_markdown(url, title, markdown, secret=sec or None)

    if channel == "wecom":
        url = (webhook_url or "").strip() or get_default_wecom_webhook()
        if not url:
            return {"ok": False, "error": "未配置企业微信 webhook"}
        return await send_wecom_markdown(url, markdown)

    return {"ok": False, "error": f"不支持的推送渠道: {channel}"}
