import logging

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from .. import chronos_client, data_cache
from ._helpers import _safe_sync, _get_cached_records, _filter_by_time
# 3. 预报 / 趋势（2 个）
# ---------------------------------------------------------------------------

class RunForecastArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    prediction_length: int = Field(default=12, description="预测步数（每个步长等同事先检测到的时间间隔）")
    mode: str = Field(default="past_covariates", description="预报模式: univariate(单变量) / past_covariates(用历史协变量) / future_covariates(用未来协变量)")
    target: str = Field(default="virtualFlow", description="目标字段: virtualFlow(流量) 或 waterLevel(水位)")
    cov_field: str = Field(default="", description="协变量字段名。预报流量时可用 waterLevel，预报水位时可用 virtualFlow。留空则自动推断")

def run_forecast(**kwargs) -> dict:
    """Chronos-2 时序预报。支持单变量、协变量模式，自动使用 aligned 层等间隔数据。"""
    args = RunForecastArgs(**kwargs)

    # 自动推断目标与协变量
    mode = args.mode or "past_covariates"
    target = args.target or "virtualFlow"
    cov_field = args.cov_field or ""
    if mode in ("past_covariates", "future_covariates") and not cov_field:
        # 自动推断：预报流量用水位为协变量，预报水位用流量为协变量
        cov_field = "waterLevel" if target == "virtualFlow" else "virtualFlow"

    try:
        series = _safe_sync(data_cache.get_aligned_chronos(
            args.station_code,
            mode=mode,
            context_length=72,
            max_age=600,
        ))
    except Exception as ex:
        logger.warning(f"run_forecast get aligned data failed: {ex}")
        return {"error": str(ex), "station_code": args.station_code}

    if not series or len(series) < 10:
        return {"error": f"历史数据不足（仅 {len(series) if series else 0} 条），至少需要 10 条", "station_code": args.station_code}

    # 构建协变量数据
    past_covariates = None
    if mode in ("past_covariates", "future_covariates") and cov_field:
        try:
            aligned = _safe_sync(data_cache.get_aligned(args.station_code, max_age=600))
            if aligned:
                records = aligned.get("records", [])
                cov_vals = []
                for r in records:
                    val = r.get(cov_field)
                    if val is not None and r.get(f"{cov_field}_source") == "measured":
                        cov_vals.append(float(val))
                if cov_vals and len(cov_vals) >= 10:
                    # 截取与目标序列相同长度的尾部
                    cov_vals = cov_vals[-len(series):]
                    if len(cov_vals) == len(series):
                        past_covariates = {cov_field: cov_vals}
        except Exception:
            pass

    logger.info("run_forecast: station=%s, steps=%d, mode=%s, target=%s, cov=%s, data=%d",
                args.station_code, args.prediction_length, mode, target, cov_field, len(series))

    try:
        result = _safe_sync(chronos_client.predict_flow(
            series, args.prediction_length,
            target=target,
            context_length=min(len(series), 72),
            mode=mode,
            past_covariates=past_covariates,
        ))
    except Exception as ex:
        logger.warning(f"run_forecast predict failed: {ex}")
        return {"error": str(ex), "station_code": args.station_code}

    return {
        "station_code": args.station_code,
        "input_count": len(series),
        "mode": mode,
        "target": target,
        "cov_field": cov_field,
        "result": result,
    }

class AnalyzeTrendArgs(BaseModel):
    station_code: str = Field(..., description="测站编码")
    metric: str = Field(default="level", description="指标：level / flow")
    days: int = Field(default=7, description="回溯天数")

def analyze_trend(**kwargs) -> dict:
    args = AnalyzeTrendArgs(**kwargs)
    try:
        if args.metric == "flow":
            data = _safe_sync(_get_cached_records(args.station_code, max_age=600))
            key = "virtualFlow"
        else:
            data = _safe_sync(_get_cached_records(args.station_code, max_age=600))
            key = "waterLevel"
    except Exception as ex:
        return {"error": str(ex), "station_code": args.station_code}
    items = _filter_by_time(data, "", "", 500)
    values = [float(item.get(key, 0)) for item in items if item.get(key) is not None]
    if not values:
        return {"error": "无数据", "station_code": args.station_code}
    n = len(values)
    x = list(range(n))
    mean_x = sum(x) / n
    mean_y = sum(values) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
    den = sum((xi - mean_x) ** 2 for xi in x)
    slope = num / den if den else 0
    trend = "up" if slope > 0.01 else "down" if slope < -0.01 else "stable"
    return {
        "station_code": args.station_code,
        "metric": args.metric,
        "count": n,
        "slope": round(slope, 4),
        "trend": trend,
        "latest": values[-1] if values else None,
    }

# ---------------------------------------------------------------------------