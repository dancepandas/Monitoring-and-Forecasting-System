import logging

logger = logging.getLogger(__name__)
from datetime import datetime

from pydantic import BaseModel, Field

from ...config import settings
from .. import aiflow_client
from .. import station_names
from ._helpers import _safe_sync, _get_cached_records, _filter_by_time, _DEVICE_CODE
from ..time_utils import default_times
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
    b, e = (args.begin, args.end) if args.begin else default_times()
    records = _safe_sync(_get_cached_records(args.station_code))
    filtered = _filter_by_time(records, b, e, args.count)
    return {"code": 200, "msg": "ok", "data": filtered, "pageInfo": {"current": 1, "pages": 1, "size": len(filtered), "total": len(filtered)}}

class QueryFlowArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    begin: str = Field(default="", description="开始时间")
    end: str = Field(default="", description="结束时间")
    count: int = Field(default=200, description="返回条数")

def query_flow(**kwargs) -> dict:
    args = QueryFlowArgs(**kwargs)
    b, e = (args.begin, args.end) if args.begin else default_times()
    records = _safe_sync(_get_cached_records(args.station_code))
    filtered = _filter_by_time(records, b, e, args.count)
    return {"code": 200, "msg": "ok", "data": filtered, "pageInfo": {"current": 1, "pages": 1, "size": len(filtered), "total": len(filtered)}}

class QueryLatestArgs(BaseModel):
    station_codes: str = Field(default=settings.station_codes.split(",")[0] if settings.station_codes else "00106", description="逗号分隔的测站编码")

def query_latest(**kwargs) -> dict:
    args = QueryLatestArgs(**kwargs)
    codes = [c.strip() for c in args.station_codes.split(",")]
    results = {}
    for code in codes:
        try:
            records = _safe_sync(_get_cached_records(code))
            if not records:
                results[code] = {"level": None}
                continue
            # 与前端 OverviewPage 行为一致：取第一条 virtualFlow 非空的记录
            # （水位用同一条记录的，确保水位和流量是同一时刻）
            latest = next((r for r in records if r.get("virtualFlow") is not None), records[0])
            results[code] = {"level": latest}
        except Exception as ex:
            logger.warning(f"query_latest failed for {code}: {ex}")
            results[code] = {"level": None}
    return {"stations": results, "updated": datetime.now().isoformat()}

class ListStationsArgs(BaseModel):
    pass

def list_stations(**kwargs) -> dict:
    ListStationsArgs(**kwargs)
    stations = []
    for code, info in station_names.STATIONS.items():
        stations.append({"code": code, "name": info["name"], "river": "汉江"})
    return {"stations": stations}

class CompareStationsArgs(BaseModel):
    station_codes: str = Field(..., description="逗号分隔的测站编码")
    metric: str = Field(default="level", description="对比指标：level / flow")
    begin: str = Field(default="", description="开始时间")
    end: str = Field(default="", description="结束时间")

def compare_stations(**kwargs) -> dict:
    args = CompareStationsArgs(**kwargs)
    codes = [c.strip() for c in args.station_codes.split(",")]
    b, e = (args.begin, args.end) if args.begin else default_times()
    results = {}
    for code in codes:
        try:
            if args.metric == "flow":
                records = _safe_sync(_get_cached_records(code))
                key = "virtualFlow"
            else:
                records = _safe_sync(_get_cached_records(code))
                key = "waterLevel"
            items = _filter_by_time(records, b, e, 200)
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
    # 从缓存读最新设备状态
    items = _safe_sync(_get_cached_records(args.station_code, max_age=600))
    device_state = "unknown"
    device_code = station_names.resolve_device_code(args.station_code)
    if items:
        device_code = items[0].get("deviceCode") or device_code
        ps = items[0].get("programState")
        if ps == 1:
            device_state = "online"
        elif ps == 0:
            device_state = "offline"

    return {
        "station_code": args.station_code,
        "devices": [
            {"device_code": device_code, "type": "遥测终端(RTU)", "status": device_state},
            {"device_code": f"{args.station_code}_WL", "type": "水位计", "status": "online" if items else "unknown"},
            {"device_code": f"{args.station_code}_FL", "type": "AiFlow 流量计", "status": "online" if items else "unknown"},
        ]
    }

class QueryVideoStatusArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")

def query_video_status(**kwargs) -> dict:
    args = QueryVideoStatusArgs(**kwargs)
    device = station_names.resolve_device_code(args.station_code)
    try:
        resp = _safe_sync(aiflow_client.get_camera_info(device))
        cameras = resp.get("data", []) or []
        return {
            "station_code": args.station_code,
            "device_code": device,
            "cameras": [
                {
                    "cameraId": c.get("cameraId"),
                    "name": c.get("name", ""),
                    "liveAddress": c.get("liveAddress", ""),
                    "programState": c.get("programState", 0),
                    "stateText": {0: "离线", 1: "在线", 2: "未知"}.get(c.get("programState"), "未知"),
                }
                for c in cameras
            ],
        }
    except Exception as e:
        logger.warning(f"query_video_status failed: {e}")
        return {"station_code": args.station_code, "cameras": [], "error": str(e)}

