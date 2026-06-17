"""
预警/告警标准配置
- 预警(early-warning): 阈值逼近，提前防范
- 告警(alert): 已发生异常，需要处理

消息规范：
- 系统问题: 描述现象 + 建议操作 + 管理员联系方式
- 水文问题: 直接指出具体问题 + 阈值对比
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "warning_standards.json"
_lock = threading.RLock()
_cache: dict | None = None

DEFAULT_STANDARDS = {
    # ── 预警阈值 ──
    "level": {
        "blue": 34.0,
        "yellow": 35.0,
        "orange": 35.5,
        "red": 36.0,
    },
    "flow": {
        "blue": 5000,
        "yellow": 8000,
        "orange": 12000,
        "red": 18000,
    },
    "rate_of_change": {
        "warning": 0.5,
        "danger": 1.0,
    },

    # ── 告警规则 ──
    "alerts": {
        "cache_stale": {
            "name": "数据缓存异常",
            "category": "系统",
            "level": "提示",
            "trigger": "缓存超过 600 秒未刷新，或数据为空",
            "message_template": "测站 {station_code} 的水位/流量数据缓存未就绪，可能原因：aiflow2 数据源连接异常或采集程序未正常运行。页面显示的数据可能不是最新值。如持续超过 10 分钟，请联系系统管理员（管理员：{admin_contact}）。",
        },
        "data_frozen": {
            "name": "数据长时间未更新",
            "category": "系统",
            "level": "黄色",
            "trigger": "缓存最新数据时间距当前 >2 小时",
            "message_template": "测站 {station_code} 数据已超过 {hours} 小时未更新（最后上报时间：{last_time}）。可能原因：遥测终端通信中断、aiflow2 数据接口异常或采集程序停止。请检查设备通信状态和 aiflow2 服务。如无法自行排查，请联系管理员（管理员：{admin_contact}）。",
        },
        "data_frozen_severe": {
            "name": "数据严重停更",
            "category": "系统",
            "level": "红色",
            "trigger": "缓存最新数据时间距当前 >4 小时",
            "message_template": "测站 {station_code} 数据已超过 {hours} 小时未更新（最后上报时间：{last_time}）。该站已处于数据盲区状态，调度决策请勿依赖此站数据。请立即排查遥测终端、aiflow2 数据链路及采集程序。如无法自行排查，请联系管理员（管理员：{admin_contact}）。",
        },
        "data_missing": {
            "name": "数据连续缺测",
            "category": "系统",
            "level": "提示",
            "trigger": "最近 10 条数据中连续 3 条以上 virtualFlow 或 waterLevel 为 null",
            "message_template": "测站 {station_code} 最近数据存在连续缺测（共 {missing_count} 条）。可能原因：传感器瞬时故障、信号干扰或 ADCP 测量异常。建议现场检查传感器状态，必要时重启设备。如持续缺测，请联系管理员（管理员：{admin_contact}）。",
        },
        "data_spike": {
            "name": "数据异常跳变",
            "category": "系统",
            "level": "黄色",
            "trigger": "相邻数据差值超过正常范围",
            "message_template": "测站 {station_code} 监测到数据异常跳变：{metric} 从 {prev_value} 突变为 {curr_value}，变化幅度超过正常波动范围。可能原因：传感器瞬时故障、信号干扰或水体瞬间波动。请核对数据是否合理，如为误报请忽略，如持续跳变需现场检查传感器。",
        },
        "collector_failure": {
            "name": "数据采集程序异常",
            "category": "系统",
            "level": "红色",
            "trigger": "采集子进程退出，或最近一轮成功率 < 50%",
            "message_template": "数据采集程序（collector）运行异常，最近一轮采集成功率仅 {success_rate}。系统可能无法获取最新水情数据，页面数据为历史缓存。请立即联系管理员重启采集服务（管理员：{admin_contact}）。",
        },
        "all_stations_empty": {
            "name": "全站数据不可用",
            "category": "系统",
            "level": "红色",
            "trigger": "所有站点（00106/00107/00108）缓存均为空",
            "message_template": "所有监测站点数据均不可用。可能原因：aiflow2 数据平台整体故障或网关与 aiflow2 之间网络中断。调度决策请勿依赖系统数据，请通过其他渠道获取水情信息。请立即联系管理员排查（管理员：{admin_contact}）。",
        },
        "report_generation_failed": {
            "name": "日报生成失败",
            "category": "系统",
            "level": "黄色",
            "trigger": "定时或手动生成日报时返回错误或超时",
            "message_template": "{report_type} 生成失败（目标日期：{date}，测站：{station_code}）。可能原因：生成脚本执行异常、python-docx 依赖缺失或系统资源不足。请检查 gateway 日志中的具体错误信息。如需手动补生成，可在日报归档页面操作或联系管理员（管理员：{admin_contact}）。",
        },
        "llm_unreachable": {
            "name": "AI 服务不可用",
            "category": "系统",
            "level": "提示",
            "trigger": "DashScope API 连续请求失败",
            "message_template": "AI 语言模型服务（DashScope）当前不可用，智能分析、日报/周报自动生成等功能将降级为纯数据模板。智能体对话功能不受影响（仍可查询数据和调用工具）。如持续超过 30 分钟，请联系管理员检查 DashScope API 配额和网络连接（管理员：{admin_contact}）。",
        },
        "level_flow_divergence": {
            "name": "水位流量关系异常",
            "category": "水文",
            "level": "提示",
            "trigger": "水位与流量连续 3 点变化趋势相反",
            "message_template": "测站 {station_code} 水位与流量变化趋势出现背离：近 3 个时段内，水位{'上升' if level_up else '下降'} 但流量{'下降' if level_up else '上升'}。此现象不符合正常的水位-流量关系规律，可能原因：传感器故障（水位计或流速仪异常）、断面冲淤变化、回水顶托影响。建议现场核验传感器数据，并检查上下游是否有特殊水情。",
        },
        "multi_station_escalation": {
            "name": "多站预警联动升级",
            "category": "水文",
            "level": "橙色",
            "trigger": "2 个及以上站点同时触发预警",
            "message_template": "多个测站同时触发预警（涉及站点：{stations}，最高预警等级：{max_level}）。此情况可能表明流域性洪水演进正在进行。建议：1）启动联防机制，上下游统一调度；2）加密水情会商频次；3）通知相关防汛单位做好应急准备。",
        },
    },

    # ── 管理员联系方式 ──
    "admin_contact": "系统管理员（值班电话：请在此处填写实际联系方式）",
    "description": "默认预警标准 — 适用于汉江流域中游测站",
}


_level_names = {"blue": "蓝色预警", "yellow": "黄色预警", "orange": "橙色预警", "red": "红色预警"}


def load_standards() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        if _CONFIG_PATH.exists():
            try:
                _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                logger.info("Loaded warning standards from %s", _CONFIG_PATH)
                return _cache
            except Exception:
                pass
        _cache = dict(DEFAULT_STANDARDS)
        save_standards(_cache)
        return _cache


def save_standards(standards: dict) -> None:
    global _cache
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        _CONFIG_PATH.write_text(json.dumps(standards, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = dict(standards)


def get_standards() -> dict:
    return load_standards()


def get_admin_contact() -> str:
    return load_standards().get("admin_contact", "系统管理员")


def update_standard(category: str, level: str, value: float) -> dict:
    standards = dict(load_standards())
    if category not in standards:
        return {"error": f"未知类别: {category}"}
    cat = standards[category]
    if not isinstance(cat, dict):
        cat = {}
        standards[category] = cat
    cat[level] = value
    save_standards(standards)
    return standards


def check_level(value: float, standards: dict) -> str | None:
    """检查水位值对应的预警级别。"""
    level_thresholds = standards.get("level", {})
    result = None
    for lv in ("blue", "yellow", "orange", "red"):
        if value >= level_thresholds.get(lv, float("inf")):
            result = lv
    return result


def check_flow(value: float, standards: dict) -> str | None:
    """检查流量值对应的预警级别。"""
    flow_thresholds = standards.get("flow", {})
    result = None
    for lv in ("blue", "yellow", "orange", "red"):
        if value >= flow_thresholds.get(lv, float("inf")):
            result = lv
    return result


def level_name(lv: str) -> str:
    return _level_names.get(lv, lv)


def invalidate_cache():
    global _cache
    with _lock:
        _cache = None
