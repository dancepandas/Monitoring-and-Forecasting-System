"""
统一缓存数据模型 — 三层架构:

1. raw 层: 从 aiflow2 采集的原始数据，按 time 去重，FIFO
2. aligned 层: 等间隔时间网格 + Chronos 预报填充空缺
3. forecast 层: 最近一次预报结果缓存

规则:
- 实测值永不被覆盖
- 空缺位置只用 Chronos 预报填充（不用线性插值/keep_last）
- 流量插补可用水位做协变量，水位插补可用流量做协变量
"""

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "hydro_cache.json"

_lock = asyncio.Lock()

_DEFAULT_MAX_RAW = settings.cache_max_raw
_DEFAULT_MAX_ALIGNED = settings.cache_max_aligned
_MAX_FILL_LENGTH = settings.aligned_fill_max
_MAX_CONTEXT = settings.aligned_context_max
_DEVICE_CODE = settings.default_device_code


# ── 内部读写 ──

def _load_full() -> dict:
    if not CACHE_FILE.exists():
        return {"meta": {"version": "3.0"}, "raw": {}, "aligned": {}, "forecast": {}}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("raw", {})
        data.setdefault("aligned", {})
        data.setdefault("forecast", {})
        return data
    except Exception as e:
        logger.warning(f"Cache load failed: {e}")
        return {"meta": {"version": "3.0"}, "raw": {}, "aligned": {}, "forecast": {}}


def _save_full(data: dict) -> None:
    try:
        data.setdefault("meta", {"version": "3.0"})
        data["meta"]["updated_at"] = time.time()
        tmp = CACHE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        tmp.replace(CACHE_FILE)
    except Exception as e:
        logger.warning(f"Cache save failed: {e}")


def _ensure_raw(data: dict, station: str, dtype: str) -> dict:
    data.setdefault("raw", {})
    data["raw"].setdefault(station, {})
    if dtype not in data["raw"][station]:
        data["raw"][station][dtype] = {
            "records": [],
            "updated_at": 0,
            "fetch_status": "init",
            "gaps": [],
            "record_count": 0,
            "config": {"max_records": _DEFAULT_MAX_RAW},
        }
    return data["raw"][station][dtype]


def _ensure_aligned(data: dict, station: str) -> dict:
    data.setdefault("aligned", {})
    if station not in data["aligned"]:
        data["aligned"][station] = {
            "records": [],
            "updated_at": 0,
            "grid": {},
            "stats": {},
            "config": {"max_records": _DEFAULT_MAX_ALIGNED},
        }
    return data["aligned"][station]


# ── merge_raw ──

def _parse_time(t) -> Optional[str]:
    """将各种时间格式统一为字符串 'YYYY-MM-DD HH:MM:SS'"""
    if not t:
        return None
    if isinstance(t, dict):
        try:
            return f"{t.get('year',2000)}-{str(t.get('month',1)).zfill(2)}-{str(t.get('day',1)).zfill(2)} {str(t.get('hours',0)).zfill(2)}:{str(t.get('minutes',0)).zfill(2)}:{str(t.get('seconds',0)).zfill(2)}"
        except Exception:
            return None
    s = str(t).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


async def merge_raw(station_code: str, data_type: str, api_response: dict) -> dict:
    """
    将 aiflow2 API 返回的数据合并到 raw 层。
    空数据不覆盖已有 records，只记录 gap。
    """
    async with _lock:
        data = _load_full()
        entry = _ensure_raw(data, station_code, data_type)
        max_records = entry["config"].get("max_records", _DEFAULT_MAX_RAW)

        items = api_response.get("data", []) or []
        has_data = any(it.get("virtualFlow") is not None or it.get("waterLevel") is not None for it in items)

        if not has_data:
            # 空数据：不覆盖 records
            if entry["records"] and entry["fetch_status"] != "empty":
                last_time = entry["records"][0].get("time", "")
                entry.setdefault("gaps", []).append({
                    "start": last_time,
                    "end": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "logged_at": time.time(),
                })
                entry["gaps"] = entry["gaps"][-20:]  # 保留最近 20 个 gap
            entry["updated_at"] = time.time()
            entry["fetch_status"] = "empty"
            _save_full(data)
            return entry

        # 有数据：合并去重
        incoming = []
        for it in items:
            t = _parse_time(it.get("measureTime"))
            if not t:
                continue
            rec = {"time": t}
            for field in ("waterLevel", "virtualFlow", "waterFlow", "sectionArea", "waterWidth",
                         "surfaceAverageVelocity", "conversionFlow", "conversionVelocity",
                         "predictFlow", "predictVelocity", "originalValueProp", "waterDeviceCode",
                         "uploadStatus", "waterLevelType", "dataType"):
                val = it.get(field)
                try:
                    rec[field] = round(float(val), 2) if val not in (None, "") else None
                except (ValueError, TypeError):
                    rec[field] = None
                rec[f"{field}_source"] = "measured" if rec[field] is not None else "unknown"
            incoming.append(rec)

        # 按 time 去重合并
        merged = {}
        for r in entry["records"]:
            t = r.get("time", "")
            if t:
                merged[t] = r
        for r in incoming:
            t = r.get("time", "")
            if t:
                merged[t] = r  # 新值覆盖

        sorted_records = sorted(merged.values(), key=lambda x: x.get("time", ""), reverse=True)
        entry["records"] = sorted_records[:max_records]
        entry["record_count"] = len(entry["records"])
        entry["updated_at"] = time.time()
        entry["fetch_status"] = "ok"
        _save_full(data)
        return entry


# ── rebuild_aligned ──

def _parse_dt(t: str) -> Optional[datetime]:
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def _detect_interval(records: list) -> int:
    """检测主导时间间隔（分钟），默认 5 分钟。"""
    if len(records) < 2:
        return 5
    times = []
    for r in records:
        dt = _parse_dt(r.get("time", ""))
        if dt:
            times.append(dt)
    times.sort()
    diffs = []
    for i in range(1, len(times)):
        d = (times[i] - times[i - 1]).total_seconds() / 60
        if 1 <= d <= 120:
            diffs.append(round(d))
    if not diffs:
        return 5
    return Counter(diffs).most_common(1)[0][0]


def _compute_stats(records: list) -> dict:
    """计算各字段的实测值统计。"""
    fields = {}
    for r in records:
        for key, val in r.items():
            if key.startswith("_") or key.endswith("_source") or key.endswith("_fill") or key == "time":
                continue
            if r.get(f"{key}_source") == "measured" and isinstance(val, (int, float)):
                fields.setdefault(key, []).append(val)
    stats = {}
    for f, vals in fields.items():
        stats[f] = {
            "measured_points": len(vals),
            "filled_points": sum(1 for r in records if r.get(f"{f}_source") == "forecast"),
            "max": round(max(vals), 2) if vals else None,
            "min": round(min(vals), 2) if vals else None,
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
        }
    return stats


async def _chronos_fill(context_series: list[dict], gap_length: int, target: str,
                        covariates: list[str] = None) -> list[float]:
    """用 Chronos 预报填充空缺。返回 float 列表，长度 = gap_length。"""
    try:
        from . import chronos_client
        mode = "multivariate" if covariates else "univariate"
        series = context_series[-_MAX_CONTEXT:]
        result = await chronos_client.predict_flow(
            series, prediction_length=gap_length, target=target,
            context_length=min(len(series), _MAX_CONTEXT), mode=mode,
        )
        if "error" in result:
            logger.warning(f"Chronos fill failed: {result['error']}, falling back to context avg")
            vals = [float(s[target]) for s in series if s.get(target) is not None]
            avg = sum(vals) / len(vals) if vals else 0
            return [avg] * gap_length
        preds = result.get("predictions", result.get("forecast", result.get("series", [])))
        return [float(p) for p in preds[:gap_length]]
    except Exception as e:
        logger.warning(f"Chronos fill error: {e}")
        vals = [float(s[target]) for s in context_series if s.get(target) is not None]
        avg = sum(vals) / len(vals) if vals else 0
        return [avg] * gap_length


async def rebuild_aligned(station_code: str) -> dict:
    """从 raw.flow_raw 重建 aligned 层：等间隔网格 + Chronos 填充空缺。"""
    async with _lock:
        data = _load_full()
        raw_station = data.get("raw", {}).get(station_code, {})
        flow_raw = raw_station.get("flow_raw", {})
        records = flow_raw.get("records", [])

        if not records:
            return _ensure_aligned(data, station_code)

        # 1. 检测时间间隔
        interval = _detect_interval(records)

        # 2. 找到连续实测段
        all_times = []
        for r in records:
            dt = _parse_dt(r.get("time", ""))
            if dt:
                all_times.append(dt)
        all_times.sort()
        if len(all_times) < 2:
            return _ensure_aligned(data, station_code)

        grid_start = all_times[0]
        grid_end = all_times[-1]
        total_points = int((grid_end - grid_start).total_seconds() / 60 / interval) + 1

        # 3. 建网格 → 对齐实测值
        aligned_records = []
        record_by_time = {}
        for r in records:
            dt = _parse_dt(r.get("time", ""))
            if dt:
                record_by_time[dt] = r

        for i in range(total_points):
            target = grid_start + timedelta(minutes=interval * i)
            half = timedelta(minutes=interval / 2)
            # 找最近实测
            best_dt, best_rec = None, None
            for dt, rec in record_by_time.items():
                if abs(dt - target) <= half:
                    if best_dt is None or abs(dt - target) < abs(best_dt - target):
                        best_dt, best_rec = dt, rec
            if best_rec:
                rec = {"time": target.strftime("%Y-%m-%d %H:%M:%S")}
                for field in ("waterLevel", "virtualFlow", "waterFlow", "sectionArea", "waterWidth",
                             "surfaceAverageVelocity", "conversionFlow"):
                    val = best_rec.get(field)
                    rec[field] = round(float(val), 2) if val is not None else None
                    rec[f"{field}_source"] = "measured" if val is not None else "unknown"
                    rec[f"{field}_fill"] = None
                aligned_records.append(rec)
            else:
                rec = {"time": target.strftime("%Y-%m-%d %H:%M:%S")}
                for field in ("waterLevel", "virtualFlow", "waterFlow"):
                    rec[field] = None
                    rec[f"{field}_source"] = "unknown"
                    rec[f"{field}_fill"] = None
                aligned_records.append(rec)

        # 4. 填充所有空缺（尾部和内部）
        # 找所有连续空缺段
        gap_runs = []
        in_gap = False
        gap_start = -1
        for i, r in enumerate(aligned_records):
            is_missing = (r.get("virtualFlow_source") == "unknown" or r.get("virtualFlow") is None)
            if is_missing and not in_gap:
                gap_start = i
                in_gap = True
            elif not is_missing and in_gap:
                gap_runs.append((gap_start, i - gap_start))
                in_gap = False
        if in_gap:
            gap_runs.append((gap_start, len(aligned_records) - gap_start))

        for gs, glen in gap_runs:
            if glen > _MAX_FILL_LENGTH or gs < 2:
                continue  # 空缺太大或上下文太少，跳过

            # 找空缺前的连续实测点做上下文
            ctx_start = max(0, gs - _MAX_CONTEXT)
            context = []
            for r in aligned_records[ctx_start:gs]:
                if r.get("virtualFlow") is not None or r.get("waterLevel") is not None:
                    ctx = {"Time": r["time"]}
                    for f in ("waterLevel", "virtualFlow"):
                        if r.get(f) is not None:
                            ctx[f] = r[f]
                    if ctx not in context:
                        context.append(ctx)

            if len(context) < 3:
                continue

            fill_len = min(glen, _MAX_FILL_LENGTH)
            # 流量填充（用水位做协变量）
            flow_preds = await _chronos_fill(context, fill_len, "virtualFlow", covariates=["waterLevel"] if any(c.get("waterLevel") for c in context) else None)
            # 水位填充（用流量做协变量）
            wl_preds = await _chronos_fill(context, fill_len, "waterLevel", covariates=["virtualFlow"] if any(c.get("virtualFlow") for c in context) else None)

            for j in range(fill_len):
                idx = gs + j
                if idx >= len(aligned_records):
                    break
                if flow_preds and j < len(flow_preds):
                    aligned_records[idx]["virtualFlow"] = round(float(flow_preds[j]), 2)
                    aligned_records[idx]["virtualFlow_source"] = "forecast"
                    aligned_records[idx]["virtualFlow_fill"] = "chronos"
                if wl_preds and j < len(wl_preds):
                    aligned_records[idx]["waterLevel"] = round(float(wl_preds[j]), 2)
                    aligned_records[idx]["waterLevel_source"] = "forecast"
                    aligned_records[idx]["waterLevel_fill"] = "chronos"

        # 5. 计算统计 + 截断 + 保存
        max_records = _DEFAULT_MAX_ALIGNED
        aligned_records = aligned_records[-max_records:]

        entry = _ensure_aligned(data, station_code)
        entry["records"] = aligned_records
        entry["updated_at"] = time.time()
        entry["grid"] = {
            "interval_minutes": interval,
            "start": aligned_records[0]["time"] if aligned_records else "",
            "end": aligned_records[-1]["time"] if aligned_records else "",
            "total_points": len(aligned_records),
        }
        entry["stats"] = _compute_stats(aligned_records)
        _save_full(data)
        return entry


# ── 读路径 ──

async def get_raw(station_code: str, data_type: str, max_age: int = 600) -> Optional[dict]:
    """读 raw 层，返回伪装旧 API 格式的 dict。"""
    raw = await _read_aligned_section("raw", station_code, data_type, max_age)
    if not raw:
        return None
    records = raw.get("records", [])
    return {
        "code": 200, "msg": "ok",
        "data": records,
        "pageInfo": {"current": 1, "pages": 1, "size": len(records), "total": len(records)},
    }


async def get_aligned(station_code: str, max_age: int = 600) -> Optional[dict]:
    """读 aligned 层。"""
    return await _read_aligned_section("aligned", station_code, None, max_age)


async def get_aligned_chronos(station_code: str, mode: str = "univariate",
                              context_length: int = 72, max_age: int = 600) -> list:
    """
    返回 Chronos 可直接使用的等间隔时间序列。
    univariate: [{Time: "...", Flow: 1234.5}, ...]
    按时间升序（Chronos 要求）。
    """
    entry = await get_aligned(station_code, max_age)
    if not entry:
        return []
    records = entry.get("records", [])
    # 只取 virtualFlow 有值的点（实测或填充均可）
    series = []
    for r in reversed(records):  # 从旧到新
        vf = r.get("virtualFlow")
        if vf is not None:
            series.append({"Time": r["time"], "Flow": round(float(vf), 2)})
    return series[-context_length:] if len(series) > context_length else series


async def get_aligned_chart(station_code: str, field: str = "virtualFlow",
                            max_age: int = 600) -> dict:
    """返回前端 TrendChart 可直接用的数据。"""
    entry = await get_aligned(station_code, max_age)
    if not entry:
        return {"history": [], "forecast": [], "stats": {}}
    records = entry.get("records", [])
    history, forecast = [], []
    for r in records:
        dt = _parse_dt(r.get("time", ""))
        ts = dt.timestamp() if dt else 0
        val = r.get(field)
        if val is None:
            continue
        point = {
            "time": int(ts * 1000) if ts else 0,
            "t": f"{dt.day:02d}日{dt.hour:02d}时" if dt else r["time"],
            "y": round(float(val), 2),
            "source": r.get(f"{field}_source", "unknown"),
            "fill": r.get(f"{field}_fill"),
        }
        if point["source"] == "measured":
            history.append(point)
        else:
            forecast.append(point)
    return {
        "history": history,
        "forecast": forecast,
        "stats": entry.get("stats", {}).get(field, {}),
        "grid": entry.get("grid", {}),
    }


async def get_stats(station_code: str, field: str, max_age: int = 600) -> dict:
    """读 aligned 层的统计信息。"""
    entry = await get_aligned(station_code, max_age)
    if not entry:
        return {}
    return entry.get("stats", {}).get(field, {})


async def _read_aligned_section(section: str, station: str, dtype: str = None,
                                 max_age: int = 600) -> Optional[dict]:
    async with _lock:
        data = _load_full()
        if section == "raw":
            entry = data.get("raw", {}).get(station, {}).get(dtype)
        else:
            entry = data.get("aligned", {}).get(station)
        if not entry:
            return None
        if time.time() - entry.get("updated_at", 0) > max_age:
            return None
        return entry


# ── 兼容旧 API ──

async def get(key: str, max_age: int = 600) -> Optional[dict]:
    """
    兼容旧的 get() 调用，自动路由到 raw 层的对应数据类型。
    key 格式: "aiflow:flow_raw:00106:FD000489923695" 或 "aiflow:level:00106"
    """
    parts = key.replace("aiflow:", "").split(":")
    if len(parts) >= 2:
        if parts[0] in ("flow_raw", "level", "flow"):
            dtype = parts[0]
            station = parts[1]
            return await get_raw(station, dtype, max_age)
    return None


async def set(key: str, value: Any, ttl: int = 600):
    """兼容旧 set()：降级到直接写 raw 层 records。"""
    parts = key.replace("aiflow:", "").split(":")
    if len(parts) >= 2:
        dtype = parts[0]
        station = parts[1]
        await merge_raw(station, dtype, value)


async def all_keys() -> list:
    async with _lock:
        data = _load_full()
        keys = []
        for station, types in data.get("raw", {}).items():
            for dtype in types:
                keys.append(f"aiflow:{dtype}:{station}:{_DEVICE_CODE}")
        return keys
