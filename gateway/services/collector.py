import asyncio
import logging
from pathlib import Path

from ..config import settings
from . import data_cache, aiflow_client

logger = logging.getLogger(__name__)

_STATION_CODES = [s.strip() for s in settings.station_codes.split(",")]
_DEVICE_CODE = settings.default_device_code
_INTERVAL = settings.collector_interval


def _today_range():
    from datetime import datetime
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    return f"{today} 00:00:00.000", f"{today} 23:59:59.999"


async def collect_all():
    b, e = _today_range()

    for code in _STATION_CODES:
        tasks = [
            ("flow_raw", aiflow_client.get_flow_raw(code, _DEVICE_CODE, b, e, 200)),
            ("level", aiflow_client.get_level(code, b, e, 1)),
            ("flow", aiflow_client.get_flow(code, b, e, 1)),
        ]
        for dtype, coro in tasks:
            try:
                data = await asyncio.wait_for(coro, timeout=20)
                await data_cache.merge_raw(code, dtype, data)
                logger.info(f"[collector] {dtype}:{code} merged")
            except Exception as exc:
                logger.warning(f"[collector] {dtype}:{code} failed: {type(exc).__name__}: {exc}")
            await asyncio.sleep(0.2)

    # 重建 aligned（仅对有 flow_raw 数据的站点）
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
