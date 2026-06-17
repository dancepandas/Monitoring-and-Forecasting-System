from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from ..auth.middleware import get_current_user
from ..config import settings
from ..services import data_cache, warning_config, station_names

router = APIRouter(prefix="/api/data", tags=["data"])


def _default_times():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    return f"{today} 00:00:00.000", f"{today} 23:59:59.999"


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
    standards = warning_config.get_standards()
    admin = warning_config.get_admin_contact()
    warnings = []
    alerts = []

    for code in codes:
        level_data = await data_cache.get(f"aiflow:level:{code}", max_age=600)
        level_items = (level_data.get("data", []) or []) if level_data else []
        flow_data = await data_cache.get(f"aiflow:flow_raw:{code}:{settings.default_device_code}", max_age=600)
        flow_items = (flow_data.get("data", []) or []) if flow_data else []

        # 缓存告警
        if not level_items and not flow_items:
            alerts.append({
                "id": f"AL-cache-{code}", "type": "告警", "category": "系统",
                "name": "数据缓存异常", "level": "提示", "station_code": code,
                "message": f"测站 {station_names.station_name(code)} 数据缓存为空。可能 aiflow2 连接异常或采集程序未运行。如持续超过 10 分钟，请联系管理员（{admin}）。",
                "time": datetime.now().isoformat(),
            })
        elif not level_items:
            alerts.append({
                "id": f"AL-cache-{code}", "type": "告警", "category": "系统",
                "name": "数据缓存异常", "level": "提示", "station_code": code,
                "message": f"测站 {station_names.station_name(code)} 水位数据缓存为空。请联系管理员（{admin}）。",
                "time": datetime.now().isoformat(),
            })

        # 水位预警
        wl_val = None
        for item in level_items:
            if item.get("waterLevel") is not None:
                wl_val = float(item["waterLevel"]); break
        if wl_val is None:
            for item in flow_items:
                if item.get("waterLevel") is not None:
                    wl_val = float(item["waterLevel"]); break
        if wl_val is not None:
            lv = warning_config.check_level(wl_val, standards)
            if lv:
                warnings.append({
                    "id": f"EW-level-{code}-{lv}", "type": "预警", "category": "水文",
                    "name": "水位超限预警", "level": warning_config.level_name(lv), "station_code": code,
                    "value": round(wl_val, 2), "unit": "m",
                    "message": f"测站 {station_names.station_name(code)} 当前水位 {wl_val:.2f}m，已达到{standards['level'].get(lv, 0)}m（{warning_config.level_name(lv)}阈值）。请加强监测。",
                    "time": datetime.now().isoformat(),
                })

        # 流量预警
        vf_val = None
        for item in flow_items:
            if item.get("virtualFlow") is not None:
                vf_val = float(item["virtualFlow"]); break
        if vf_val is not None:
            lv = warning_config.check_flow(vf_val, standards)
            if lv:
                warnings.append({
                    "id": f"EW-flow-{code}-{lv}", "type": "预警", "category": "水文",
                    "name": "流量超限预警", "level": warning_config.level_name(lv), "station_code": code,
                    "value": round(vf_val, 0), "unit": "m³/s",
                    "message": f"测站 {station_names.station_name(code)} 当前流量 {vf_val:.0f}m³/s，已达到{standards['flow'].get(lv, 0)}m³/s（{warning_config.level_name(lv)}阈值）。请通知航运部门关注。",
                    "time": datetime.now().isoformat(),
                })

    return {
        "warnings": warnings, "warning_count": len(warnings),
        "alerts": alerts, "alert_count": len(alerts),
        "total": len(warnings) + len(alerts),
        "updated": datetime.now().isoformat(),
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
    """聚合各站视频链路状态"""
    codes = [c.strip() for c in station_codes.split(",")]
    feeds = []
    cam_id = 0
    for code in codes:
        data = await data_cache.get(f"aiflow:flow:{code}", max_age=600)
        if not data:
            continue
        items = data.get("data", []) or []
        if items and items[0]:
            item = items[0]
            video_urls = []
            for key in ("videoUrl", "videoUrlSecond", "videoUrlThird"):
                url = item.get(key)
                if url:
                    video_urls.append(url)
            cam_files = item.get("cameraVideoFiles") or []
            for cf in cam_files:
                if cf.get("videoUrl"):
                    video_urls.append(cf["videoUrl"])
            ai_tasks = []
            if item.get("measureResult") is not None:
                ai_tasks.append("流速估计")
            if video_urls:
                ai_tasks.append("漂浮物识别")
            cam_id += 1
            feeds.append({
                "id": f"CAM-{cam_id:02d}",
                "station_code": code,
                "label": f"{code}站",
                "status": "online" if item.get("uploadStatus") == 1 else "offline",
                "ai_tasks": ai_tasks,
                "video_count": len(video_urls),
                "water_level": item.get("waterLevel"),
                "water_flow": item.get("waterFlow"),
            })
    return {"feeds": feeds, "total": len(feeds), "updated": datetime.now().isoformat()}


@router.get("/device-stats")
async def get_device_stats(station_codes: str = settings.station_codes, user: dict = Depends(get_current_user)):
    """设备统计"""
    codes = [c.strip() for c in station_codes.split(",")]
    online = 0
    total = 0
    detail = []
    for code in codes:
        # 优先从 flow_raw 缓存读取（有实际数据），level 缓存做 fallback
        data = await data_cache.get(f"aiflow:flow_raw:{code}:{settings.default_device_code}", max_age=600)
        if data:
            items = data.get("data", []) or []
        else:
            data = await data_cache.get(f"aiflow:level:{code}", max_age=600)
            items = (data.get("data", []) or []) if data else []
        if items and items[0]:
            item = items[0]
            total += 1
            status = "online" if item.get("uploadStatus") in (1, None, 0) else "offline"
            if status == "online":
                online += 1
            detail.append({
                "station_code": code,
                "status": status,
                "water_level": item.get("waterLevel"),
                "device_code": item.get("deviceCode", item.get("waterDeviceCode", "")),
            })
        else:
            detail.append({"station_code": code, "status": "no_data"})
    return {"total": total, "online": online, "offline": total - online, "detail": detail, "updated": datetime.now().isoformat()}


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
