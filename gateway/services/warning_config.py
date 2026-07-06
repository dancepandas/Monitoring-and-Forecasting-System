"""
预警/告警标准配置
- 预警(early-warning): 阈值逼近，提前防范
- 告警(alert): 已发生异常，需要处理

v2: 每个站点独立配置水位/流量预警阈值，不再使用全局统一值。
    stations.<code>.level / stations.<code>.flow  每站专属阈值
    _defaults.level / _defaults.flow              新站点回退默认值

消息规范：
- 系统问题: 描述现象 + 建议操作 + 管理员联系方式
- 水文问题: 直接指出具体问题 + 阈值对比
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .system_events import write_event

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "warning_standards.json"
_lock = threading.RLock()
_cache: dict | None = None

DEFAULT_STANDARDS = {
    # ── 每站独立阈值（v2 新增） ──
    # 格式: "00125": {"level": {...}, "flow": {...}}
    "stations": {},

    # ── 新站点回退默认值 ──
    "_defaults": {
        "level": {"blue": 34.0, "yellow": 35.0, "orange": 35.5, "red": 36.0},
        "flow": {"blue": 5000, "yellow": 8000, "orange": 12000, "red": 18000},
    },

    # ── 全局变化率阈值（暂不按站区分） ──
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
            "message_template": "测站 {station_code} 最近数据存在连续缺测（共 {missing_count} 条）。可能原因：传感器瞬时故障、信号干扰或 AiFlow 测量异常。建议现场检查传感器状态，必要时重启设备。如持续缺测，请联系管理员（管理员：{admin_contact}）。",
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
            "trigger": "所有站点缓存均为空",
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
    "wecom_webhook": "",
    "dingtalk_webhook": "",
    "dingtalk_secret": "",
    "dingtalk_outgoing_token": "",
    "dingtalk_bot_app_key": "",
    "dingtalk_bot_app_secret": "",
    "description": "默认预警标准 — v2 每站独立阈值",
}

_level_names = {"blue": "蓝色预警", "yellow": "黄色预警", "orange": "橙色预警", "red": "红色预警"}


def _migrate_if_needed(raw: dict) -> dict:
    """将旧格式（全局 level/flow）自动迁移为 v2 格式（每站独立阈值）。"""
    if "stations" in raw:
        return raw  # 已是 v2 格式

    logger.info("Migrating warning_standards.json to v2 (per-station thresholds)")
    existing_level = raw.pop("level", None)
    existing_flow = raw.pop("flow", None)

    migrated = dict(DEFAULT_STANDARDS)
    # 保留旧文件中的全局设置作为 _defaults
    if existing_level:
        migrated["_defaults"]["level"] = existing_level
    if existing_flow:
        migrated["_defaults"]["flow"] = existing_flow
    # 复制其他顶层字段（alerts, admin_contact, webhooks 等）
    for key, val in raw.items():
        if key not in ("stations", "_defaults"):
            migrated[key] = val

    return migrated


def load_standards() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        if _CONFIG_PATH.exists():
            try:
                raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                _cache = _migrate_if_needed(raw)
                if _cache != raw:
                    save_standards(_cache)  # 回写迁移后的格式
                logger.info("Loaded warning standards (v2) from %s", _CONFIG_PATH)
                return _cache
            except Exception:
                logger.exception("Failed to load warning standards, using defaults")
        _cache = dict(DEFAULT_STANDARDS)
        save_standards(_cache)
        return _cache


def save_standards(standards: dict) -> None:
    global _cache
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = _CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(standards, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CONFIG_PATH)
        _cache = dict(standards)


def get_standards() -> dict:
    """返回完整配置（含 stations、_defaults、alerts、admin_contact 等）。"""
    return load_standards()


def get_station_thresholds(station_code: str) -> dict:
    """返回指定站点的水位+流量阈值。

    以 _defaults 为基底，站点专属配置覆盖对应级别，确保未配置的级别正确回退。
    返回格式: {"level": {...}, "flow": {...}, "is_custom": bool}
    """
    cfg = load_standards()
    stations = cfg.get("stations", {})
    defaults = cfg.get("_defaults", {})
    default_level = dict(defaults.get("level", {}))
    default_flow = dict(defaults.get("flow", {}))

    station_cfg = stations.get(station_code, {})
    # 深合并：默认值打底，站点配置覆盖
    custom_level = station_cfg.get("level", {})
    custom_flow = station_cfg.get("flow", {})
    default_level.update(custom_level)
    default_flow.update(custom_flow)

    return {
        "level": default_level,
        "flow": default_flow,
        "is_custom": station_code in stations,
    }


def get_admin_contact() -> str:
    return load_standards().get("admin_contact", "系统管理员")


def update_station_threshold(station_code: str, category: str, level: str, value: float) -> dict:
    """更新指定站点指定类别的预警阈值。

    Args:
        station_code: 测站编码
        category: "level" (水位) 或 "flow" (流量)
        level: blue / yellow / orange / red
        value: 阈值数值
    Returns: 更新后的完整 standards 配置
    """
    if category not in ("level", "flow"):
        return {"error": f"未知类别: {category}，仅支持 level / flow"}
    if level not in ("blue", "yellow", "orange", "red"):
        return {"error": f"未知预警等级: {level}，仅支持 blue / yellow / orange / red"}

    standards = dict(load_standards())
    stations = standards.setdefault("stations", {})
    station_cfg = stations.setdefault(station_code, {})
    cat_cfg = station_cfg.setdefault(category, {})
    old_val = cat_cfg.get(level, "未设置")
    cat_cfg[level] = float(value)
    station_cfg[category] = cat_cfg
    stations[station_code] = station_cfg
    standards["stations"] = stations

    save_standards(standards)
    write_event("threshold", "threshold_updated",
        f"站点阈值变更: {station_code} {category}/{level} {old_val} → {value}",
        station_code=station_code,
        old_value=json.dumps({category: {level: str(old_val)}}, ensure_ascii=False),
        new_value=json.dumps({category: {level: str(value)}}, ensure_ascii=False))
    return standards


def update_standard(category: str, level: str, value: float) -> dict:
    """更新全局默认阈值或变化率（兼容旧接口）。

    用于 rate_of_change 等全局配置。stations 阈值请使用 update_station_threshold()。
    """
    standards = dict(load_standards())
    if category not in standards:
        return {"error": f"未知类别: {category}"}
    cat = standards[category]
    if not isinstance(cat, dict):
        cat = {}
        standards[category] = cat
    old_val = cat.get(level, "未设置")
    cat[level] = value
    save_standards(standards)
    write_event("threshold", "threshold_updated",
        f"全局默认阈值变更: {category}/{level} {old_val} → {value}",
        old_value=json.dumps({category: {level: str(old_val)}}, ensure_ascii=False),
        new_value=json.dumps({category: {level: str(value)}}, ensure_ascii=False))
    return standards


def check_level(value: float, station_code: str, thresholds: dict | None = None) -> str | None:
    """检查水位值在指定站点的预警级别。

    自动查询该站专属阈值，未配置时回退到 _defaults。
    调用方已有阈值 dict 时可通过 thresholds 参数传入，避免重复加载配置。
    """
    if thresholds is None:
        thresholds = get_station_thresholds(station_code)
    level_thresholds = thresholds.get("level", {})

    result = None
    for lv in ("blue", "yellow", "orange", "red"):
        if value >= level_thresholds.get(lv, float("inf")):
            result = lv
    return result


def check_flow(value: float, station_code: str, thresholds: dict | None = None) -> str | None:
    """检查流量值在指定站点的预警级别。

    自动查询该站专属阈值，未配置时回退到 _defaults。
    调用方已有阈值 dict 时可通过 thresholds 参数传入，避免重复加载配置。
    """
    if thresholds is None:
        thresholds = get_station_thresholds(station_code)
    flow_thresholds = thresholds.get("flow", {})

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
