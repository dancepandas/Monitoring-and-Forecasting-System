from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)

from ..auth.middleware import get_current_user
from ..config import settings
from ..services import data_cache, warning_config, station_names, aiflow_client
from ..services.time_utils import default_times

router = APIRouter(prefix="/api/data", tags=["data"])


def _empty(code: str = settings.station_codes.split(",")[0] if settings.station_codes else "00106"):
    return {"code": 200, "msg": "缓存未就绪", "data": [], "stationCode": code}


@router.get("/level")
async def get_level(station_code: str, begin_time: str = "", end_time: str = "", count: int = 200, user: dict = Depends(get_current_user)):
    data = await data_cache.get(f"aiflow:level:{station_code}", max_age=600)
    if data is None:
        return _empty(station_code)
    return data


@router.get("/flow")
async def get_flow(station_code: str, begin_time: str = "", end_time: str = "", count: int = 200, user: dict = Depends(get_current_user)):
    data = await data_cache.get(f"aiflow:flow:{station_code}", max_age=600)
    if data is None:
        return _empty(station_code)
    return data


@router.get("/level-raw")
async def get_level_raw(station_code: str, device_code: str, begin_time: str = "", end_time: str = "", count: int = 200, user: dict = Depends(get_current_user)):
    data = await data_cache.get(f"aiflow:level_raw:{station_code}:{device_code}", max_age=600)
    if data is None:
        return _empty(station_code)
    return data


@router.get("/flow-raw")
async def get_flow_raw(station_code: str, device_code: str, begin_time: str = "", end_time: str = "", count: int = 200, user: dict = Depends(get_current_user)):
    logger.info(f"/api/data/flow-raw called: station={station_code} device={device_code}")
    data = await data_cache.get(f"aiflow:flow_raw:{station_code}:{device_code}", max_age=600)
    if data is None:
        logger.warning(f"/api/data/flow-raw cache miss: station={station_code}")
        return _empty(station_code)
    logger.info(f"/api/data/flow-raw cache hit: station={station_code}")
    return data


@router.get("/latest")
async def get_latest(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    codes = [c.strip() for c in station_codes.split(",")]
    results = {}
    for code in codes:
        data = await data_cache.get(f"aiflow:level:{code}", max_age=600)
        item = None
        if data:
            items = data.get("data", []) or []
            if items:
                item = items[0]
        results[code] = {"level": item}
    return {"stations": results, "updated": datetime.now().isoformat()}


@router.get("/warnings")
async def get_warnings(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    codes = [c.strip() for c in station_codes.split(",")]
    admin = warning_config.get_admin_contact()
    warnings = []
    alerts = []

    # 从 AlertTracker 获取活跃告警（已确认的过滤掉），使用引擎单例的 tracker
    from ..services.monitor_engine import MonitorEngine
    tracker = MonitorEngine.get()._tracker
    tracker_alerts = await tracker.list_active()
    tracker_ids = set()  # 用于去重

    for code in codes:
        # 使用 aligned 层数据，与 monitor_engine 和前端图表保持一致
        aligned = await data_cache.get_aligned(code, max_age=600)
        aligned_records = aligned.get("records", []) if aligned else []

        # 只取实测记录
        measured = [r for r in aligned_records if r.get("waterLevel_source") == "measured" or r.get("virtualFlow_source") == "measured"]

        # 缓存告警：无实测数据才触发
        if not measured:
            alert_id = f"AL-cache-{code}"
            tracker_ids.add(alert_id)
            alerts.append({
                "id": alert_id, "type": "告警", "category": "系统",
                "name": "数据缓存异常", "level": "提示", "station_code": code,
                "message": f"测站 {station_names.station_name(code)} 数据缓存为空。可能 aiflow2 连接异常或采集程序未运行。如持续超过 10 分钟，请联系管理员（{admin}）。",
                "time": datetime.now().isoformat(),
            })

        # 水位预警（取最新实测值）
        wl_val = None
        for r in reversed(aligned_records):
            if r.get("waterLevel_source") == "measured" and r.get("waterLevel") is not None:
                wl_val = float(r["waterLevel"])
                break
        if wl_val is not None:
            lv = warning_config.check_level(wl_val, code)
            if lv:
                thresholds = warning_config.get_station_thresholds(code)
                warnings.append({
                    "id": f"EW-level-{code}-{lv}", "type": "预警", "category": "水文",
                    "name": "水位超限预警", "level": warning_config.level_name(lv), "station_code": code,
                    "value": round(wl_val, 2), "unit": "m",
                    "message": f"测站 {station_names.station_name(code)} 当前水位 {wl_val:.2f}m，已达到{thresholds['level'].get(lv, 0)}m（{warning_config.level_name(lv)}阈值）。请加强监测。",
                    "time": datetime.now().isoformat(),
                })

        # 流量预警（取最新实测值）
        vf_val = None
        for r in reversed(aligned_records):
            if r.get("virtualFlow_source") == "measured" and r.get("virtualFlow") is not None:
                vf_val = float(r["virtualFlow"])
                break
        if vf_val is not None:
            lv = warning_config.check_flow(vf_val, code)
            if lv:
                thresholds = warning_config.get_station_thresholds(code)
                warnings.append({
                    "id": f"EW-flow-{code}-{lv}", "type": "预警", "category": "水文",
                    "name": "流量超限预警", "level": warning_config.level_name(lv), "station_code": code,
                    "value": round(vf_val, 0), "unit": "m³/s",
                    "message": f"测站 {station_names.station_name(code)} 当前流量 {vf_val:.0f}m³/s，已达到{thresholds['flow'].get(lv, 0)}m³/s（{warning_config.level_name(lv)}阈值）。请通知航运部门关注。",
                    "time": datetime.now().isoformat(),
                })

    # 合并 AlertTracker 中的活跃告警（未确认的），去重
    for ta in tracker_alerts:
        if ta.acknowledged:
            continue  # 已确认的告警不展示在预警列表
        if ta.station_code not in codes:
            continue
        alert_id = ta.id
        if alert_id in tracker_ids:
            continue
        tracker_ids.add(alert_id)
        alerts.append({
            "id": alert_id,
            "type": "告警",
            "category": "系统",
            "name": ta.title,
            "level": ta.level,
            "station_code": ta.station_code,
            "message": ta.message,
            "time": datetime.fromtimestamp(ta.triggered_at).isoformat(),
            "notify_count": ta.notify_count,
            "acknowledged": ta.acknowledged,
        })

    return {
        "warnings": warnings, "warning_count": len(warnings),
        "alerts": alerts, "alert_count": len(alerts),
        "total": len(warnings) + len(alerts),
        "updated": datetime.now().isoformat(),
    }


@router.get("/disposal/agent")
async def get_disposal_agent(
    station_code: str,
    level: str = "yellow",
    metric: str = "level",
    wl_value: float = 0,
    vf_value: float = 0,
    user: dict = Depends(get_current_user),
):
    """Agent 动态生成处置建议，基于实时数值而非静态字典。"""
    from ..services.agent_utils import quick_ask

    unit = "m" if metric == "level" else "m³/s"
    value = wl_value if metric == "level" else vf_value
    name = station_names.station_name(station_code)
    thresholds = warning_config.get_station_thresholds(station_code)
    metric_thresholds = thresholds.get(metric, {})

    prompt = f"""你是防汛专家。请为以下情况生成 3-5 条具体的处置建议：

- 测站：{name}（{station_code}）
- 当前{ '水位' if metric == 'level' else '流量' }：{value:.2f} {unit}
- 预警级别：{level}
- 各级阈值：{json.dumps(metric_thresholds, ensure_ascii=False)}

要求：
1. 每行一条建议，以 - 开头
2. 建议应具体可操作，包含时间频率和具体行动
3. 针对当前数值给出针对性建议，不要泛泛而谈
4. 纯文本，不要 markdown 代码块

示例格式：
- 每1小时记录一次水位数据，关注变化趋势
- 通知下游航运部门注意航行安全
- 检查堤防和闸门设备运行状态"""

    system = "你是防汛指挥专家，用中文输出具体可操作的处置建议，每条一行以 - 开头。"
    text = await quick_ask(prompt, system, max_tokens=600)
    if not text:
        # fallback to static disposal
        return await get_disposal(station_code, level, metric, user)
    suggestions = [{"text": s.lstrip("- ").strip(), "color": "var(--river)"}
                   for s in text.strip().split("\n") if s.strip().startswith("-")]
    if not suggestions:
        suggestions = [{"text": s.strip(), "color": "var(--river)"}
                       for s in text.strip().split("\n") if s.strip()]
    return {
        "station_code": station_code,
        "level": level,
        "metric": metric,
        "suggestions": suggestions or [{"text": "保持常规监测，关注水情变化趋势。", "color": "var(--river)"}],
        "generated_at": datetime.now().isoformat(),
        "source": "agent",
    }


@router.get("/disposal")
async def get_disposal(station_code: str, level: str = "yellow", metric: str = "level", user: dict = Depends(get_current_user)):
    dp = {
        ("level", "blue"): ["密切关注水位变化，每4小时记录一次。", "检查遥测终端通信状态。"],
        ("level", "yellow"): ["加强巡查频次，每2小时上报一次水位。", "通知下游单位关注水情变化。", "检查闸门、泵站设备状态。"],
        ("level", "orange"): ["启动防汛应急预案，全员到岗。", "每1小时上报水位、流量数据。", "通知下游单位做好人员转移准备。", "开启泄洪闸门预泄，降低库容。", "安排专人巡查堤防险工险段。"],
        ("level", "red"): ["立即启动一级防汛应急响应。", "组织危险区群众立即转移。", "所有闸门全开泄洪，泵站全力排涝。", "每30分钟上报水情数据。", "请求上级防汛指挥部支援。"],
        ("flow", "blue"): ["关注流量变化趋势，检查上下游水情。"],
        ("flow", "yellow"): ["加密流量监测频次，每1小时记录。", "通知航运部门注意航行安全。"],
        ("flow", "orange"): ["发布航行警告，必要时封航。", "检查堤防承受能力，准备抢险物资。"],
        ("flow", "red"): ["全面封航，所有船只回港避洪。", "启动溃堤应急预案，组织抢险队伍。"],
    }
    suggestions = dp.get((metric, level), ["保持常规监测，关注水情变化趋势。"])
    colors = {"red": "var(--clay)", "orange": "var(--clay)", "yellow": "var(--amber)", "blue": "var(--river)"}
    return {
        "station_code": station_code,
        "level": level,
        "metric": metric,
        "suggestions": [{"text": s, "color": colors.get(level, "var(--river)")} for s in suggestions],
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/video-feeds")
async def get_video_feeds(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    """各站实时视频状态（调 deviceCamera 接口获取播放地址）。"""
    codes = [c.strip() for c in station_codes.split(",")]
    feeds = []
    for code in codes:
        device = station_names.station_device(code) or settings.default_device_code
        try:
            # 先尝试调 deviceCamera 获取真实摄像头列表
            cam_resp = await aiflow_client.get_camera_info(device)
            cameras = cam_resp.get("data", []) or []
        except Exception:
            cameras = []

        if cameras:
            for i, cam in enumerate(cameras):
                cam_id = cam.get("cameraId", i + 1)
                live_addr = cam.get("liveAddress") or ""  # None → ""，让前端跳过空地址
                feeds.append({
                    "id": f"CAM-{cam_id}",
                    "station_code": code,
                    "label": f"{station_names.station_name(code)} · {cam.get('name', '摄像头')}",
                    "status": "online" if cam.get("programState") == 1 and live_addr else "offline",
                    "ai_tasks": ["监测画面"],
                    "live_address": live_addr,
                    "camera_index": cam.get("cameraIndex"),
                })
        else:
            # 回退：从缓存读（可能有 videoUrl）
            data = await data_cache.get(f"aiflow:flow_raw:{code}:{device}", max_age=600)
            if data:
                items = data.get("data", []) or []
                for i, item in enumerate(items[:3]):
                    vu = item.get("videoUrl")
                    if vu:
                        feeds.append({
                            "id": f"CAM-{i + 1:02d}",
                            "station_code": code,
                            "label": station_names.station_name(code),
                            "status": "online",
                            "ai_tasks": ["监测画面"],
                            "live_address": str(vu),
                        })
                    if len(feeds) >= 3:
                        break

    return {"feeds": feeds, "total": len(feeds), "updated": datetime.now().isoformat()}


@router.get("/video-snapshots")
async def get_video_snapshots(
    station_code: str = Query("00106"),
    limit: int = Query(10, ge=1, le=10),
    user: dict = Depends(get_current_user),
):
    """视频快照历史。station_code=__all__ 时返回所有站点分组。"""
    if station_code == "__all__":
        grouped = await data_cache.get_all_video_snapshots(limit=limit)
        allowed = set(s.strip() for s in settings.station_codes.split(","))
        stations = []
        for code, snaps in grouped.items():
            if code not in allowed:
                continue
            name = station_names.station_name(code)
            stations.append({
                "station_code": code,
                "station_name": name,
                "snapshots": snaps,
                "count": len(snaps),
            })
        stations.sort(key=lambda s: s["station_name"])
        return {"stations": stations, "total_stations": len(stations), "total_snapshots": sum(s["count"] for s in stations)}

    snaps = await data_cache.get_video_snapshots(station_code, limit=limit)
    return {"snapshots": snaps, "total": len(snaps), "station_code": station_code}


@router.get("/device-stats")
async def get_device_stats(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    """设备统计（RTU 在线 + 摄像头 + 采集器心跳）。逻辑见 station_collector.collect_device_stats。"""
    from ..services.station_collector import collect_device_stats
    return await collect_device_stats()


@router.get("/aligned/chart")
async def get_aligned_chart(
    station_code: str = settings.station_codes.split(",")[0] if settings.station_codes else "00106",
    field: str = "virtualFlow",
    user: dict = Depends(get_current_user),
):
    """返回等间隔 + Chronos 填充后的图表数据，带 source/fill 标记。"""
    return await data_cache.get_aligned_chart(station_code, field)


@router.get("/stats")
async def get_stats(
    station_code: str = settings.station_codes.split(",")[0] if settings.station_codes else "00106",
    field: str = "virtualFlow",
    user: dict = Depends(get_current_user),
):
    """返回指定字段的统计信息（仅实测值）。"""
    return await data_cache.get_stats(station_code, field)


@router.get("/warning-standards")
async def get_warning_standards(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    """返回各站预警阈值配置（用于管理页面展示）。"""
    codes = [c.strip() for c in station_codes.split(",")]
    cfg = warning_config.get_standards()
    stations_thresholds = {}
    for code in codes:
        t = warning_config.get_station_thresholds(code)
        stations_thresholds[code] = {
            "name": station_names.station_name(code),
            "level": t.get("level", {}),
            "flow": t.get("flow", {}),
        }
    return {
        "stations": stations_thresholds,
        "defaults": cfg.get("_defaults", {}),
        "rate_of_change": cfg.get("rate_of_change", {}),
        "updated": datetime.now().isoformat(),
    }
