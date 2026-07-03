import logging

logger = logging.getLogger(__name__)
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ...config import settings
from .. import warning_config, station_names
from ._helpers import _safe_sync, _get_cached_records
from ..time_utils import parse_ts
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
    admin = warning_config.get_admin_contact()
    warnings = []
    alerts = []

    for code in codes:
        # ── 获取数据 ──
        records = _safe_sync(_get_cached_records(code)) or []
        level_cached = any(r.get("waterLevel") is not None for r in records)
        flow_cached = any((r.get("virtualFlow") or r.get("waterFlow")) is not None for r in records)

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
        for item in records:
            wl = item.get("waterLevel")
            if wl is not None:
                wl_val = float(wl)
                break
        if wl_val is None:
            for item in records:
                wl = item.get("waterLevel")
                if wl is not None:
                    wl_val = float(wl)
                    break

        if wl_val is not None:
            lv = warning_config.check_level(wl_val, code)
            if lv:
                thresholds = warning_config.get_station_thresholds(code)
                threshold = thresholds["level"].get(lv, 0)
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
                    "message": f"测站 {station_names.station_name(code)} 当前水位 {wl_val:.2f}m，已达到{threshold}m（{warning_config.level_name(lv)}阈值）。距上一级阈值还有{_next_threshold_distance(thresholds['level'], lv, wl_val)}m。请加强监测并做好处置准备。",
                    "time": datetime.now().isoformat(),
                })

        vf_val = None
        for item in records:
            vf = item.get("virtualFlow")
            if vf is not None:
                vf_val = float(vf)
                break
        if vf_val is not None:
            lv = warning_config.check_flow(vf_val, code)
            if lv:
                thresholds = warning_config.get_station_thresholds(code)
                threshold = thresholds["flow"].get(lv, 0)
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
        if records:
            last_measure = parse_ts(records[0].get("measureTime", ""))
            if last_measure:
                hours = (now_ts - last_measure) / 3600
                if hours > 4:
                    alerts.append({
                        "id": f"AL-data_frozen_severe-{code}",
                        "type": "告警", "category": "系统",
                        "name": "数据严重停更",
                        "level": "红色",
                        "station_code": code,
                        "message": f"测站 {station_names.station_name(code)} 数据已超过 {hours:.1f} 小时未更新（最后上报：{records[0].get('measureTime','')}）。该站已处于数据盲区状态。请立即排查遥测终端、aiflow2 数据链路及采集程序。如无法自行排查，请联系管理员（{admin}）。",
                        "time": datetime.now().isoformat(),
                    })
                elif hours > 2:
                    alerts.append({
                        "id": f"AL-data_frozen-{code}",
                        "type": "告警", "category": "系统",
                        "name": "数据长时间未更新",
                        "level": "黄色",
                        "station_code": code,
                        "message": f"测站 {station_names.station_name(code)} 数据已 {hours:.1f} 小时未更新（最后上报：{records[0].get('measureTime','')}）。可能原因：遥测终端通信中断或 aiflow2 接口异常。请检查设备通信状态。如无法自行排查，请联系管理员（{admin}）。",
                        "time": datetime.now().isoformat(),
                    })

        # ── B3 数据缺测检测 ──
        if records:
            null_count = sum(1 for it in records[:10] if it.get("virtualFlow") is None)
            if null_count >= 3:
                alerts.append({
                    "id": f"AL-data_missing-{code}",
                    "type": "告警", "category": "系统",
                    "name": "数据连续缺测",
                    "level": "提示",
                    "station_code": code,
                    "message": f"测站 {code} 最近 10 条数据中有 {null_count} 条流量为空。可能原因：传感器瞬时故障或 AiFlow 测量异常。建议现场检查传感器状态。如持续缺测，请联系管理员（{admin}）。",
                    "time": datetime.now().isoformat(),
                })

        # ── B4 数据异常跳变 ──
        if len(records) >= 2:
            prev = records[0].get("virtualFlow")
            curr = records[1].get("virtualFlow")
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
        "standards": {code: warning_config.get_station_thresholds(code) for code in codes},
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
    """修改全局默认预警阈值或变化率阈值（不区分站点）。如需修改某站专属阈值，使用 update_station_threshold。"""
    args = UpdateWarningStandardArgs(**kwargs)
    return warning_config.update_standard(args.category, args.level, args.value)

# ── 每站阈值查询与修改（v2） ──

class GetStationThresholdsArgs(BaseModel):
    station_code: str = Field(..., description="测站编码，如 00125")

def get_station_thresholds(**kwargs) -> dict:
    """查询指定站点的水位+流量预警阈值。返回该站专属配置，未配置时显示回退默认值。"""
    args = GetStationThresholdsArgs(**kwargs)
    thresholds = warning_config.get_station_thresholds(args.station_code)
    name = station_names.station_name(args.station_code)
    return {
        "station_code": args.station_code,
        "station_name": name,
        "thresholds": thresholds,
        "is_custom": thresholds.get("is_custom", False),
    }

class UpdateStationThresholdArgs(BaseModel):
    station_code: str = Field(..., description="测站编码，如 00230")
    category: str = Field(..., description="类别: level(水位) / flow(流量)")
    level: str = Field(..., description="预警级别: blue / yellow / orange / red")
    value: float = Field(..., description="新的阈值数值，如 130.0")

def update_station_threshold(**kwargs) -> dict:
    """修改指定站点的预警阈值，立即生效并持久化，随后自动重新巡检该站。"""
    args = UpdateStationThresholdArgs(**kwargs)
    warning_config.update_station_threshold(
        args.station_code, args.category, args.level, args.value
    )
    result = {
        "station_code": args.station_code,
        "category": args.category,
        "level": args.level,
        "new_value": args.value,
        "recheck": "ok",
    }
    try:
        from ..monitor_engine import MonitorEngine
        _safe_sync(MonitorEngine.get().recheck_station(args.station_code))
    except Exception as e:
        logger.warning("recheck after threshold update failed for %s: %s", args.station_code, e)
        result["recheck"] = "failed"
        result["recheck_error"] = str(e)
    return result

# ---------------------------------------------------------------------------