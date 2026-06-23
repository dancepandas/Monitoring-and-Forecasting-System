"""告警事件生命周期管理：生成、去重、升级、恢复、持久化。"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ALERTS_FILE = Path(__file__).parent.parent / "data" / "active_alerts.json"


@dataclass
class AlertEvent:
    id: str
    station_code: str
    alert_type: str
    level: str
    title: str
    message: str
    metric: dict = field(default_factory=dict)
    triggered_at: float = field(default_factory=time.time)
    acknowledged: bool = False
    acknowledged_by: str = ""
    resolved_at: Optional[float] = None
    resolution: str = ""
    evidence: dict = field(default_factory=dict)
    notify_count: int = 0
    last_notify_at: Optional[float] = None
    push_channels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AlertEvent":
        return AlertEvent(**d)


class AlertTracker:
    """内存 + JSON 文件持久化的告警追踪器（异步安全）。"""

    def __init__(self, dedup_window_seconds: int = 1800):
        self.dedup_window = dedup_window_seconds
        self._alerts: dict[str, AlertEvent] = {}
        self._lock = asyncio.Lock()

    def _alert_id(self, station_code: str, alert_type: str, level: str) -> str:
        base = f"{station_code}:{alert_type}:{level}"
        return "alert_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    async def load(self):
        """异步加载持久化告警。"""
        await self._load()

    async def _load(self):
        if not _ALERTS_FILE.exists():
            return
        try:
            data = await asyncio.to_thread(_ALERTS_FILE.read_text, encoding="utf-8")
            parsed = json.loads(data)
            for k, v in parsed.items():
                self._alerts[k] = AlertEvent.from_dict(v)
            logger.info("loaded %d active alerts", len(self._alerts))
        except Exception as e:
            logger.warning("load active_alerts failed: %s", e)

    async def _save(self):
        try:
            _ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _ALERTS_FILE.with_suffix(".tmp")
            payload = json.dumps({k: v.to_dict() for k, v in self._alerts.items()}, ensure_ascii=False, indent=2, default=str)
            await asyncio.to_thread(tmp.write_text, payload, encoding="utf-8")
            await asyncio.to_thread(tmp.replace, _ALERTS_FILE)
        except Exception as e:
            logger.warning("save active_alerts failed: %s", e)

    async def create_or_update(
        self,
        station_code: str,
        alert_type: str,
        level: str,
        title: str,
        message: str,
        metric: Optional[dict] = None,
        evidence: Optional[dict] = None,
    ) -> tuple[AlertEvent, bool]:
        """
        创建或更新告警。
        返回 (event, is_new)。
        is_new=True 表示这是新事件，应该触发推送。
        """
        alert_id = self._alert_id(station_code, alert_type, level)
        now = time.time()

        # 持续性异常类型：超过去重窗口只更新不新建（避免触发-恢复-触发循环）
        PERSISTENT_TYPES = {"data_frozen", "cache_stale", "data_missing", "data_spike"}

        async with self._lock:
            existing = self._alerts.get(alert_id)
            if existing and existing.resolved_at is None:
                if now - existing.triggered_at < self.dedup_window:
                    # 窗口内：只更新内容，不推送
                    existing.message = message
                    existing.metric = metric or existing.metric
                    existing.evidence = evidence or existing.evidence
                    existing.title = title
                    await self._save()
                    return existing, False
                elif alert_type in PERSISTENT_TYPES or alert_type.startswith("level_") or alert_type.startswith("flow_") or alert_type.startswith("forecast_"):
                    # 持续异常：更新内容 + 刷新时间，保持活跃，不新建
                    existing.message = message
                    existing.metric = metric or existing.metric
                    existing.evidence = evidence or existing.evidence
                    existing.title = title
                    existing.triggered_at = now
                    await self._save()
                    logger.info("persistent alert %s updated (age > window), kept alive", alert_id)
                    return existing, False
                else:
                    # 非持续异常：超时恢复后新建
                    existing.resolved_at = now
                    existing.resolution = "超时自动恢复（同类型新事件触发）"

            event = AlertEvent(
                id=alert_id,
                station_code=station_code,
                alert_type=alert_type,
                level=level,
                title=title,
                message=message,
                metric=metric or {},
                triggered_at=now,
                evidence=evidence or {},
            )
            self._alerts[alert_id] = event
            await self._save()
            return event, True

    async def escalate(self, alert_id: str, new_level: str, new_title: str, new_message: str, metric: Optional[dict] = None) -> tuple[AlertEvent, bool]:
        """升级告警：关闭旧事件，创建新级别事件。"""
        now = time.time()
        async with self._lock:
            old = self._alerts.get(alert_id)
            if old and old.resolved_at is None:
                old.resolved_at = now
                old.resolution = f"升级为 {new_level} 告警"

            new_id = self._alert_id(old.station_code if old else "", old.alert_type if old else alert_id, new_level)
            event = AlertEvent(
                id=new_id,
                station_code=old.station_code if old else "",
                alert_type=old.alert_type if old else alert_id,
                level=new_level,
                title=new_title,
                message=new_message,
                metric=metric or (old.metric if old else {}),
                triggered_at=now,
            )
            self._alerts[new_id] = event
            await self._save()
            return event, True

    async def resolve(self, alert_id: str, resolution: str = "人工解除", by: str = "") -> Optional[AlertEvent]:
        async with self._lock:
            event = self._alerts.get(alert_id)
            if not event or event.resolved_at:
                return None
            event.resolved_at = time.time()
            event.resolution = resolution
            event.acknowledged = True
            event.acknowledged_by = by
            await self._save()
            return event

    async def acknowledge(self, alert_id: str, by: str = "") -> Optional[AlertEvent]:
        async with self._lock:
            event = self._alerts.get(alert_id)
            if not event:
                return None
            event.acknowledged = True
            event.acknowledged_by = by
            await self._save()
            return event

    async def mark_notified(self, alert_id: str, channels: list[str]):
        async with self._lock:
            event = self._alerts.get(alert_id)
            if not event:
                return
            event.notify_count += 1
            event.last_notify_at = time.time()
            event.push_channels = list(set(event.push_channels + channels))
            await self._save()

    async def list_active(self, station_code: Optional[str] = None, level: Optional[str] = None) -> list[AlertEvent]:
        async with self._lock:
            events = [e for e in self._alerts.values() if e.resolved_at is None]
        if station_code:
            events = [e for e in events if e.station_code == station_code]
        if level:
            events = [e for e in events if e.level == level]
        return sorted(events, key=lambda x: x.triggered_at, reverse=True)

    async def list_all(self, limit: int = 100) -> list[AlertEvent]:
        async with self._lock:
            events = list(self._alerts.values())
        return sorted(events, key=lambda x: x.triggered_at, reverse=True)[:limit]

    async def get(self, alert_id: str) -> Optional[AlertEvent]:
        async with self._lock:
            return self._alerts.get(alert_id)

    async def cleanup_resolved(self, max_age_days: int = 7):
        """清理已恢复超过 N 天的告警。"""
        cutoff = time.time() - max_age_days * 86400
        async with self._lock:
            to_remove = [k for k, e in self._alerts.items() if e.resolved_at and e.resolved_at < cutoff]
            for k in to_remove:
                del self._alerts[k]
            if to_remove:
                await self._save()
                logger.info("cleaned up %d resolved alerts", len(to_remove))
