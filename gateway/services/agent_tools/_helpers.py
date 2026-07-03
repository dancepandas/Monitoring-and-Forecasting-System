import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime


from ...config import settings
from .. import data_cache

logger = logging.getLogger(__name__)

_DEVICE_CODE = settings.default_device_code
_sync_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-tool")


def _safe_sync(coro):
    """安全地在同步/异步混合环境中运行协程。"""
    import threading
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已有运行中的事件循环，调度到该 loop 执行并等待结果
    # 防护：如果在事件循环所在线程调用会死锁
    if threading.current_thread() is threading.main_thread():
        raise RuntimeError(
            "_safe_sync called from event loop thread (main thread) — would deadlock. "
            "Use 'await coro' directly instead."
        )
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)

async def _get_cached_records(station_code: str, max_age: int = 600) -> list[dict]:
    """从 flow_raw 缓存读取记录列表（统一数据源为 realTimeInfo）。

    返回扁平化的记录列表，每条含 measureTime/waterLevel/virtualFlow/waterVelocity/videoUrl 等字段。
    数据为空时返回空列表。
    """
    data = await data_cache.get(f"aiflow:flow_raw:{station_code}:{_DEVICE_CODE}", max_age=max_age)
    if not data:
        return []
    raw_items = data.get("data", []) or []
    mapped = []
    for it in raw_items:
        mapped.append({
            "measureTime": it.get("time") or it.get("measureTime"),
            "waterLevel": it.get("waterLevel"),
            "virtualFlow": it.get("virtualFlow") or it.get("waterFlow"),
            "waterVelocity": it.get("waterVelocity"),
            "videoUrl": it.get("videoUrl"),
            "deviceCode": it.get("deviceCode", _DEVICE_CODE),
            "programState": it.get("programState"),
            "stationCode": station_code,
        })
    return mapped


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
