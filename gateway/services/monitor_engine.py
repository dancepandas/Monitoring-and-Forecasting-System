"""24x7 智能值守引擎 — 只负责检测异常并生成 AlertEvent，不直接推送。

推送决策交给 AgentAlertDispatcher，由智能体综合分析后决定是否通知联系人。
由 gateway/server.py lifespan 启动，依赖 APScheduler 定时触发。
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Optional

from apscheduler.triggers.cron import CronTrigger

from ..config import settings
from . import data_cache, warning_config
from .alert_tracker import AlertEvent, AlertTracker

logger = logging.getLogger(__name__)

# 事件回调：发现新事件时调用 dispatcher
_alert_handler: Optional[Callable[[AlertEvent], None]] = None

# APScheduler 实例（模块级，避免被 pickle 进 job）
_scheduler = None


def set_alert_handler(handler: Callable[[AlertEvent], None]):
    global _alert_handler
    _alert_handler = handler


async def _tick_wrapper():
    """APScheduler job 包装函数，调用引擎实例的巡检逻辑。"""
    engine = MonitorEngine.get()
    await engine._tick()


async def _cleanup_wrapper():
    """APScheduler job 包装函数，调用引擎实例的清理逻辑。"""
    engine = MonitorEngine.get()
    engine._tracker.cleanup_resolved()


class MonitorEngine:
    """全局单例值守引擎。"""

    _instance: Optional["MonitorEngine"] = None

    def __init__(self):
        self._tracker = AlertTracker(dedup_window_seconds=1800)
        self._tick_job_id = "monitor_tick"
        self._cleanup_job_id = "monitor_cleanup"
        self._stations = [s.strip() for s in settings.station_codes.split(",") if s.strip()]
        self._device = settings.default_device_code

    @classmethod
    def get(cls) -> "MonitorEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self, scheduler):
        global _scheduler
        _scheduler = scheduler
        # 每 5 分钟巡检一次（用模块级包装函数，避免 pickle 引擎实例）
        scheduler.add_job(_tick_wrapper, trigger=CronTrigger(minute="*/5"), id=self._tick_job_id, replace_existing=True)
        # 每天凌晨清理已恢复告警
        scheduler.add_job(_cleanup_wrapper, trigger=CronTrigger(hour=3, minute=0), id=self._cleanup_job_id, replace_existing=True)
        logger.info("MonitorEngine started, stations=%s", self._stations)

    async def _tick(self):
        logger.info("[monitor] tick start")
        tasks = []
        for code in self._stations:
            tasks.append(self._check_station(code))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("[monitor] tick done")

    async def _check_station(self, station_code: str):
        try:
            await self._check_data_availability(station_code)
            await self._check_thresholds(station_code)
            await self._check_spike(station_code)
            await self._check_forecast_thresholds(station_code)
        except Exception as e:
            logger.exception("[monitor] check station %s failed: %s", station_code, e)

    # ------------------------------------------------------------------
    # 1. 数据可用性检查（基于 aligned 层）
    # ------------------------------------------------------------------
    async def _check_data_availability(self, station_code: str):
        standards = warning_config.get_standards()
        admin = warning_config.get_admin_contact()

        # 使用 aligned 层数据，与前端展示保持一致
        aligned = await data_cache.get_aligned(station_code, max_age=600)
        if not aligned:
            msg = standards["alerts"]["cache_stale"]["message_template"].format(
                station_code=station_code, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="cache_stale",
                level="提示",
                title=f"测站 {station_code} 数据缓存异常",
                message=msg,
                metric={"reason": "aligned 缓存为空"},
            )
            if is_new:
                self._emit(event)
            return

        records = aligned.get("records", [])
        if not records:
            msg = standards["alerts"]["cache_stale"]["message_template"].format(
                station_code=station_code, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="cache_stale",
                level="提示",
                title=f"测站 {station_code} 数据缓存异常",
                message=msg,
                metric={"reason": "aligned records 为空"},
            )
            if is_new:
                self._emit(event)
            return

        # 只取实测记录（排除 Chronos 预报填充值）
        measured = [r for r in records if r.get("waterLevel_source") == "measured" or r.get("virtualFlow_source") == "measured"]

        if not measured:
            msg = standards["alerts"]["cache_stale"]["message_template"].format(
                station_code=station_code, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="cache_stale",
                level="提示",
                title=f"测站 {station_code} 数据缓存异常",
                message=msg,
                metric={"reason": "无实测数据"},
            )
            if is_new:
                self._emit(event)
            return

        # aligned 按时间升序，最后一条 = 最新实测
        latest = measured[-1]
        last_time = latest.get("time", "")
        last_ts = self._parse_ts(last_time)
        age_hours = (time.time() - last_ts) / 3600 if last_ts else 999

        if age_hours > 4:
            msg = standards["alerts"]["data_frozen_severe"]["message_template"].format(
                station_code=station_code, hours=f"{age_hours:.1f}", last_time=last_time, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="data_frozen",
                level="红色",
                title=f"测站 {station_code} 数据严重停更",
                message=msg,
                metric={"age_hours": round(age_hours, 1), "last_time": last_time},
            )
            if is_new:
                self._emit(event)
        elif age_hours > 2:
            msg = standards["alerts"]["data_frozen"]["message_template"].format(
                station_code=station_code, hours=f"{age_hours:.1f}", last_time=last_time, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="data_frozen",
                level="黄色",
                title=f"测站 {station_code} 数据长时间未更新",
                message=msg,
                metric={"age_hours": round(age_hours, 1), "last_time": last_time},
            )
            if is_new:
                self._emit(event)
        else:
            # 数据恢复正常，自动解除相关告警
            self._auto_resolve(station_code, "cache_stale", "数据已恢复")
            self._auto_resolve(station_code, "data_frozen", "数据已恢复")

        # 连续缺测检查：最近 10 个网格点
        recent = records[-10:]
        null_count = sum(1 for r in recent if r.get("virtualFlow") is None)
        if null_count >= 3:
            msg = standards["alerts"]["data_missing"]["message_template"].format(
                station_code=station_code, missing_count=null_count, admin_contact=admin
            )
            event, is_new = self._tracker.create_or_update(
                station_code=station_code,
                alert_type="data_missing",
                level="提示",
                title=f"测站 {station_code} 数据连续缺测",
                message=msg,
                metric={"missing_count": null_count},
            )
            if is_new:
                self._emit(event)
        else:
            self._auto_resolve(station_code, "data_missing", "缺测已恢复")

    # ------------------------------------------------------------------
    # 2. 水文阈值检查（基于 aligned 层实测值）
    # ------------------------------------------------------------------
    async def _check_thresholds(self, station_code: str):
        standards = warning_config.get_standards()

        aligned = await data_cache.get_aligned(station_code, max_age=600)
        if not aligned:
            return
        records = aligned.get("records", [])
        if not records:
            return

        # 取最新一条有实测水位的记录
        wl, vf = None, None
        for r in reversed(records):
            if wl is None and r.get("waterLevel_source") == "measured" and r.get("waterLevel") is not None:
                wl = float(r["waterLevel"])
            if vf is None and r.get("virtualFlow_source") == "measured" and r.get("virtualFlow") is not None:
                vf = float(r["virtualFlow"])
            if wl is not None and vf is not None:
                break

        # 水位
        if wl is not None:
            lv = warning_config.check_level(wl, standards)
            if lv:
                lv_name = warning_config.level_name(lv)  # 完整名称，如 "蓝色预警"
                threshold = standards["level"][lv]
                event, is_new = self._tracker.create_or_update(
                    station_code=station_code,
                    alert_type=f"level_{lv}",
                    level=lv_name,
                    title=f"测站 {station_code} 水位{lv_name}",
                    message=f"当前水位 **{wl:.2f}m**，已达到 **{lv_name}** 阈值 **{threshold}m**，请加强监测并关注趋势变化。",
                    metric={"value": wl, "threshold": threshold, "unit": "m"},
                )
                if is_new:
                    self._emit(event)
            else:
                for lv in ("blue", "yellow", "orange", "red"):
                    self._auto_resolve(station_code, f"level_{lv}", "水位已回落至阈值以下")

        # 流量
        if vf is not None:
            lv = warning_config.check_flow(vf, standards)
            if lv:
                lv_name = warning_config.level_name(lv)
                threshold = standards["flow"][lv]
                event, is_new = self._tracker.create_or_update(
                    station_code=station_code,
                    alert_type=f"flow_{lv}",
                    level=lv_name,
                    title=f"测站 {station_code} 流量{lv_name}",
                    message=f"当前流量 **{vf:.0f}m³/s**，已达到 **{lv_name}** 阈值 **{threshold}m³/s**，请通知航运部门关注。",
                    metric={"value": vf, "threshold": threshold, "unit": "m³/s"},
                )
                if is_new:
                    self._emit(event)
            else:
                for lv in ("blue", "yellow", "orange", "red"):
                    self._auto_resolve(station_code, f"flow_{lv}", "流量已回落至阈值以下")

    # ------------------------------------------------------------------
    # 3. 数据突变检查（基于 aligned 层实测值）
    # ------------------------------------------------------------------
    async def _check_spike(self, station_code: str):
        standards = warning_config.get_standards()
        rate_cfg = standards.get("rate_of_change", {})
        danger_delta = rate_cfg.get("danger", 1.0)
        warning_delta = rate_cfg.get("warning", 0.5)

        aligned = await data_cache.get_aligned(station_code, max_age=600)
        if not aligned:
            return
        records = aligned.get("records", [])
        if len(records) < 2:
            return

        # 取最近两条有实测流量的记录（从最新往旧找）
        vals = []
        for r in reversed(records):
            if r.get("virtualFlow_source") == "measured" and r.get("virtualFlow") is not None:
                vals.append(float(r["virtualFlow"]))
            if len(vals) >= 2:
                break
        if len(vals) < 2:
            return

        curr, prev = vals[0], vals[1]
        delta = abs(curr - prev)

        if delta >= danger_delta:
            level = "黄色"
        elif delta >= warning_delta:
            level = "提示"
        else:
            self._auto_resolve(station_code, "data_spike", "数据波动恢复正常")
            return

        event, is_new = self._tracker.create_or_update(
            station_code=station_code,
            alert_type="data_spike",
            level=level,
            title=f"测站 {station_code} 数据异常跳变",
            message=f"流量从 **{prev:.0f}m³/s** 突变为 **{curr:.0f}m³/s**，变化幅度 **{delta:.0f}m³/s**，超过正常波动范围。请核对数据合理性，必要时现场检查传感器。",
            metric={"prev": prev, "curr": curr, "delta": delta},
        )
        if is_new:
            self._emit(event)

    # ------------------------------------------------------------------
    # 4. 预报预警检查（基于 aligned 层 Chronos-2 预报值）
    # ------------------------------------------------------------------
    async def _check_forecast_thresholds(self, station_code: str):
        """检查未来预报值是否超过阈值，提前发出预报预警。"""
        standards = warning_config.get_standards()

        aligned = await data_cache.get_aligned(station_code, max_age=600)
        if not aligned:
            return
        records = aligned.get("records", [])
        if not records:
            return

        # 取未来预报记录（source="forecast" 且时间在未来）
        now = datetime.now()
        forecast_records = []
        for r in records:
            if r.get("waterLevel_source") == "forecast" or r.get("virtualFlow_source") == "forecast":
                dt = self._parse_dt_str(r.get("time", ""))
                if dt and dt > now:
                    forecast_records.append(r)

        if not forecast_records:
            # 无预报数据，清除旧的预报告警
            for lv in ("blue", "yellow", "orange", "red"):
                self._auto_resolve(station_code, f"forecast_level_{lv}", "预报已过期")
                self._auto_resolve(station_code, f"forecast_flow_{lv}", "预报已过期")
            return

        # 预报水位检查
        for r in forecast_records:
            wl = r.get("waterLevel")
            if wl is not None:
                lv = warning_config.check_level(float(wl), standards)
                if lv:
                    lv_name = warning_config.level_name(lv)
                    threshold = standards["level"][lv]
                    forecast_time = r.get("time", "")
                    event, is_new = self._tracker.create_or_update(
                        station_code=station_code,
                        alert_type=f"forecast_level_{lv}",
                        level=f"预报{lv_name}",
                        title=f"测站 {station_code} 预报水位将达{lv_name}",
                        message=f"Chronos-2 预报 **{forecast_time}** 水位将达到 **{float(wl):.2f}m**，超过 **{lv_name}** 阈值 **{threshold}m**。请提前做好防范准备。",
                        metric={"value": float(wl), "threshold": threshold, "unit": "m", "forecast_time": forecast_time},
                    )
                    if is_new:
                        self._emit(event)
                    break  # 只报最高级别

        # 预报流量检查
        for r in forecast_records:
            vf = r.get("virtualFlow")
            if vf is not None:
                lv = warning_config.check_flow(float(vf), standards)
                if lv:
                    lv_name = warning_config.level_name(lv)
                    threshold = standards["flow"][lv]
                    forecast_time = r.get("time", "")
                    event, is_new = self._tracker.create_or_update(
                        station_code=station_code,
                        alert_type=f"forecast_flow_{lv}",
                        level=f"预报{lv_name}",
                        title=f"测站 {station_code} 预报流量将达{lv_name}",
                        message=f"Chronos-2 预报 **{forecast_time}** 流量将达到 **{float(vf):.0f}m³/s**，超过 **{lv_name}** 阈值 **{threshold}m³/s**。请通知航运部门提前关注。",
                        metric={"value": float(vf), "threshold": threshold, "unit": "m³/s", "forecast_time": forecast_time},
                    )
                    if is_new:
                        self._emit(event)
                    break

        # 清除未触发的预报告警级别
        for lv in ("blue", "yellow", "orange", "red"):
            has_wl = any(
                r.get("waterLevel") is not None and warning_config.check_level(float(r["waterLevel"]), standards) == lv
                for r in forecast_records
            )
            if not has_wl:
                self._auto_resolve(station_code, f"forecast_level_{lv}", "预报值未达该级别阈值")
            has_vf = any(
                r.get("virtualFlow") is not None and warning_config.check_flow(float(r["virtualFlow"]), standards) == lv
                for r in forecast_records
            )
            if not has_vf:
                self._auto_resolve(station_code, f"forecast_flow_{lv}", "预报值未达该级别阈值")

    # ------------------------------------------------------------------
    # 事件分发
    # ------------------------------------------------------------------
    def _emit(self, event: AlertEvent):
        logger.info("[monitor] new alert event: %s", event.id)
        if _alert_handler:
            try:
                _alert_handler(event)
            except Exception as e:
                logger.exception("[monitor] alert handler failed: %s", e)

    def _auto_resolve(self, station_code: str, alert_type: str, reason: str):
        """自动解除指定类型的活动告警。"""
        for event in self._tracker.list_active(station_code=station_code):
            if event.alert_type == alert_type and event.resolved_at is None:
                self._tracker.resolve(event.id, reason)
                logger.info("[monitor] auto resolved %s: %s", event.id, reason)

    @staticmethod
    def _parse_ts(t) -> float:
        if not t:
            return 0
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(str(t), fmt).timestamp()
            except Exception:
                pass
        return 0

    @staticmethod
    def _parse_dt_str(t) -> Optional[datetime]:
        if not t:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(str(t), fmt)
            except Exception:
                pass
        return None


# 兼容直接 import 的便捷入口
_engine: Optional[MonitorEngine] = None


def get_engine() -> MonitorEngine:
    global _engine
    if _engine is None:
        _engine = MonitorEngine()
    return _engine
