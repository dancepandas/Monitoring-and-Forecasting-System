import logging
import json
import time
import socket
import requests
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from ..config import settings

logger = logging.getLogger(__name__)
_token = None
_token_lock = threading.Lock()

AIFLOW_CONNECT_TIMEOUT = 5
AIFLOW_READ_TIMEOUT = 10
CACHE_TTL = 300  # 5 minutes

_cache = {}
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="aiflow")
_session = requests.Session()


def _cache_key(endpoint: str, json_data: dict) -> str:
    return f"{endpoint}:{json.dumps(json_data, sort_keys=True, ensure_ascii=False)}"


def _get_cached(key: str):
    now = time.time()
    entry = _cache.get(key)
    if entry and now - entry["ts"] < CACHE_TTL:
        logger.info(f"aiflow2 cache hit: {key[:120]}")
        return entry["data"]
    return None


def _set_cached(key: str, data: dict):
    _cache[key] = {"ts": time.time(), "data": data}


def _sync_post(url: str, json_data: dict, headers: dict = None) -> dict:
    """同步 HTTP POST，在线程池里跑，不阻塞事件循环。"""
    logger.info(f"aiflow2 sync request: POST {url}")
    try:
        r = _session.post(
            url,
            json=json_data,
            headers=headers,
            timeout=(AIFLOW_CONNECT_TIMEOUT, AIFLOW_READ_TIMEOUT),
        )
        data = r.json()
        logger.info(f"aiflow2 sync response: POST {url} status={r.status_code} code={data.get('code')}")
        return data
    except requests.exceptions.Timeout:
        logger.error(f"aiflow2 sync timeout: POST {url}")
        raise
    except requests.exceptions.ConnectionError as e:
        logger.error(f"aiflow2 sync connection error: POST {url} - {e}")
        raise
    except Exception as e:
        logger.error(f"aiflow2 sync error: POST {url} - {type(e).__name__}: {e}")
        raise


def _sync_get_token() -> str:
    global _token
    with _token_lock:
        if _token:
            return _token
        url = f"{settings.aiflow_base_url}/loginNoVerify"
        data = _sync_post(url, {"username": settings.aiflow_username, "password": settings.aiflow_password})
        if data.get("code") == 200:
            _token = data["token"]
            logger.info("aiflow2 token acquired")
            return _token
        raise Exception(f"aiflow2 auth failed: {data}")


def _sync_proxy_post(endpoint: str, json_data: dict) -> dict:
    token = _sync_get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{settings.aiflow_base_url}{endpoint}"
    try:
        return _sync_post(url, json_data, headers)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            global _token
            _token = None
            token = _sync_get_token()
            headers["Authorization"] = f"Bearer {token}"
            return _sync_post(url, json_data, headers)
        raise


async def proxy_post(endpoint: str, json_data: dict) -> dict:
    key = _cache_key(endpoint, json_data)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(_executor, partial(_sync_proxy_post, endpoint, json_data))
        _set_cached(key, data)
        return data
    except requests.exceptions.Timeout:
        logger.error(f"aiflow2 timeout: POST {endpoint}")
        raise Exception(f"aiflow2 timeout: POST {endpoint}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"aiflow2 connection error: POST {endpoint} - {e}")
        raise Exception(f"aiflow2 connection error: POST {endpoint}")
    except Exception as e:
        logger.error(f"aiflow2 error: POST {endpoint} - {type(e).__name__}: {e}")
        raise


async def get_level(station_code: str, begin: str, end: str, count: int = 200) -> dict:
    return await proxy_post("/level/reportDataPage", {
        "count": count, "page": 1,
        "request": {"stationCode": station_code, "beginTime": begin, "endTime": end, "isMedia": 1}
    })


async def get_flow(station_code: str, begin: str, end: str, count: int = 200) -> dict:
    return await proxy_post("/flow/reportDataPage", {
        "count": count, "page": 1,
        "request": {"stationCode": station_code, "beginTime": begin, "endTime": end, "isMedia": 1}
    })


async def get_level_raw(station_code: str, device_code: str, begin: str, end: str, count: int = 200) -> dict:
    return await proxy_post("/level/originalDataFilterPage", {
        "count": count, "page": 1,
        "request": {"stationCode": station_code, "deviceCode": device_code, "beginTime": begin, "endTime": end}
    })


async def get_flow_raw(station_code: str, device_code: str, begin: str, end: str, count: int = 200) -> dict:
    return await proxy_post("/flow/originalDataFilterPage", {
        "count": count, "page": 1,
        "request": {"stationCode": station_code, "deviceCode": device_code, "beginTime": begin, "endTime": end}
    })
