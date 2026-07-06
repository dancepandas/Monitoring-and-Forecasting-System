"""系统状态查询工具 — 供 Agent 查询系统事件日志（告警历史、阈值变更、诊断记录、全量事件）。

这些工具是只读的，Agent 通过它们访问系统完整历史状态。
"""

import logging
from datetime import datetime
from typing import Callable

from pydantic import BaseModel, Field

from ..system_events import query_events

logger = logging.getLogger(__name__)


# ── 共享 helper：格式化事件列表为 Markdown 表格 ──

def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def _build_table(events: list[dict], columns: list[tuple[str, Callable[[dict], str]]],
                 title: str, empty_msg: str) -> str:
    """将事件列表渲染为 Markdown 表格。

    columns: [(header_label, cell_fn(event) -> str), ...]
    """
    if not events:
        return empty_msg
    header = "| " + " | ".join(c[0] for c in columns) + " |"
    sep = "|" + "|".join("------" for _ in columns) + "|"
    rows = []
    for e in events:
        cells = [c[1](e) for c in columns]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([title, "", header, sep] + rows)


# ── 输入模型 ──

class ListAlertHistoryInput(BaseModel):
    hours: int = Field(default=24, description="查询最近多少小时的告警历史")
    station_code: str = Field(default="", description="可选：指定测站编码，不传查全部")


class GetThresholdChangesInput(BaseModel):
    days: int = Field(default=7, description="查询最近多少天的阈值变更记录")


class GetSystemDiagnosisInput(BaseModel):
    pass


class GetRecentEventsInput(BaseModel):
    hours: int = Field(default=6, description="查询最近多少小时的所有系统事件")
    category: str = Field(default="", description="可选：按类别过滤（alert/threshold/diagnosis/report/schedule/notification）")


# ── 工具函数 ──

async def list_alert_history(**kwargs) -> str:
    """查询历史告警记录（含已触发、已解除、已确认等全部状态）。"""
    hours = kwargs.get("hours", 24)
    station_code = kwargs.get("station_code", "") or ""
    events = query_events(category="alert", hours=hours, limit=50, station_code=station_code)
    return _build_table(events, [
        ("时间",  lambda e: _fmt_ts(e["ts"])),
        ("站点",  lambda e: e["station_code"] or "—"),
        ("类型",  lambda e: e["event_type"]),
        ("级别",  lambda e: e["severity"]),
        ("摘要",  lambda e: e["summary"]),
        ("操作者", lambda e: e["session_id"]),
    ], f"最近 {hours} 小时告警记录（{len(events)} 条）：",
       f"最近 {hours} 小时内无告警记录。")


async def get_threshold_changes(**kwargs) -> str:
    """查询阈值变更日志（包含站点阈值和全局默认值的修改记录）。"""
    days = kwargs.get("days", 7)
    events = query_events(category="threshold", hours=days * 24, limit=50)
    return _build_table(events, [
        ("时间",   lambda e: _fmt_ts(e["ts"])),
        ("站点",   lambda e: e["station_code"] or "全局"),
        ("变更内容", lambda e: e["summary"]),
        ("操作者",  lambda e: e["session_id"]),
    ], f"最近 {days} 天阈值变更记录（{len(events)} 条）：",
       f"最近 {days} 天内无阈值变更记录。")


async def get_system_diagnosis(**_kwargs) -> str:
    """获取最近的系统诊断记录。"""
    events = query_events(category="diagnosis", hours=24, limit=5)
    _icons = {"info": "✅", "warning": "⚠️", "critical": "🔴"}
    return _build_table(events, [
        ("时间", lambda e: _fmt_ts(e["ts"])),
        ("状态", lambda e: _icons.get(e.get("severity", ""), "❓")),
        ("诊断摘要", lambda e: e["summary"]),
    ], f"最近诊断记录（{len(events)} 条）：",
       "暂无系统诊断记录。")


async def get_recent_events(**kwargs) -> str:
    """查询最近 N 小时内的所有系统事件（全类别时间线）。"""
    hours = kwargs.get("hours", 6)
    category = kwargs.get("category", "") or ""
    events = query_events(category=category, hours=hours, limit=50)
    rng = f"{category} " if category else ""
    return _build_table(events, [
        ("时间", lambda e: _fmt_ts(e["ts"])),
        ("类别", lambda e: e.get("category", "")),
        ("摘要", lambda e: e["summary"][:80]),
    ], f"最近 {hours} 小时系统事件（{len(events)} 条）：",
       f"最近 {hours} 小时内无{rng}事件记录。")
