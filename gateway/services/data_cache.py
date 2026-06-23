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
                         "uploadStatus", "waterLevelType", "dataType",
                         "waterVelocity", "videoUrl", "deviceCode", "programState"):
                val = it.get(field)
                if field in ("videoUrl", "deviceCode"):
                    rec[field] = str(val) if val else None
                else:
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




def _interpolate_missing(values: list) -> list:
    """对列表中的 None 值做线性插值，两端缺失则用最近有效值填充。
    若完全没有有效值，返回原列表（不做 0 填充，避免水文数据误报）。"""
    if not values:
        return values
    n = len(values)
    result = list(values)
    valid_indices = [i for i, v in enumerate(result) if v is not None]
    if not valid_indices:
        # 完全没有有效值，不能猜测为 0
        return result
    if len(valid_indices) == 1:
        # 只有一个有效值，用它填充全部
        fill_val = result[valid_indices[0]]
        return [fill_val] * n
    for i in range(n):
        if result[i] is None:
            left_idx, right_idx = None, None
            for j in range(i - 1, -1, -1):
                if result[j] is not None:
                    left_idx = j
                    break
            for j in range(i + 1, n):
                if result[j] is not None:
                    right_idx = j
                    break
            if left_idx is not None and right_idx is not None:
                ratio = (i - left_idx) / (right_idx - left_idx)
                result[i] = result[left_idx] + ratio * (result[right_idx] - result[left_idx])
            elif left_idx is not None:
                result[i] = result[left_idx]
            elif right_idx is not None:
                result[i] = result[right_idx]
    return result


async def rebuild_aligned(station_code: str) -> dict:
    """从 raw.flow_raw 重建 aligned 层（Chronos-2 推理在锁外执行）。

    三阶段：
    1. 加锁：读取 raw 数据，构建等间隔网格
    2. 无锁：运行 Chronos-2 预报和空缺填充
    3. 加锁：回写结果到 aligned 缓存
    """
    # ── Phase 1: 加锁读取，构建网格 ──
    async with _lock:
        data = _load_full()
        raw_station = data.get("raw", {}).get(station_code, {})
        flow_raw = raw_station.get("flow_raw", {})
        records = list(flow_raw.get("records", []))  # 浅拷贝

        if not records:
            return _ensure_aligned(data, station_code)

        # 1. 检测主导时间间隔
        interval = _detect_interval(records)

        # 2. 按时间排序，建实测映射
        record_by_dt = {}
        all_times = []
        for r in records:
            dt = _parse_dt(r.get("time", ""))
            if dt:
                aligned_dt = _snap_to_grid(dt, interval)
                record_by_dt[aligned_dt] = r
                all_times.append(aligned_dt)
        if len(all_times) < 1:
            return _ensure_aligned(data, station_code)
        all_times.sort()

        grid_start = all_times[0]
        grid_end = all_times[-1]
        if grid_start == grid_end:
            total_points = 1
        else:
            total_points = int((grid_end - grid_start).total_seconds() / 60 / interval) + 1

        # 3. 建等间隔网格 → 映射实测值
        aligned_records = []
        for i in range(total_points):
            target = grid_start + timedelta(minutes=interval * i)
            t_str = target.strftime("%Y-%m-%d %H:%M:%S")
            best_rec = record_by_dt.get(target)
            if best_rec:
                rec = {"time": t_str}
                for field in ("waterLevel", "virtualFlow", "waterFlow", "waterVelocity",
                             "sectionArea", "waterWidth", "surfaceAverageVelocity"):
                    val = best_rec.get(field)
                    rec[field] = round(float(val), 2) if val is not None else None
                    rec[f"{field}_source"] = "measured" if val is not None else "unknown"
                    rec[f"{field}_fill"] = None
                aligned_records.append(rec)
            else:
                aligned_records.append({
                    "time": t_str,
                    "waterLevel": None, "waterLevel_source": "unknown", "waterLevel_fill": None,
                    "virtualFlow": None, "virtualFlow_source": "unknown", "virtualFlow_fill": None,
                    "waterFlow": None, "waterFlow_source": "unknown", "waterFlow_fill": None,
                })

    # ── Phase 2: 无锁运行 Chronos-2 ──
    MIN_POINTS = 10
    FORECAST_STEPS = 12
    future_records = []

    wl_measured = [r for r in aligned_records if r.get("waterLevel_source") == "measured" and r.get("waterLevel") is not None]
    vf_measured = [r for r in aligned_records if r.get("virtualFlow_source") == "measured" and r.get("virtualFlow") is not None]
    wl_ok = len(wl_measured) >= MIN_POINTS
    vf_ok = len(vf_measured) >= MIN_POINTS

    if wl_ok or vf_ok:
        try:
            from . import chronos_client

            # 生成未来时间网格
            future_start = grid_end + timedelta(minutes=interval)
            for i in range(FORECAST_STEPS):
                ft = future_start + timedelta(minutes=interval * i)
                future_records.append({
                    "time": ft.strftime("%Y-%m-%d %H:%M:%S"),
                    "waterLevel": None, "waterLevel_source": "unknown", "waterLevel_fill": None,
                    "virtualFlow": None, "virtualFlow_source": "unknown", "virtualFlow_fill": None,
                    "waterFlow": None, "waterFlow_source": "unknown", "waterFlow_fill": None,
                })

            # 构建协变量序列的辅助函数：缺失值用插值填充，避免完全降级
            def _build_covariates(measured_records, cov_field, cov_name, count):
                """从实测记录中构建协变量序列，缺失值用插值填充。"""
                raw_vals = [r.get(cov_field) for r in measured_records[-count:]]
                if not raw_vals:
                    return {}, "univariate"
                # 统计缺失比例
                none_count = sum(1 for v in raw_vals if v is None)
                if none_count == 0:
                    return {cov_name: [float(v) for v in raw_vals]}, "past_covariates"
                # 缺失 <= 30% 时插值填充；否则降级
                if none_count / len(raw_vals) <= 0.3:
                    interp = _interpolate_missing(raw_vals)
                    if all(v is not None for v in interp):
                        logger.info("covariate '%s' %d/%d missing, interpolated", cov_name, none_count, len(raw_vals))
                        return {cov_name: [float(v) for v in interp]}, "past_covariates"
                return {}, "univariate"

            async def _chronos_predict(field, cov_field, cov_name, cov_ok):
                measured = [r for r in aligned_records if r.get(f"{field}_source") == "measured" and r.get(field) is not None]
                if len(measured) < MIN_POINTS:
                    return
                ctx_count = min(len(measured), 72)
                ctx_series = []
                for r in measured[-ctx_count:]:
                    entry = {"Time": r["time"], field: r.get(field)}
                    ctx_series.append(entry)

                past_cv, mode = _build_covariates(measured, cov_field, cov_name, ctx_count) if cov_ok else ({}, "univariate")

                try:
                    result = await chronos_client.predict_flow(
                        data=ctx_series,
                        prediction_length=FORECAST_STEPS,
                        target=field,
                        context_length=ctx_count,
                        mode=mode,
                        past_covariates=past_cv or None,
                    )
                except Exception:
                    return
                if result and result.get("predictions"):
                    for j, v in enumerate(result["predictions"]):
                        if j < FORECAST_STEPS:
                            future_records[j][field] = round(float(v), 2)
                            future_records[j][f"{field}_source"] = "future_forecast"
                            future_records[j][f"{field}_fill"] = "chronos"

            if wl_ok:
                await _chronos_predict("waterLevel", "virtualFlow", "virtualFlow", vf_ok)
            if vf_ok:
                await _chronos_predict("virtualFlow", "waterLevel", "waterLevel", wl_ok)

            # 内部空缺填充（同样使用插值协变量）
            async def _fill_gaps(field, cov_field, cov_name, cov_ok):
                max_fill = _MAX_FILL_LENGTH
                gap_start = -1
                fill_tasks = []
                for i, r in enumerate(aligned_records):
                    src = r.get(f"{field}_source", "")
                    val = r.get(field)
                    if src in ("unknown", None) and val is None:
                        if gap_start < 0:
                            gap_start = i
                    elif gap_start >= 0:
                        glen = min(i - gap_start, max_fill)
                        fill_tasks.append((gap_start, glen))
                        gap_start = -1
                if gap_start >= 0:
                    glen = min(len(aligned_records) - gap_start, max_fill)
                    fill_tasks.append((gap_start, glen))

                for gs, glen in fill_tasks:
                    if glen <= 0:
                        continue
                    ctx = aligned_records[max(0, gs - 72):gs]
                    ctx_series = []
                    ctx_cov_vals = []
                    for r in ctx:
                        v = r.get(field)
                        if v is not None:
                            entry = {"Time": r["time"], field: v}
                            ctx_series.append(entry)
                            if cov_ok and cov_field:
                                ctx_cov_vals.append(r.get(cov_field))
                    if len(ctx_series) < 5:
                        continue

                    past_cv, mode = {}, "univariate"
                    if cov_ok and cov_field and ctx_cov_vals:
                        none_count = sum(1 for v in ctx_cov_vals if v is None)
                        if none_count == 0:
                            past_cv = {cov_name: [float(v) for v in ctx_cov_vals]}
                            mode = "past_covariates"
                        elif none_count / len(ctx_cov_vals) <= 0.3:
                            interp = _interpolate_missing(ctx_cov_vals)
                            if all(v is not None for v in interp):
                                past_cv = {cov_name: [float(v) for v in interp]}
                                mode = "past_covariates"

                    try:
                        result = await chronos_client.predict_flow(
                            data=ctx_series, prediction_length=glen,
                            target=field, context_length=min(len(ctx_series), 72),
                            mode=mode, past_covariates=past_cv or None,
                        )
                    except Exception:
                        result = None
                    if result and result.get("predictions"):
                        for j, v in enumerate(result["predictions"]):
                            idx = gs + j
                            if idx >= len(aligned_records):
                                break
                            aligned_records[idx][field] = round(float(v), 2)
                            aligned_records[idx][f"{field}_source"] = "forecast"
                            aligned_records[idx][f"{field}_fill"] = "chronos"

            if wl_ok:
                await _fill_gaps("waterLevel", "virtualFlow", "virtualFlow", vf_ok)
            if vf_ok:
                await _fill_gaps("virtualFlow", "waterLevel", "waterLevel", wl_ok)
        except ImportError:
            pass

    # ── Phase 3: 加锁回写 ──
    async with _lock:
        data = _load_full()
        aligned_records.extend(future_records)
        max_records = _DEFAULT_MAX_ALIGNED
        # 确保未来预报不被截断：先截断历史头，保留尾部（含未来预报）
        if len(aligned_records) > max_records:
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


def _snap_to_grid(dt: datetime, interval_min: int) -> datetime:
    """将时间对齐到等间隔网格点（向下取整），正确处理小时进位。"""
    base = dt.replace(second=0, microsecond=0)
    total_minutes = base.hour * 60 + base.minute
    snapped = (total_minutes // interval_min) * interval_min
    hour = snapped // 60
    minute = snapped % 60
    return base.replace(hour=hour, minute=minute)


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
    # 只取 virtualFlow 有实测值的点（过滤 Chronos 填充值，避免级联预报误差）
    series = []
    for r in reversed(records):  # 从旧到新
        vf = r.get("virtualFlow")
        if vf is not None and r.get("virtualFlow_source") == "measured":
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
        elif point["source"] == "future_forecast":
            forecast.append(point)
        else:
            # gap-fill forecast: part of historical record
            history.append(point)
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


# ── 视频快照缓存（独立轻量存储） ──

_VIDEO_SNAPSHOTS_FILE = CACHE_DIR / "video_snapshots.json"
_video_lock = asyncio.Lock()
_MAX_VIDEO_SNAPSHOTS = 10


async def save_video_snapshot(station_code: str, snapshot: dict) -> list:
    """保存一条视频快照，保留最近 10 条。返回当前全部快照列表。"""
    async with _video_lock:
        snaps = _load_video_snapshots()
        station_snaps = snaps.get(station_code, [])
        station_snaps.insert(0, snapshot)
        station_snaps = station_snaps[:_MAX_VIDEO_SNAPSHOTS]
        snaps[station_code] = station_snaps
        _save_video_snapshots(snaps)
        return station_snaps


async def get_video_snapshots(station_code: str, limit: int = 10) -> list:
    """读取视频快照列表。"""
    async with _video_lock:
        snaps = _load_video_snapshots()
        return snaps.get(station_code, [])[:limit]


def _load_video_snapshots() -> dict:
    if not _VIDEO_SNAPSHOTS_FILE.exists():
        return {}
    try:
        return json.loads(_VIDEO_SNAPSHOTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_video_snapshots(data: dict):
    try:
        tmp = _VIDEO_SNAPSHOTS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(_VIDEO_SNAPSHOTS_FILE)
    except Exception:
        pass
