import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..config import settings
from . import data_cache, aiflow_client, station_names

logger = logging.getLogger(__name__)

_STATION_CODES = list(station_names.ALL_CODES)
_INTERVAL = settings.collector_interval


def _parse_expire(url: str) -> int:
    """从萤石云直播地址解析 expire 参数为绝对 Unix 时间戳，无法解析返回 0。"""
    if not url or "expire=" not in url:
        return 0
    try:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        return int(qs.get("expire", [0])[0])
    except (ValueError, TypeError):
        return 0


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
        device = station_names.resolve_device_code(code)
        try:
            resp = await asyncio.wait_for(
                aiflow_client.get_flow_original_data(code, device, begin_time, end_time, count=200),
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
            cam = await asyncio.wait_for(aiflow_client.get_camera_info(device), timeout=15)
            if cam.get("code") == 200:
                cam_data = cam.get("data", {}) or {}
                if isinstance(cam_data, list):
                    cam_data = cam_data[0] if cam_data else {}
                if isinstance(cam_data, dict):
                    live_addr = cam_data.get("liveAddress") or cam_data.get("live_address")
                    # 解析萤石云地址的 expire 参数 → 绝对过期时间戳，供读取时过滤已失效快照
                    expire_at = _parse_expire(live_addr)
                    snap = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "station_code": code,
                        "station_name": station_names.station_name(code),
                        "device_code": device,
                        "live_address": live_addr,
                        "expire_at": expire_at,  # 0 表示无法解析（按不过滤处理）
                        "device_name": cam_data.get("deviceName") or cam_data.get("device_name", ""),
                        "status": "online" if live_addr else "offline",
                    }
                    await data_cache.save_video_snapshot(code, snap)
                    logger.info(f"[collector] video snapshot saved for {code}, status={snap['status']}, expire_at={expire_at}")
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
    # 心跳路径与 server.py 看门狗保持一致（gateway/data/）
    # collector.py 在 gateway/services/ 下，需 parent.parent 才到 gateway/
    heartbeat_file = Path(__file__).parent.parent / "data" / "collector_heartbeat.txt"

    async def _collect_with_heartbeat():
        # 先写心跳再采集——防止 collect_all() 耗时长导致看门狗误判杀死进程
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_file.write_text(str(time.time()))
        await collect_all()

    logger.info("[collector] starting background loop")
    try:
        await _collect_with_heartbeat()
    except Exception as e:
        logger.error(f"[collector] initial collection failed: {e}")

    while True:
        await asyncio.sleep(_INTERVAL)
        try:
            await _collect_with_heartbeat()
        except Exception as e:
            logger.error(f"[collector] loop error: {e}")


if __name__ == "__main__":
    # 仅使用 StreamHandler — 服务器 subprocess 已通过 pipe 将 stdout/stderr 重定向到
    # collector.log；此处不能再 FileHandler 同一文件，否则 Windows 文件锁冲突导致 rc=1。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    asyncio.run(run_loop())
