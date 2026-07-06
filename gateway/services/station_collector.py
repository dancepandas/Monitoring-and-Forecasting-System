"""共享站点数据采集 —— generate_report 和 scheduler 共用。

从缓存读取各站水位/流量数据并解析为数值序列。
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from ..config import settings
from . import data_cache, station_names

logger = logging.getLogger(__name__)

# 采集器心跳文件（collector.py 写入 gateway/data/collector_heartbeat.txt）
_HEARTBEAT_FILE = Path(__file__).parent.parent / "data" / "collector_heartbeat.txt"




def _parse_wl_values(level_data, flow_data):
    """提取有效水位数值列表（level 优先，flow_raw 作为 fallback）。"""
    wl_values = []
    level_items = (level_data.get("data", []) or []) if level_data else []
    for item in level_items:
        wl = item.get("waterLevel")
        if wl is not None:
            try:
                wl_values.append(float(wl))
            except (ValueError, TypeError):
                pass
    if not wl_values:
        flow_items = (flow_data.get("data", []) or []) if flow_data else []
        for item in flow_items:
            wl = item.get("waterLevel")
            if wl is not None:
                try:
                    wl_values.append(float(wl))
                except (ValueError, TypeError):
                    pass
    return wl_values


def _parse_flow_values(flow_data):
    """提取有效流量数值列表。"""
    flow_values = []
    flow_items = (flow_data.get("data", []) or []) if flow_data else []
    for item in flow_items:
        vf = item.get("virtualFlow")
        if vf is not None:
            try:
                flow_values.append(round(float(vf), 2))
            except (ValueError, TypeError):
                pass
    return flow_values


async def collect_station_data(code: str):
    """采集单个站点的缓存数据并解析为数值序列。

    返回: dict with code, name, device, level_items, flow_items, wl_vals, flow_vals
    """
    device = station_names.resolve_device_code(code)
    level_data = await data_cache.get(f"aiflow:level:{code}", max_age=600)
    flow_data = await data_cache.get(f"aiflow:flow_raw:{code}:{device}", max_age=600)
    level_items = (level_data.get("data", []) or []) if level_data else []
    flow_items = (flow_data.get("data", []) or []) if flow_data else []
    wl_vals = _parse_wl_values(level_data, flow_data)
    flow_vals = _parse_flow_values(flow_data)

    return {
        "code": code,
        "name": station_names.station_name(code),
        "device": device,
        "level_items": level_items,
        "flow_items": flow_items,
        "wl_vals": wl_vals,
        "flow_vals": flow_vals,
    }


async def collect_all_stations():
    """采集全部站点的数据。

    返回: list[dict]，每项为 collect_station_data 的返回值。
    """
    codes = [s.strip() for s in settings.station_codes.split(",") if s.strip()]
    results = []
    for code in codes:
        try:
            results.append(await collect_station_data(code))
        except Exception as e:
            logger.warning(f"collect_station_data failed for {code}: {e}")
    return results


async def collect_device_stats() -> dict:
    """聚合各站 RTU/水位计/流量计/摄像头状态 + 采集器心跳健康。

    供「设备在线率日报」与 /api/data/device-stats 路由共用（去重）。
    返回: {total, online, offline, detail[], collector_healthy, collector_heartbeat_age_s, updated}
    detail 每项: {station_code, station_name, status, rtu, flow_meter, camera, water_level, device_code}
    """
    codes = [s.strip() for s in settings.station_codes.split(",") if s.strip()]
    # 各站最新一条视频快照（已自动过滤 liveAddress 过期）
    cam_snaps = await data_cache.get_all_video_snapshots(limit=1)

    detail = []
    online = 0
    total = 0
    for code in codes:
        device = station_names.resolve_device_code(code)
        data = await data_cache.get(f"aiflow:flow_raw:{code}:{device}", max_age=600)
        if not data:
            data = await data_cache.get(f"aiflow:level:{code}", max_age=600)
        items = (data.get("data", []) or []) if data else []

        cam_list = cam_snaps.get(code) or []
        cam_status = cam_list[0].get("status", "unknown") if cam_list else "unknown"

        if items and items[0]:
            item = items[0]
            total += 1
            rtu_online = item.get("uploadStatus") == 1
            if rtu_online:
                online += 1
            status = "online" if rtu_online else "offline"
            detail.append({
                "station_code": code,
                "station_name": station_names.station_name(code),
                "status": status,
                "rtu": status,
                "flow_meter": "online" if items else "unknown",
                "camera": cam_status,
                "water_level": item.get("waterLevel"),
                "device_code": item.get("deviceCode", item.get("waterDeviceCode", "")),
            })
        else:
            detail.append({
                "station_code": code,
                "station_name": station_names.station_name(code),
                "status": "no_data",
                "rtu": "no_data",
                "flow_meter": "unknown",
                "camera": cam_status,
                "water_level": None,
                "device_code": "",
            })

    # 采集器心跳：>10 分钟未更新视为不健康
    collector_healthy = False
    hb_age_s = None
    try:
        if _HEARTBEAT_FILE.exists():
            hb_age_s = time.time() - float(_HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
            collector_healthy = hb_age_s < 600
    except Exception as e:
        logger.warning(f"read collector heartbeat failed: {e}")

    return {
        "total": total,
        "online": online,
        "offline": total - online,
        "detail": detail,
        "collector_healthy": collector_healthy,
        "collector_heartbeat_age_s": round(hb_age_s, 1) if hb_age_s is not None else None,
        "updated": datetime.now().isoformat(),
    }
