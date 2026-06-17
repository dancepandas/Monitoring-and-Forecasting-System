import asyncio
import json
import logging
import os
import subprocess
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import settings
from . import aiflow_client, chronos_client, data_cache
from . import warning_config, station_names

logger = logging.getLogger(__name__)

_DEVICE_CODE = settings.default_device_code
_sync_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-tool")


def _safe_sync(coro):
    """安全地在同步/异步混合环境中运行协程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已有运行中的事件循环，用线程跑
    fut = _sync_executor.submit(asyncio.run, coro)
    return fut.result(timeout=30)

async def _get_cached_level(station_code: str, max_age: int = 600) -> dict:
    """从本地缓存读取水位数据，避免直接请求 aiflow2。"""
    data = await data_cache.get(f"aiflow:level:{station_code}", max_age=max_age)
    if not data:
        return {"code": 200, "msg": "缓存未就绪", "data": [], "pageInfo": {"current": 1, "pages": 0, "size": 10, "total": 0}}
    return data


async def _get_cached_flow(station_code: str, max_age: int = 600) -> dict:
    """从本地缓存读取流量原始数据（flow_raw），返回与 query_flow 兼容的格式。"""
    data = await data_cache.get(f"aiflow:flow_raw:{station_code}:{_DEVICE_CODE}", max_age=max_age)
    if not data:
        return {"code": 200, "msg": "缓存未就绪", "data": [], "pageInfo": {"current": 1, "pages": 0, "size": 10, "total": 0}}
    raw_items = data.get("data", []) or []
    mapped = []
    for it in raw_items:
        if it.get("virtualFlow") is not None:
            mapped.append({
                "measureTime": it.get("measureTime"),
                "waterFlow": it.get("virtualFlow"),
                "virtualFlow": it.get("virtualFlow"),
                "stationCode": station_code,
            })
    return {"code": 200, "msg": "ok", "data": mapped, "pageInfo": {"current": 1, "pages": 1, "size": len(mapped), "total": len(mapped)}}


def _filter_by_time(items: list, begin: str, end: str, count: int) -> list:
    """按时间范围和条数过滤数据项。"""
    try:
        b = datetime.strptime(begin, "%Y-%m-%d %H:%M:%S.%f") if begin else None
        e = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f") if end else None
    except ValueError:
        try:
            b = datetime.strptime(begin, "%Y-%m-%d %H:%M:%S") if begin else None
            e = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") if end else None
        except ValueError:
            b = e = None

    def _parse_time(t):
        if isinstance(t, dict):
            return f"{t.get('year','')}-{str(t.get('month','')).zfill(2)}-{str(t.get('day','')).zfill(2)} {str(t.get('hours','')).zfill(2)}:{str(t.get('minutes','')).zfill(2)}"
        return str(t)

    filtered = items
    if b or e:
        def _in_range(it):
            try:
                ts = datetime.strptime(_parse_time(it.get("measureTime")), "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                try:
                    ts = datetime.strptime(_parse_time(it.get("measureTime")), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return False
            if b and ts < b:
                return False
            if e and ts > e:
                return False
            return True
        filtered = [it for it in filtered if _in_range(it)]
    return filtered[:count]

# ---------------------------------------------------------------------------
# 1. 数据查询工具（7 个）
# ---------------------------------------------------------------------------

class QueryWaterLevelArgs(BaseModel):
    """查询指定测站在一段时间内的水位数据。"""
    station_code: str = Field(..., description="测站编码")
    begin: str = Field(default="", description="开始时间，如 2026-06-01 00:00:00")
    end: str = Field(default="", description="结束时间，如 2026-06-15 23:59:59")
    count: int = Field(default=200, description="返回条数")


def query_water_level(**kwargs) -> dict:
    args = QueryWaterLevelArgs(**kwargs)
    b, e = (args.begin, args.end) if args.begin else _default_times()
    data = _safe_sync(_get_cached_level(args.station_code))
    items = data.get("data", []) or []
    filtered = _filter_by_time(items, b, e, args.count)
    return {**data, "data": filtered, "pageInfo": {"current": 1, "pages": 1, "size": len(filtered), "total": len(filtered)}}


class QueryFlowArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    begin: str = Field(default="", description="开始时间")
    end: str = Field(default="", description="结束时间")
    count: int = Field(default=200, description="返回条数")


def query_flow(**kwargs) -> dict:
    args = QueryFlowArgs(**kwargs)
    b, e = (args.begin, args.end) if args.begin else _default_times()
    data = _safe_sync(_get_cached_flow(args.station_code))
    items = data.get("data", []) or []
    filtered = _filter_by_time(items, b, e, args.count)
    return {**data, "data": filtered, "pageInfo": {"current": 1, "pages": 1, "size": len(filtered), "total": len(filtered)}}


class QueryLatestArgs(BaseModel):
    station_codes: str = Field(default=settings.station_codes.split(",")[0] if settings.station_codes else "00106", description="逗号分隔的测站编码")


def query_latest(**kwargs) -> dict:
    args = QueryLatestArgs(**kwargs)
    codes = [c.strip() for c in args.station_codes.split(",")]
    results = {}
    for code in codes:
        try:
            data = _safe_sync(_get_cached_level(code))
            items = data.get("data", []) or []
            results[code] = {"level": items[0] if items else None}
        except Exception as ex:
            logger.warning(f"query_latest failed for {code}: {ex}")
            results[code] = {"level": None}
    return {"stations": results, "updated": datetime.now().isoformat()}


class ListStationsArgs(BaseModel):
    pass


def list_stations(**kwargs) -> dict:
    ListStationsArgs(**kwargs)
    stations = []
    for code, name in station_names.STATION_NAMES.items():
        stations.append({"code": code, "name": name, "river": "汉江"})
    return {"stations": stations}


class CompareStationsArgs(BaseModel):
    station_codes: str = Field(..., description="逗号分隔的测站编码")
    metric: str = Field(default="level", description="对比指标：level / flow")
    begin: str = Field(default="", description="开始时间")
    end: str = Field(default="", description="结束时间")


def compare_stations(**kwargs) -> dict:
    args = CompareStationsArgs(**kwargs)
    codes = [c.strip() for c in args.station_codes.split(",")]
    b, e = (args.begin, args.end) if args.begin else _default_times()
    results = {}
    for code in codes:
        try:
            if args.metric == "flow":
                data = _safe_sync(_get_cached_flow(code))
                key = "waterFlow"
            else:
                data = _safe_sync(_get_cached_level(code))
                key = "waterLevel"
            items = _filter_by_time(data.get("data", []) or [], b, e, 200)
            values = [float(item.get(key, 0)) for item in items if item.get(key) is not None]
            results[code] = {
                "count": len(values),
                "max": max(values) if values else None,
                "min": min(values) if values else None,
                "avg": round(sum(values) / len(values), 2) if values else None,
            }
        except Exception as ex:
            logger.warning(f"compare_stations failed for {code}: {ex}")
            results[code] = {"error": str(ex)}
    return {"metric": args.metric, "stations": results}


class QueryDevicesArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")


def query_devices(**kwargs) -> dict:
    args = QueryDevicesArgs(**kwargs)
    return {
        "station_code": args.station_code,
        "devices": [
            {"device_code": f"{args.station_code}_D01", "type": "水位计", "status": "online"},
            {"device_code": f"{args.station_code}_D02", "type": "流量计", "status": "online"},
        ]
    }


class QueryVideoStatusArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")


def query_video_status(**kwargs) -> dict:
    args = QueryVideoStatusArgs(**kwargs)
    return {
        "station_code": args.station_code,
        "cameras": [
            {"id": f"{args.station_code}_CAM01", "status": "online", "url": ""},
        ]
    }


# ---------------------------------------------------------------------------
# 2. 预警 / 处置（2 个）
# ---------------------------------------------------------------------------

class ListWarningsArgs(BaseModel):
    station_codes: Optional[str] = Field(default=None, description="测站编码(逗号分隔),空则查所有常用站")
    level: Optional[str] = Field(default=None, description="筛选级别: blue/yellow/orange/red 或 提示/黄色/橙色/红色")
    category: Optional[str] = Field(default=None, description="筛选类别: 预警(阈值) / 告警-系统 / 告警-水文")


def list_warnings(**kwargs) -> dict:
    """返回 预警(阈值逼近) + 告警(已发生异常) 的完整列表。"""
    import time as _time
    args = ListWarningsArgs(**kwargs)
    codes = [c.strip() for c in (args.station_codes or settings.station_codes).split(",")]
    standards = warning_config.get_standards()
    admin = warning_config.get_admin_contact()
    warnings = []
    alerts = []

    _DEVICE = settings.default_device_code

    for code in codes:
        # ── 获取数据 ──
        level_data = _safe_sync(_get_cached_level(code))
        level_items = (level_data.get("data", []) or []) if level_data else []
        flow_data = _safe_sync(_get_cached_flow(code))
        flow_items = (flow_data.get("data", []) or []) if flow_data else []

        # ── 缓存状态 ──
        level_cached = bool(level_items)
        flow_cached = bool(flow_items)

        if not level_cached and not flow_cached:
            alerts.append({
                "id": f"AL-cache_stale-{code}",
                "type": "告警",
                "category": "系统",
                "name": "数据缓存异常",
                "level": "提示",
                "station_code": code,
                "message": f"测站 {code} 的水位和流量数据缓存均为空。可能原因：aiflow2 数据源连接异常或采集程序未正常运行。页面显示的数据可能不是最新值。如持续超过 10 分钟，请联系管理员（{admin}）。",
                "time": datetime.now().isoformat(),
            })
        elif not level_cached:
            alerts.append({
                "id": f"AL-cache_stale-{code}",
                "type": "告警",
                "category": "系统",
                "name": "数据缓存异常",
                "level": "提示",
                "station_code": code,
                "message": f"测站 {code} 的水位数据缓存为空。如持续超过 10 分钟，请联系管理员（{admin}）。",
                "time": datetime.now().isoformat(),
            })

        # ── A1/A2 水文阈值预警 ──
        wl_val = None
        for item in level_items:
            wl = item.get("waterLevel")
            if wl is not None:
                wl_val = float(wl)
                break
        if wl_val is None:
            for item in flow_items:
                wl = item.get("waterLevel")
                if wl is not None:
                    wl_val = float(wl)
                    break

        if wl_val is not None:
            lv = warning_config.check_level(wl_val, standards)
            if lv:
                threshold = standards["level"].get(lv, 0)
                warnings.append({
                    "id": f"EW-level-{code}-{lv}",
                    "type": "预警",
                    "category": "水文",
                    "name": "水位超限预警",
                    "level": lv,
                    "level_name": warning_config.level_name(lv),
                    "station_code": code,
                    "value": round(wl_val, 2),
                    "unit": "m",
                    "threshold": threshold,
                    "metric": "水位",
                    "message": f"测站 {station_names.station_name(code)} 当前水位 {wl_val:.2f}m，已达到{threshold}m（{warning_config.level_name(lv)}阈值）。距上一级阈值还有{_next_threshold_distance(standards['level'], lv, wl_val)}m。请加强监测并做好处置准备。",
                    "time": datetime.now().isoformat(),
                })

        vf_val = None
        for item in flow_items:
            vf = item.get("virtualFlow")
            if vf is not None:
                vf_val = float(vf)
                break
        if vf_val is not None:
            lv = warning_config.check_flow(vf_val, standards)
            if lv:
                threshold = standards["flow"].get(lv, 0)
                warnings.append({
                    "id": f"EW-flow-{code}-{lv}",
                    "type": "预警",
                    "category": "水文",
                    "name": "流量超限预警",
                    "level": lv,
                    "level_name": warning_config.level_name(lv),
                    "station_code": code,
                    "value": round(vf_val, 0),
                    "unit": "m³/s",
                    "threshold": threshold,
                    "metric": "流量",
                    "message": f"测站 {station_names.station_name(code)} 当前流量 {vf_val:.0f}m³/s，已达到{threshold}m³/s（{warning_config.level_name(lv)}阈值）。请通知航运部门关注，并检查堤防承受能力。",
                    "time": datetime.now().isoformat(),
                })

        # ── B2 数据停更检测 ──
        now_ts = _time.time()
        if flow_items:
            last_measure = _parse_time_to_ts(flow_items[0].get("measureTime", ""))
            if last_measure:
                hours = (now_ts - last_measure) / 3600
                if hours > 4:
                    alerts.append({
                        "id": f"AL-data_frozen_severe-{code}",
                        "type": "告警", "category": "系统",
                        "name": "数据严重停更",
                        "level": "红色",
                        "station_code": code,
                        "message": f"测站 {station_names.station_name(code)} 数据已超过 {hours:.1f} 小时未更新（最后上报：{flow_items[0].get('measureTime','')}）。该站已处于数据盲区状态。请立即排查遥测终端、aiflow2 数据链路及采集程序。如无法自行排查，请联系管理员（{admin}）。",
                        "time": datetime.now().isoformat(),
                    })
                elif hours > 2:
                    alerts.append({
                        "id": f"AL-data_frozen-{code}",
                        "type": "告警", "category": "系统",
                        "name": "数据长时间未更新",
                        "level": "黄色",
                        "station_code": code,
                        "message": f"测站 {station_names.station_name(code)} 数据已 {hours:.1f} 小时未更新（最后上报：{flow_items[0].get('measureTime','')}）。可能原因：遥测终端通信中断或 aiflow2 接口异常。请检查设备通信状态。如无法自行排查，请联系管理员（{admin}）。",
                        "time": datetime.now().isoformat(),
                    })

        # ── B3 数据缺测检测 ──
        if flow_items:
            null_count = sum(1 for it in flow_items[:10] if it.get("virtualFlow") is None)
            if null_count >= 3:
                alerts.append({
                    "id": f"AL-data_missing-{code}",
                    "type": "告警", "category": "系统",
                    "name": "数据连续缺测",
                    "level": "提示",
                    "station_code": code,
                    "message": f"测站 {code} 最近 10 条数据中有 {null_count} 条流量为空。可能原因：传感器瞬时故障或 ADCP 测量异常。建议现场检查传感器状态。如持续缺测，请联系管理员（{admin}）。",
                    "time": datetime.now().isoformat(),
                })

        # ── B4 数据异常跳变 ──
        if len(flow_items) >= 2:
            prev = flow_items[0].get("virtualFlow")
            curr = flow_items[1].get("virtualFlow")
            if prev is not None and curr is not None and prev != 0:
                change = abs(curr - prev) / prev
                if change > 0.5:
                    alerts.append({
                        "id": f"AL-data_spike-{code}",
                        "type": "告警", "category": "系统",
                        "name": "数据异常跳变",
                        "level": "黄色",
                        "station_code": code,
                        "message": f"测站 {station_names.station_name(code)} 流量数据出现异常跳变：从 {prev:.0f}m³/s 变为 {curr:.0f}m³/s，变化幅度 {change*100:.0f}%。可能原因：传感器瞬时故障或水体瞬间波动。如持续跳变需现场检查传感器。",
                        "time": datetime.now().isoformat(),
                    })

    if args.level:
        warnings = [w for w in warnings if w["level"] == args.level]
        alerts = [a for a in alerts if a["level"] == args.level]
    if args.category:
        if args.category == "预警":
            alerts = []
        elif args.category.startswith("告警"):
            warnings = []
        if "系统" in args.category:
            alerts = [a for a in alerts if a["category"] == "系统"]
        elif "水文" in args.category:
            warnings = [w for w in warnings if w["category"] == "水文"]
            alerts = [a for a in alerts if a["category"] == "水文"]

    return {
        "warnings": warnings,
        "warning_count": len(warnings),
        "alerts": alerts,
        "alert_count": len(alerts),
        "total": len(warnings) + len(alerts),
        "standards": {k: v for k, v in standards.items() if k in ("level", "flow")},
        "updated": datetime.now().isoformat(),
    }


def _next_threshold_distance(thresholds: dict, current_lv: str, value: float) -> str:
    """计算距离下一级阈值还有多远。"""
    ordered = ["blue", "yellow", "orange", "red"]
    idx = ordered.index(current_lv) if current_lv in ordered else -1
    if idx >= 0 and idx + 1 < len(ordered):
        next_lv = ordered[idx + 1]
        dist = thresholds.get(next_lv, float("inf")) - value
        if dist > 0:
            return f"{dist:.2f}"
    return "—"


def _parse_time_to_ts(t):
    """解析各种时间格式为 Unix timestamp。"""
    if not t:
        return 0
    if isinstance(t, dict):
        try:
            return datetime(t.get("year", 2000), t.get("month", 1), t.get("day", 1),
                          t.get("hours", 0), t.get("minutes", 0), t.get("seconds", 0)).timestamp()
        except Exception:
            return 0
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(t), fmt).timestamp()
        except ValueError:
            continue
    return 0


class GenerateDisposalArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    level: str = Field(default="yellow", description="预警级别: blue/yellow/orange/red")
    metric: str = Field(default="level", description="指标: level(水位) / flow(流量)")


def generate_disposal(**kwargs) -> dict:
    args = GenerateDisposalArgs(**kwargs)
    dp = {
        ("level", "blue"): [
            "密切关注水位变化，每4小时记录一次。",
            "检查遥测终端通信状态。",
        ],
        ("level", "yellow"): [
            "加强巡查频次，每2小时上报一次水位。",
            "通知下游单位关注水情变化。",
            "检查闸门、泵站设备状态。",
        ],
        ("level", "orange"): [
            "启动防汛应急预案，全员到岗。",
            "每1小时上报水位、流量数据。",
            "通知下游单位做好人员转移准备。",
            "开启泄洪闸门预泄，降低库容。",
            "安排专人巡查堤防险工险段。",
        ],
        ("level", "red"): [
            "立即启动一级防汛应急响应。",
            "组织危险区群众立即转移。",
            "所有闸门全开泄洪，泵站全力排涝。",
            "每30分钟上报水情数据。",
            "请求上级防汛指挥部支援。",
            "安排武警、消防待命抢险。",
        ],
        ("flow", "blue"): [
            "关注流量变化趋势，检查上下游水情。",
        ],
        ("flow", "yellow"): [
            "加密流量监测频次，每1小时记录。",
            "通知航运部门注意航行安全。",
        ],
        ("flow", "orange"): [
            "发布航行警告，必要时封航。",
            "检查堤防承受能力，准备抢险物资。",
        ],
        ("flow", "red"): [
            "全面封航，所有船只回港避洪。",
            "启动溃堤应急预案，组织抢险队伍。",
        ],
    }
    suggestions = dp.get((args.metric, args.level), [
        "保持常规监测，关注水情变化趋势。",
    ])
    return {
        "station_code": args.station_code,
        "level": args.level,
        "metric": args.metric,
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(),
    }


class UpdateWarningStandardArgs(BaseModel):
    category: str = Field(..., description="类别: level(水位) / flow(流量) / rate_of_change(变化率)")
    level: str = Field(..., description="级别: blue/yellow/orange/red 或 warning/danger")
    value: float = Field(..., description="新的阈值")


def update_warning_standard(**kwargs) -> dict:
    """修改预警标准阈值。category: level/flow/rate_of_change, level: blue/yellow/orange/red/warning/danger, value: 新阈值"""
    args = UpdateWarningStandardArgs(**kwargs)
    return warning_config.update_standard(args.category, args.level, args.value)


# ---------------------------------------------------------------------------
# 3. 预报 / 趋势（2 个）
# ---------------------------------------------------------------------------

class RunForecastArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    prediction_length: int = Field(default=72, description="预测步长（小时）")
    target: str = Field(default="Flow", description="目标字段")


def run_forecast(**kwargs) -> dict:
    """Chronos 时序预报。优先从本地缓存读取 flow_raw 历史流量数据。"""
    args = RunForecastArgs(**kwargs)

    try:
        flow_data = _safe_sync(_get_cached_flow(args.station_code, max_age=600))
    except Exception as ex:
        logger.warning(f"run_forecast get cached flow failed: {ex}")
        return {"error": str(ex), "station_code": args.station_code}

    raw_items = flow_data.get("data", [])
    if not raw_items:
        return {"error": "无历史流量数据", "station_code": args.station_code}

    series = _time_series(raw_items, "waterFlow")
    if len(series) < 10:
        return {"error": f"历史数据不足（仅 {len(series)} 条）", "station_code": args.station_code}

    # ── 预处理 ──
    preprocess_result = _preprocess_series(series)
    if preprocess_result.get("error"):
        return preprocess_result

    clean_series = preprocess_result["series"]
    logger.info("run_forecast: raw=%d, clean=%d, interval=%s",
                len(series), len(clean_series), preprocess_result.get("interval"))

    try:
        result = _safe_sync(chronos_client.predict_flow(
            clean_series, args.prediction_length,
            target=args.target,
            context_length=min(len(clean_series), 72),
        ))
    except Exception as ex:
        logger.warning(f"run_forecast predict failed: {ex}")
        return {"error": str(ex), "station_code": args.station_code}

    return {
        "station_code": args.station_code,
        "input_count": len(clean_series),
        "preprocess": preprocess_result,
        "result": result,
    }


def _preprocess_series(series: list[dict]) -> dict:
    """
    Chronos 预处理管线:
    1. 提取时间戳和值
    2. 检测主时间间隔
    3. 构建等间隔时间线, 匹配最近数据点
    4. 空缺值处理 — >3连续空缺丢弃, ≤3插值
    5. 数据不足(≤5)则不可预报
    """
    from datetime import datetime as dt

    # 1. 提取 (timestamp, value)
    points = []
    for s in series:
        try:
            t_str = s["Time"]
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    t = dt.strptime(t_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                continue
            points.append((t, s["Flow"]))
        except (ValueError, KeyError):
            continue
    if len(points) < 5:
        return {"error": f"有效数据点不足(仅{len(points)}个)", "series": []}
    points.sort(key=lambda x: x[0])

    # 2. 检测主流时间间隔
    diffs = []
    for i in range(1, len(points)):
        diff = (points[i][0] - points[i-1][0]).total_seconds() / 60
        diffs.append(diff)
    from collections import Counter
    interval_counter = Counter(round(d) for d in diffs)
    dominant_interval = interval_counter.most_common(1)[0][0]
    if dominant_interval <= 0:
        dominant_interval = 5

    # 3. 构建等间隔时间线 + 值对齐
    start = points[0][0]
    end = points[-1][0]
    total_steps = int((end.timestamp() - start.timestamp()) / 60 / dominant_interval) + 1
    timeline = []
    from datetime import timedelta

    # 建立时间→值的索引库
    value_index = {}
    for t, v in points:
        ts = t.timestamp()
        value_index[ts] = v

    for step in range(total_steps):
        target_t = start + timedelta(minutes=dominant_interval * step)
        target_ts = target_t.timestamp()
        # 在原始数据中找最近点 (容差: 半个间隔)
        half_interval_sec = dominant_interval * 30
        best_val = None
        for ts, v in value_index.items():
            if abs(ts - target_ts) < half_interval_sec:
                best_val = v
                break
        timeline.append((target_t, best_val))

    # 4. 检测连续空缺
    missing_runs = []  # [(start_idx, count), ...]
    current = 0
    for i, (t, v) in enumerate(timeline):
        if v is None:
            current += 1
        elif current > 0:
            missing_runs.append((i - current, current))
            current = 0
    if current > 0:
        missing_runs.append((len(timeline) - current, current))

    gap_desc = []
    if not missing_runs:
        gap_desc.append("数据完整,无空缺")
    else:
        max_run = max(r[1] for r in missing_runs)
        if max_run > 3:
            # 找最后一个>3空缺, 丢弃它及之前数据
            last_bad = 0
            for idx, count in missing_runs:
                if count > 3:
                    last_bad = idx + count  # 丢弃到空缺结束位置
            if last_bad >= len(timeline):
                return {"error": "所有数据都在大空缺之前", "series": []}
            timeline = timeline[last_bad:]
            dropped = last_bad
            gap_desc.append(f"连续空缺>3个,丢弃前{dropped}个点({start.strftime('%H:%M')}~{(start+timedelta(minutes=dominant_interval*(dropped-1))).strftime('%H:%M')})")
            missing_runs = [(i - dropped, c) for i, c in missing_runs if i + c > dropped]
        else:
            gap_desc.append(f"空缺均≤3,共{len(missing_runs)}处,线性插值填充")

        # 处理剩余空缺 (≤3): 插值填充
        for idx, count in missing_runs:
            if idx > 0 and idx + count < len(timeline):
                prev_val = timeline[idx - 1][1]
                next_val = timeline[idx + count][1]
                if prev_val is not None and next_val is not None:
                    for j in range(count):
                        ratio = (j + 1) / (count + 1)
                        interp_val = prev_val + (next_val - prev_val) * ratio
                        timeline[idx + j] = (timeline[idx + j][0], round(interp_val, 2))

    # 5. 过滤掉仍有 None 的点
    valid = [(t, v) for t, v in timeline if v is not None]
    if len(valid) < 5:
        return {"error": f"处理后可用数据点不足(仅{len(valid)}个)", "series": []}

    # 6. 取最后72个
    if len(valid) > 72:
        valid = valid[-72:]

    return {
        "series": [{"Time": t.strftime("%Y-%m-%d %H:%M"), "Flow": v} for t, v in valid],
        "interval": f"{dominant_interval}min",
        "raw_count": len(points),
        "clean_count": len(valid),
        "gap_info": "; ".join(gap_desc) if gap_desc else "无空缺",
    }


# _interpolate_fill 保留兼容，但新逻辑已内联
def _interpolate_fill(points: list, interval_min: int) -> list:
    """线性插值填充空缺值（已废弃，保留兼容）"""
    return points


class AnalyzeTrendArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    metric: str = Field(default="level", description="指标：level / flow")
    days: int = Field(default=7, description="回溯天数")


def analyze_trend(**kwargs) -> dict:
    args = AnalyzeTrendArgs(**kwargs)
    try:
        if args.metric == "flow":
            data = _safe_sync(_get_cached_flow(args.station_code, max_age=600))
            key = "waterFlow"
        else:
            data = _safe_sync(_get_cached_level(args.station_code, max_age=600))
            key = "waterLevel"
    except Exception as ex:
        return {"error": str(ex), "station_code": args.station_code}
    items = _filter_by_time(data.get("data", []) or [], "", "", 500)
    values = [float(item.get(key, 0)) for item in items if item.get(key) is not None]
    if not values:
        return {"error": "无数据", "station_code": args.station_code}
    n = len(values)
    x = list(range(n))
    mean_x = sum(x) / n
    mean_y = sum(values) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
    den = sum((xi - mean_x) ** 2 for xi in x)
    slope = num / den if den else 0
    trend = "up" if slope > 0.01 else "down" if slope < -0.01 else "stable"
    return {
        "station_code": args.station_code,
        "metric": args.metric,
        "count": n,
        "slope": round(slope, 4),
        "trend": trend,
        "latest": values[-1] if values else None,
    }


# ---------------------------------------------------------------------------
# 4. 报告（2 个）
# ---------------------------------------------------------------------------

class GenerateReportArgs(BaseModel):
    report_type: str = Field(default="daily", description="报告类型：daily / weekly / monthly")
    station_code: str = Field(..., description="测站编码")
    date: str = Field(default="", description="日期，如 2026-06-15")


def generate_report(**kwargs) -> dict:
    args = GenerateReportArgs(**kwargs)
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    cmd = [
        "python", "-m", "gateway.scripts.generate_report",
        "--type", args.report_type,
        "--station", args.station_code,
        "--date", date,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"generate_report subprocess failed: {result.stderr}")
            return {"error": result.stderr, "cmd": " ".join(cmd)}
        output = json.loads(result.stdout)
        return output
    except Exception as ex:
        logger.error(f"generate_report exception: {ex}")
        return {"error": str(ex), "cmd": " ".join(cmd)}


class QueryReportsArgs(BaseModel):
    pass


def query_reports(**kwargs) -> dict:
    QueryReportsArgs(**kwargs)
    reports_dir = Path(settings.reports_dir)
    if not reports_dir.exists():
        return {"reports": []}
    files = sorted(reports_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "reports": [
            {
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
            for f in files
        ]
    }


# ---------------------------------------------------------------------------
# 5. 文件检索（2 个）
# ---------------------------------------------------------------------------

class GlobArgs(BaseModel):
    pattern: str = Field(..., description="glob 模式，如 **/*.py")
    path: str = Field(default=".", description="搜索根目录")


def glob_search(**kwargs) -> dict:
    args = GlobArgs(**kwargs)
    root = Path(args.path)
    matches = sorted(root.glob(args.pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "matches": [str(p) for p in matches],
        "count": len(matches),
    }


class GrepArgs(BaseModel):
    pattern: str = Field(..., description="正则表达式")
    path: str = Field(default=".", description="搜索根目录")
    glob: str = Field(default="*", description="文件过滤模式")


def grep_search(**kwargs) -> dict:
    args = GrepArgs(**kwargs)
    root = Path(args.path)
    regex = re.compile(args.pattern)
    matches = []
    for file_path in root.rglob(args.glob):
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append({"file": str(file_path), "line": i, "text": line})
    return {"matches": matches, "count": len(matches)}


# ---------------------------------------------------------------------------
# 6. 定时任务（3 个）
# ---------------------------------------------------------------------------

class CreateScheduledTaskArgs(BaseModel):
    task_type: str = Field(..., description="任务类型：generate_report / run_forecast / check_warnings")
    cron: str = Field(..., description="cron 表达式，如 0 9 * * *")
    params: dict = Field(default_factory=dict, description="任务参数 JSON")


def create_scheduled_task(**kwargs) -> dict:
    args = CreateScheduledTaskArgs(**kwargs)
    from . import scheduler
    task_id = scheduler.create_task(args.task_type, args.cron, args.params)
    return {"task_id": task_id, "task_type": args.task_type, "cron": args.cron}


class ListScheduledTasksArgs(BaseModel):
    pass


def list_scheduled_tasks(**kwargs) -> dict:
    ListScheduledTasksArgs(**kwargs)
    from . import scheduler
    tasks = scheduler.list_tasks()
    return {"tasks": tasks}


class CancelScheduledTaskArgs(BaseModel):
    task_id: str = Field(..., description="任务 ID")


def cancel_scheduled_task(**kwargs) -> dict:
    args = CancelScheduledTaskArgs(**kwargs)
    from . import scheduler
    ok = scheduler.cancel_task(args.task_id)
    return {"success": ok, "task_id": args.task_id}


# ---------------------------------------------------------------------------
# 6.5 系统自诊断与自愈
# ---------------------------------------------------------------------------

class DiagnoseSystemArgs(BaseModel):
    """系统诊断：检查所有站点缓存状态、数据时效。"""
    pass


def diagnose_system(**kwargs) -> dict:
    """诊断系统缓存状态，判断是单站故障还是全局故障。"""
    import time as _time
    DiagnoseSystemArgs(**kwargs)
    codes = [s.strip() for s in settings.station_codes.split(",")]
    DEVICE = settings.default_device_code
    now_ts = _time.time()
    stations_result = []

    for code in codes:
        level_data = _safe_sync(_get_cached_level(code, max_age=600))
        flow_data = _safe_sync(_get_cached_flow(code, max_age=600))
        level_items = (level_data.get("data", []) or []) if level_data else []
        flow_items = (flow_data.get("data", []) or []) if flow_data else []

        last_time = ""
        age_h = 0
        if flow_items:
            last_time = str(flow_items[0].get("measureTime", ""))
            ts = _parse_time_to_ts(last_time)
            age_h = (now_ts - ts) / 3600 if ts else 0

        null_count = sum(1 for it in flow_items[:10] if it.get("virtualFlow") is None)

        stations_result.append({
            "station_code": code,
            "level_records": len(level_items),
            "flow_records": len(flow_items),
            "last_data_time": last_time,
            "data_age_hours": round(age_h, 1),
            "recent_nulls": null_count,
            "status": "healthy" if flow_items and age_h < 2 else "warning" if age_h < 4 else "critical" if flow_items else "no_data",
        })

    all_empty = all(s["flow_records"] == 0 for s in stations_result)
    diagnosis = "global_failure" if all_empty else \
                "partial_failure" if any(s["status"] == "critical" for s in stations_result) else \
                "degraded" if any(s["status"] == "warning" for s in stations_result) else \
                "healthy"

    conclusion_map = {
        "global_failure": "全部站点无数据，疑似 aiflow2 数据平台整体故障或 collector 进程停止。请联系管理员检查 aiflow2 服务和 collector 进程。",
        "partial_failure": "部分站点数据严重停更，可能是对应站点的遥测终端或 aiflow2 数据链路故障。建议排查具体站点设备。",
        "degraded": "部分站点数据略有延迟或少量缺测，系统整体可用但需关注。",
        "healthy": "所有站点数据正常，缓存有效，系统运行正常。",
    }

    return {
        "diagnosis": diagnosis,
        "conclusion": conclusion_map.get(diagnosis, ""),
        "stations": stations_result,
        "checked_at": datetime.now().isoformat(),
    }


class RetryFailedReportsArgs(BaseModel):
    """重试生成失败的日报/周报。"""
    report_type: str = Field(default="daily", description="daily 或 weekly")
    date: str = Field(default="", description="日期 YYYY-MM-DD，空则默认昨天")


def retry_failed_reports(**kwargs) -> dict:
    """重试失败的报告生成。日报默认重试昨天的，周报重试过去一周。"""
    from . import scheduler as _sched
    args = RetryFailedReportsArgs(**kwargs)

    if args.report_type == "daily":
        param = {"date": args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")}
        task_type = "agent_daily_report"
    else:
        param = {}
        task_type = "agent_weekly_report"

    try:
        _safe_sync(_sched._retry(
            lambda: _sched._run_agent_daily_report(param) if task_type == "agent_daily_report"
                   else _sched._run_agent_weekly_report(param),
            f"retry_{task_type}",
            max_retries=1, delay=5
        ))
        return {"success": True, "report_type": args.report_type, "message": f"{args.report_type} 重试成功"}
    except Exception as e:
        return {"success": False, "report_type": args.report_type, "error": str(e), "message": f"重试失败: {e}。建议检查缓存数据是否可用，或联系管理员手动生成。"}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _default_times() -> tuple[str, str]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    return f"{today} 00:00:00.000", f"{today} 23:59:59.999"


def _time_series(raw_data: list, value_key: str, time_key: str = "measureTime") -> list[dict]:
    result = []
    for item in (raw_data or []):
        t = item.get("measureTime")
        if isinstance(t, dict):
            t = f"{t.get('year','')}-{str(t.get('month','')).zfill(2)}-{str(t.get('day','')).zfill(2)} {str(t.get('hours','')).zfill(2)}:{str(t.get('minutes','')).zfill(2)}"
        v = item.get(value_key)
        if t and v is not None:
            result.append({"Time": str(t), "Flow": float(v)})
    return result


# ---------------------------------------------------------------------------
# 工具注册表（供 AgentService 使用）
# ---------------------------------------------------------------------------

TOOLS_REGISTRY = {
    "query_water_level": (QueryWaterLevelArgs, query_water_level),
    "query_flow": (QueryFlowArgs, query_flow),
    "query_latest": (QueryLatestArgs, query_latest),
    "list_stations": (ListStationsArgs, list_stations),
    "compare_stations": (CompareStationsArgs, compare_stations),
    "query_devices": (QueryDevicesArgs, query_devices),
    "query_video_status": (QueryVideoStatusArgs, query_video_status),
    "list_warnings": (ListWarningsArgs, list_warnings),
    "generate_disposal": (GenerateDisposalArgs, generate_disposal),
    "update_warning_standard": (UpdateWarningStandardArgs, update_warning_standard),
    "run_forecast": (RunForecastArgs, run_forecast),
    "analyze_trend": (AnalyzeTrendArgs, analyze_trend),
    "generate_report": (GenerateReportArgs, generate_report),
    "query_reports": (QueryReportsArgs, query_reports),
    "Glob": (GlobArgs, glob_search),
    "Grep": (GrepArgs, grep_search),
    "CreateScheduledTask": (CreateScheduledTaskArgs, create_scheduled_task),
    "ListScheduledTasks": (ListScheduledTasksArgs, list_scheduled_tasks),
    "CancelScheduledTask": (CancelScheduledTaskArgs, cancel_scheduled_task),
    "diagnose_system": (DiagnoseSystemArgs, diagnose_system),
    "retry_failed_reports": (RetryFailedReportsArgs, retry_failed_reports),
}

TOOL_DESCRIPTIONS = {
    "query_water_level":
        "查询指定测站的水位数据（从本地缓存读取，每5分钟刷新一次）。"
        "参数: station_code(必填,如'00106'), begin(可选,开始时间), end(可选,结束时间), count(默认200)。"
        "返回: {code, msg, data:[{measureTime, waterLevel, ...}], pageInfo}。"
        "注意: 数据按上报频率(5min/30min)缓存，并非实时数据。不传 begin/end 则返回全部缓存数据。"
        "快速查看最新状态优先用 query_latest。",

    "query_flow":
        "查询指定测站的流量数据（从本地缓存读取，基于原始上报数据）。"
        "参数: station_code(必填,如'00106'), begin(可选), end(可选), count(默认200)。"
        "返回: {code, msg, data:[{measureTime, virtualFlow, waterFlow, ...}], pageInfo}。"
        "注意: 数据按上报频率缓存，不传 begin/end 返回全部。流量字段为 virtualFlow。",

    "query_latest":
        "查询一个或多个测站最新一条水位数据（从缓存读取）。"
        "参数: station_codes(逗号分隔,如'00106'或'00106,00107',默认'00106')。"
        "返回: {stations: {code: {level: {measureTime, waterLevel, ...}}}, updated}。"
        "这是获取最新水情最直接的方式，无需指定时间范围。",

    "list_stations":
        "列出系统中已接入的所有测站清单,无需参数。"
        "返回: {stations: [{code, name, river}]}。",

    "compare_stations":
        "对多个测站的最新水位或流量数据进行统计对比(最大值/最小值/平均值)。"
        "参数: station_codes(必填,逗号分隔), metric('level'或'flow',默认level)。"
        "返回: {metric, stations: {code: {count, max, min, avg}}}。"
        "注意: 从缓存读取各站全部可用数据做统计，无需指定时间范围。",

    "query_devices":
        "查询指定测站下挂载的设备清单及在线状态。"
        "参数: station_code(必填)。"
        "返回: {station_code, devices: [{device_code, type, status}]}。",

    "query_video_status":
        "查询指定测站的视频监控摄像头状态。"
        "参数: station_code(必填)。"
        "返回: {station_code, cameras: [{id, status, url}]}。",

    "list_warnings":
        "列出当前系统预警信息（从缓存读取最新数据后根据阈值判断）。"
        "参数: station_code(可选,为空则查00106/00107/00108), level(可选,值:blue/yellow/orange/red)。"
        "返回: {warnings: [{id, station_code, level, message, time}], total}。",

    "generate_disposal":
        "针对指定测站和预警级别生成应急处置建议。"
        "参数: station_code(必填), level(预警级别:blue/yellow/orange/red,默认yellow), metric(指标:level水位/flow流量,默认level)。"
        "返回: {station_code, level, metric, suggestions: [措施列表], generated_at}。",

    "update_warning_standard":
        "修改预警标准阈值,修改后立即生效。"
        "参数: category(必填,level水位/flow流量/rate_of_change变化率), level(必填,blue/yellow/orange/red), value(必填,新阈值)。"
        "示例: category='level', level='yellow', value=35.0 表示将黄色水位预警阈值设为35.0m。",

    "run_forecast":
        "基于缓存中的历史流量数据运行 Chronos 时序预测模型。自动从缓存拉数据、预处理（等间隔对齐、空缺值插值）。"
        "参数: station_code(必填), prediction_length(预测步长,默认72), target(默认'Flow')。"
        "返回: {station_code, input_count, preprocess: {interval, raw_count, clean_count, gap_info}, result}。"
        "注意: 无需手动传时间范围，工具自动读取缓存中的全部可用数据。",

    "analyze_trend":
        "对指定测站的水位或流量数据进行线性趋势分析(最小二乘法)。"
        "参数: station_code(必填), metric('level'或'flow',默认level), days(回溯天数,默认7)。"
        "返回: {station_code, metric, count, slope, trend('up'/'down'/'stable'), latest}。",

    "generate_report":
        "调用报告脚本生成水文报告(Word文档),保存到 reports 目录。"
        "参数: report_type('daily'/'weekly'/'monthly',默认daily), station_code(必填), date(可选,格式YYYY-MM-DD,默认昨天)。"
        "返回: {path, filename, size, summary}。",

    "query_reports":
        "列出已生成的所有报告文件,无需参数。"
        "返回: {reports: [{filename, path, size, modified}]}。",

    "Glob":
        "按glob模式搜索文件。"
        "参数: pattern(必填,如'**/*.py'), path(搜索根目录,默认'.')。"
        "返回: {matches: [路径列表], count}。",

    "Grep":
        "按正则表达式搜索文件内容。"
        "参数: pattern(必填,正则表达式), path(搜索根目录,默认'.'), glob(文件过滤,默认'*')。"
        "返回: {matches: [{file, line, text}], count}。",

    "CreateScheduledTask":
        "创建定时任务。"
        "参数: task_type(必填，支持以下类型), cron(必填，如'0 0 * * *'表示每天0点), params(可选)。"
        "agent_daily_report: 采集全站水位/流量/预警数据，LLM整理为完整日报，存为 daily_{date}.txt。"
        "agent_weekly_report: 读取最近7天日报，LLM汇总为周报，存为 weekly_{start}_{end}.txt。"
        "返回: {task_id, task_type, cron}。",

    "ListScheduledTasks":
        "列出所有已创建的定时任务,无需参数。"
        "返回: {tasks: [{task_id, task_type, params, next_run_time, trigger}]}。",

    "CancelScheduledTask":
        "取消指定ID的定时任务。"
        "参数: task_id(必填)。"
        "返回: {success: bool, task_id}。",

    "diagnose_system":
        "全系统诊断：检查 00106/00107/00108 三个站点的缓存状态、数据时效、缺测情况，判断是单站故障还是全局故障。"
        "无需参数。"
        "返回: {diagnosis: global_failure/partial_failure/degraded/healthy, conclusion: 人可读的诊断结论, stations: [{station_code, level_records, flow_records, last_data_time, data_age_hours, recent_nulls, status}]}。",

    "retry_failed_reports":
        "重试生成失败的日报或周报。先调用 diagnose_system 确认缓存数据可用后再重试。"
        "参数: report_type(必填,'daily'或'weekly'), date(可选,日报默认昨天,周报自动计算当周范围)。"
        "返回: {success: bool, report_type, message, error}。"
        "注意: 重试会自动写入 reports 目录，与定时任务使用的同一套生成逻辑。",
}
