import asyncio
import logging

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from ._helpers import _safe_sync
from ..notifier import push_alert
from ..monitor_engine import get_engine
from ..system_events import write_event
# 辅助函数
# ---------------------------------------------------------------------------

class SendNotificationArgs(BaseModel):
    channel: str = Field("dingtalk", description="推送渠道：dingtalk 或 wecom")
    title: str = Field(..., description="消息标题")
    message: str = Field(..., description="消息正文")
    level: str = Field("提示", description="预警级别：红色/橙色/黄色/蓝色/提示")
    station_code: str = Field("", description="相关测站编码，可选")
    webhook_url: str = Field("", description="自定义 webhook 地址，为空则读配置")
    secret: str = Field("", description="钉钉加签 secret，为空则读配置")
    alert_id: str = Field("", description="关联的告警事件ID，推送成功后会更新该事件的推送计数")

def send_notification(**kwargs) -> dict:
    """向钉钉/企业微信推送一条通知消息；若提供 alert_id，会自动标记该告警已推送。"""
    channel = kwargs.get("channel", "dingtalk")
    title = kwargs.get("title", "")
    message = kwargs.get("message", "")
    level = kwargs.get("level", "提示")
    station_code = kwargs.get("station_code", "")
    webhook_url = kwargs.get("webhook_url", "") or ""
    secret = kwargs.get("secret", "") or ""
    alert_id = kwargs.get("alert_id", "") or ""
    try:
        result = _safe_sync(push_alert(
            title=title,
            message=message,
            level=level,
            station_code=station_code,
            channel=channel,
            webhook_url=webhook_url or None,
            secret=secret or None,
        ))
        if result.get("ok") and alert_id:
            try:
                _safe_sync(get_engine()._tracker.mark_notified(alert_id, [channel]))
            except Exception as mark_err:
                logger.warning("mark_notified failed: %s", mark_err)
        if result.get("ok"):
            write_event("notification", "notification_sent",
                f"告警推送: {channel} — {title[:80]}",
                station_code=station_code, severity=level)
        return {"code": 200 if result.get("ok") else 500, "data": result}
    except Exception as e:
        return {"code": 500, "error": str(e)}

class ListActiveAlertsArgs(BaseModel):
    station_code: str = Field("", description="按测站编码筛选，为空则返回全部")
    level: str = Field("", description="按级别筛选：红色/橙色/黄色/蓝色/提示，为空则返回全部")

def list_active_alerts(**kwargs) -> dict:
    """列出当前未解除的告警事件。"""
    station_code = kwargs.get("station_code", "") or ""
    level = kwargs.get("level", "") or ""
    engine = get_engine()
    events = asyncio.run_coroutine_threadsafe(
        engine._tracker.list_active(station_code=station_code or None, level=level or None),
        asyncio.get_event_loop(),
    ).result(timeout=10)
    return {
        "code": 200,
        "total": len(events),
        "alerts": [e.to_dict() for e in events],
    }

class AcknowledgeAlertArgs(BaseModel):
    alert_id: str = Field(..., description="要确认的告警ID")
    by: str = Field("智能体", description="确认人")

def acknowledge_alert(**kwargs) -> dict:
    """确认一条告警，表示已收到并正在处理。"""
    alert_id = kwargs.get("alert_id", "")
    by = kwargs.get("by", "智能体")
    engine = get_engine()
    event = asyncio.run_coroutine_threadsafe(
        engine._tracker.acknowledge(alert_id, by=by),
        asyncio.get_event_loop(),
    ).result(timeout=10)
    if not event:
        return {"code": 404, "error": "告警不存在或已解除"}
    return {"code": 200, "alert": event.to_dict()}

class ResolveAlertArgs(BaseModel):
    alert_id: str = Field(..., description="要解除的告警ID")
    resolution: str = Field("已处理", description="处置说明")
    by: str = Field("智能体", description="解除人")

def resolve_alert(**kwargs) -> dict:
    """解除一条告警并记录处置结果。"""
    alert_id = kwargs.get("alert_id", "")
    resolution = kwargs.get("resolution", "已处理")
    by = kwargs.get("by", "智能体")
    engine = get_engine()
    event = asyncio.run_coroutine_threadsafe(
        engine._tracker.resolve(alert_id, resolution=resolution, by=by),
        asyncio.get_event_loop(),
    ).result(timeout=10)
    if not event:
        return {"code": 404, "error": "告警不存在或已解除"}
    return {"code": 200, "alert": event.to_dict()}

# ---------------------------------------------------------------------------