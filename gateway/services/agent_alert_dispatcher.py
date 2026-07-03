"""告警事件智能体分发器 — 把 MonitorEngine 检测到的异常交给 Agent 做研判与推送决策。"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from .agent_service import AgentService
from .alert_tracker import AlertEvent, AlertTracker
from .notifier import push_alert
from ..config import settings
from . import warning_config

logger = logging.getLogger(__name__)

# 专用线程池：APScheduler 线程中运行 agent 流时使用，避免耗尽 scheduler 线程池
_dispatch_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alert-dispatch")


class AgentAlertDispatcher:
    """接收告警事件，启动一次 Agent 流，由智能体决定是否推送、如何处置。"""

    def __init__(self, tracker: AlertTracker):
        self._tracker = tracker
        self._running: set[str] = set()
        self._lock = threading.Lock()  # 保护 _running set 的竞态

    def dispatch(self, event: AlertEvent):
        """同步入口，由 MonitorEngine 在 tick 中调用。内部转异步执行。"""
        with self._lock:
            if event.id in self._running:
                logger.info("[alert-dispatch] already handling %s", event.id)
                return
            self._running.add(event.id)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（如在 APScheduler 线程），提交到专用线程池运行，避免阻塞 scheduler
            logger.warning("[alert-dispatch] no running event loop for %s, dispatching via executor", event.id)
            _dispatch_executor.submit(self._run_sync, event)
            return

        # 已在事件循环中，创建任务并确保任务结束时清理 _running
        task = asyncio.create_task(self._handle(event))

        def _on_done(t):
            try:
                t.result()
            except Exception as e:
                logger.exception("[alert-dispatch] task failed: %s", e)

        task.add_done_callback(_on_done)

    def _run_sync(self, event: AlertEvent):
        """在专用线程池中同步运行 agent 流（无事件循环时使用）。"""
        try:
            asyncio.run(self._handle(event))
        except Exception as e:
            logger.exception("[alert-dispatch] sync run failed: %s", e)
        finally:
            self._running.discard(event.id)

    async def _handle(self, event: AlertEvent):
        try:
            session_id = f"alert-{event.id}-{int(time.time())}"
            svc = AgentService.get_or_create_alert_agent(session_id)

            prompt = self._build_prompt(event)
            logger.info("[alert-dispatch] start alert agent for %s", event.id)

            # 消费 agent 流，工具执行（含 send_notification）会在流中完成
            async for _ in svc.stream(session_id, prompt):
                pass

            logger.info("[alert-dispatch] agent done for %s", event.id)

            # 兜底检查：红色/橙色告警如果 agent 结束后仍未推送，直接推送
            await self._fallback_push(event)
        except Exception as e:
            logger.exception("[alert-dispatch] handle failed: %s", e)
            # agent 异常时红色/橙色告警直接兜底推送
            if event.level in ("红色", "橙色", "红色预警", "橙色预警"):
                await self._direct_push(event, reason=f"Agent 研判异常: {e}")
        finally:
            self._running.discard(event.id)

    async def _fallback_push(self, event: AlertEvent):
        """Agent 流结束后检查是否已推送，红色/橙色告警未推送则兜底直推。"""
        # 重新加载事件状态
        updated = await self._tracker.get(event.id)
        if not updated:
            return
        if updated.notify_count > 0:
            return  # 已经推送过了
        if updated.acknowledged:
            return  # 已人工确认

        # 红色/橙色告警必须推送
        critical_levels = ("红色", "橙色", "红色预警", "橙色预警")
        if event.level in critical_levels:
            logger.warning("[alert-dispatch] %s level alert %s was not pushed by agent, fallback direct push",
                         event.level, event.id)
            await self._direct_push(updated, reason="Agent 研判后未推送，兜底直推")

    async def _direct_push(self, event: AlertEvent, reason: str):
        """绕过 Agent，直接推送告警到钉钉。"""
        try:
            cfg = warning_config.get_standards()
            webhook = cfg.get("dingtalk_webhook", "")
            secret = cfg.get("dingtalk_secret", "")

            if not webhook:
                logger.error("[alert-dispatch] no dingtalk webhook configured, cannot push")
                return

            await push_alert(
                title=f"[兜底] {event.title}",
                message=f"{event.message}\n\n> 推送原因: {reason}",
                level=event.level.replace("预警", ""),
                station_code=event.station_code,
                channel="dingtalk",
                webhook_url=webhook,
                secret=secret or None,
            )
            await self._tracker.mark_notified(event.id)
            logger.info("[alert-dispatch] fallback push success for %s", event.id)
        except Exception as e:
            logger.exception("[alert-dispatch] fallback push failed: %s", e)

    def _build_prompt(self, event: AlertEvent) -> str:
        ts = datetime.fromtimestamp(event.triggered_at).strftime("%Y-%m-%d %H:%M:%S")
        metric_text = ""
        if event.metric:
            metric_text = "\n**监测指标**：\n" + "\n".join(f"- {k}: {v}" for k, v in event.metric.items())

        return f"""你正在执行 FloodMind 7×24 智能值守任务。当前时间 {ts}，系统检测到一条异常事件，请你独立分析并决定是否推送告警给值班人员。

## 异常事件
- 事件ID：{event.id}（调用 send_notification 时必须传入此 alert_id）
- 站点：{event.station_code or '无'}
- 类型：{event.alert_type}
- 级别：{event.level}
- 标题：{event.title}
- 描述：{event.message}{metric_text}

## 你的任务
1. 先调用相关工具核实情况（如 diagnose_system、query_latest、query_video_status、list_warnings、query_flow 等）。
2. 判断这是真实险情、设备故障、数据异常，还是可忽略的波动。
3. 如果需要推送，调用 send_notification 时**必须传入 alert_id="{event.id}"**，并发送一条清晰、专业的告警消息。
4. 如果判断为误报或无需立即处理，则只输出结论，不要推送。

## 推送前检查（重要）
- 调用 `list_active_alerts` 查看该事件 `notify_count` 和 `acknowledged` 状态。
- 若 `notify_count > 0`，说明已经推送过，本次不要再推。
- 若 `acknowledged == True`，说明已有人工确认，本次不要再推。
- 若这是新事件且需要人工关注，再调用 send_notification。

## 输出要求
先给出你的分析结论，再说明是否已推送及原因。"""


_dispatcher: Optional[AgentAlertDispatcher] = None


def get_dispatcher(tracker: AlertTracker) -> AgentAlertDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AgentAlertDispatcher(tracker)
    return _dispatcher


def init_dispatcher(engine):
    """在 MonitorEngine 启动后调用，把 dispatcher 注册为事件处理器。"""
    dispatcher = get_dispatcher(engine._tracker)
    from .monitor_engine import set_alert_handler
    set_alert_handler(dispatcher.dispatch)
    logger.info("AgentAlertDispatcher registered")
