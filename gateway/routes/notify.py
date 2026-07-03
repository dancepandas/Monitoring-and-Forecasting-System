import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from ..auth.middleware import get_current_user
from ..services import notifier, warning_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.post("/dingtalk")
async def api_send_dingtalk(
    title: str,
    message: str,
    webhook_url: str = "",
    secret: str = "",
    level: str = "提示",
    station_code: str = "",
    user: dict = Depends(get_current_user),
):
    """手动测试向钉钉群机器人推送一条 markdown 消息。"""
    result = await notifier.push_alert(
        title=title,
        message=message,
        level=level,
        station_code=station_code,
        channel="dingtalk",
        webhook_url=webhook_url or None,
        secret=secret or None,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=result.get("error") or "推送失败")
    return {"ok": True, "result": result}


@router.post("/wecom")
async def api_send_wecom(
    title: str,
    message: str,
    webhook_url: str = "",
    level: str = "提示",
    station_code: str = "",
    user: dict = Depends(get_current_user),
):
    """手动测试向企业微信群机器人推送一条 markdown 消息。"""
    result = await notifier.push_alert(
        title=title,
        message=message,
        level=level,
        station_code=station_code,
        channel="wecom",
        webhook_url=webhook_url or None,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=result.get("error") or "推送失败")
    return {"ok": True, "result": result}


@router.get("/config")
async def api_notify_config(user: dict = Depends(get_current_user)):
    """返回当前通知配置（脱敏）。"""
    standards = warning_config.get_standards()
    return {
        "dingtalk_webhook": _mask(standards.get("dingtalk_webhook", "")),
        "dingtalk_secret": "已配置" if standards.get("dingtalk_secret") else "未配置",
        "wecom_webhook": _mask(standards.get("wecom_webhook", "")),
    }


def _mask(url: str) -> str:
    if not url or len(url) < 20:
        return "未配置"
    return url[:20] + "***" + url[-8:]
