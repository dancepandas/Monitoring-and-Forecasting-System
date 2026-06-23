import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from ..config import settings
from . import data_cache, aiflow_client

logger = logging.getLogger(__name__)

_STATION_CODES = [s.strip() for s in settings.station_codes.split(",")]
_DEVICE_CODE = settings.default_device_code
_INTERVAL = settings.collector_interval


def _extract_flow_records(api_response: dict) -> list:
    """从时序库 flow/originalDataFilterPage 响应中提取记录列表。"""
    if not api_response:
        return []
    data = api_response.get("data", []) or []
    if not isinstance(data, list):
        return []
    return data


async def collect_all():
    """每轮采集：从时序库拉取流量原始数据（含水位/流速/视频），追加到本地缓存。"""

    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")
    # 从 raw 缓存获取上次最后一条记录时间，避免固定窗口漏数据
    begin_time = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S.000")
    try:
        for code in _STATION_CODES:
            raw = await data_cache.get_raw(code, "flow_raw", max_age=99999)
            if raw and raw.get("data"):
                records = raw.get("data", [])
                if records:
                    last_time = records[0].get("time", "")
                    if last_time:
                        # 从上一次最后记录时间开始（留 1 分钟余量）
                        try:
                            dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                            begin_time = (dt - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S.000")
                        except ValueError:
                            pass
                    break  # 任一站点有数据即确定窗口
    except Exception:
        pass

    for code in _STATION_CODES:
        try:
            resp = await asyncio.wait_for(
                aiflow_client.get_flow_original_data(code, _DEVICE_CODE, begin_time, end_time, count=200),
                timeout=30,
            )
            records = _extract_flow_records(resp)
            if records:
                await data_cache.merge_raw(code, "flow_raw", {"data": records})
                latest = records[0]
                logger.info(
                    f"[collector] flow_raw:{code} merged {len(records)} records — "
                    f"WL={latest.get('waterLevel')}, Flow={latest.get('waterFlow')}, "
                    f"Vel={latest.get('waterVelocity')}"
                )
            else:
                logger.warning(f"[collector] flow_raw:{code} empty (no records)")
        except Exception as exc:
            logger.warning(f"[collector] flow_raw:{code} failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(0.2)

        # ── 视频快照采集 ──
        try:
            cam = await asyncio.wait_for(aiflow_client.get_camera_info(_DEVICE_CODE), timeout=15)
            if cam.get("code") == 200:
                cam_data = cam.get("data", {}) or {}
                if isinstance(cam_data, list):
                    cam_data = cam_data[0] if cam_data else {}
                if isinstance(cam_data, dict):
                    snap = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "station_code": code,
                        "device_code": _DEVICE_CODE,
                        "live_address": cam_data.get("liveAddress") or cam_data.get("live_address"),
                        "device_name": cam_data.get("deviceName") or cam_data.get("device_name", ""),
                        "status": "online" if (cam_data.get("liveAddress") or cam_data.get("live_address")) else "offline",
                    }
                    await data_cache.save_video_snapshot(code, snap)
                    logger.info(f"[collector] video snapshot saved for {code}, status={snap['status']}")
        except Exception as exc:
            logger.warning(f"[collector] video snapshot {code} failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(0.2)

    # 重建 aligned
    for code in _STATION_CODES:
        raw = await data_cache.get_raw(code, "flow_raw", max_age=99999)
        if raw and raw.get("data"):
            try:
                await data_cache.rebuild_aligned(code)
                logger.info(f"[collector] aligned rebuilt for {code}")
            except Exception as exc:
                logger.error(f"[collector] aligned rebuild failed for {code}: {exc}")

    logger.info("[collector] round done")


async def run_loop():
    logger.info("[collector] starting background loop")
    try:
        await collect_all()
    except Exception as e:
        logger.error(f"[collector] initial collection failed: {e}")

    while True:
        await asyncio.sleep(_INTERVAL)
        try:
            await collect_all()
        except Exception as e:
            logger.error(f"[collector] loop error: {e}")


if __name__ == "__main__":
    log_path = Path(__file__).parent.parent / "data" / "collector.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    asyncio.run(run_loop())
