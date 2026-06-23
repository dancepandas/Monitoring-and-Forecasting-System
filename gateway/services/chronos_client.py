"""
Chronos-2 时序预报模型 — 直接加载本地 Pipeline，支持单变量与协变量模式。

首次调用时自动加载模型（约 3~5 秒），后续调用复用单例。
"""

import logging
import threading
from typing import Optional

import numpy as np
import pandas as pd

from ..config import settings

logger = logging.getLogger(__name__)

_pipeline = None
_pipeline_lock = threading.Lock()
_predict_lock = threading.Lock()
_MODEL_NAME = "amazon/chronos-2"


def _get_pipeline():
    """Chronos2Pipeline 单例（首次调用时加载，线程安全）。"""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            import torch
            from chronos import Chronos2Pipeline
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("加载 Chronos-2: %s, device=%s", _MODEL_NAME, device)
            try:
                _pipeline = Chronos2Pipeline.from_pretrained(
                    _MODEL_NAME, device_map=device, local_files_only=True
                )
            except Exception:
                _pipeline = Chronos2Pipeline.from_pretrained(
                    _MODEL_NAME, device_map=device
                )
            logger.info("Chronos-2 模型加载完成")
        except Exception as e:
            logger.error("Chronos-2 加载失败: %s", e)
            raise
    return _pipeline


def _local_poly_forecast(values: np.ndarray, prediction_length: int) -> dict:
    """Chronos 不可用时的多项式趋势 fallback。"""
    n = len(values)
    x = np.arange(n, dtype=float)
    degree = 2 if n >= 10 else 1
    coeffs = np.polyfit(x, values, degree)
    poly = np.poly1d(coeffs)
    base = float(np.mean(values[-min(n, 24):]))
    preds = []
    for i in range(prediction_length):
        trend = float(poly(n + i))
        w = min(1.0, i / 24.0)
        preds.append(round(trend * (1 - w) + base * w, 2))
    return {
        "model": "local_poly_fallback",
        "predictions": preds,
        "forecast": preds,
        "series": preds,
    }


async def predict_flow(
    data: list[dict],
    prediction_length: int = 72,
    target: str = "Flow",
    context_length: int = 72,
    mode: str = "univariate",
    past_covariates: Optional[dict[str, list[float]]] = None,
    future_covariates: Optional[dict[str, list[float]]] = None,
) -> dict:
    """用 Chronos-2 做时序预测。

    Args:
        data: 历史数据，每项含 Time 和值字段
        prediction_length: 预测步数
        target: 预测目标字段名
        context_length: 历史上下文长度
        mode: univariate / past_covariates / future_covariates
        past_covariates: {covariate_name: [values]}, 长度须等于 data
        future_covariates: {covariate_name: [future_values]}, 长度须等于 prediction_length
    """
    import asyncio
    loop = asyncio.get_event_loop()

    series = data[-context_length:] if len(data) > context_length else data
    target_vals = [float(s.get(target, 0) or 0) for s in series]

    if len(target_vals) < 10:
        return _local_poly_forecast(np.array(target_vals or [0]), prediction_length)

    # 校验协变量长度
    valid_past = {}
    if past_covariates and mode in ("past_covariates", "future_covariates"):
        for name, vals in past_covariates.items():
            if len(vals) == len(series):
                valid_past[name] = [float(v) for v in vals]
            else:
                logger.warning("past_covariate '%s' length mismatch (%d vs %d), ignored",
                               name, len(vals), len(series))

    valid_future = {}
    if future_covariates and mode == "future_covariates":
        for name, vals in future_covariates.items():
            if len(vals) == prediction_length:
                valid_future[name] = [float(v) for v in vals]
            else:
                logger.warning("future_covariate '%s' length mismatch (%d vs %d), ignored",
                               name, len(vals), prediction_length)

    # 协变量全部不可用时降级
    effective_mode = mode
    if mode == "future_covariates" and not valid_future:
        effective_mode = "past_covariates" if valid_past else "univariate"
        logger.info("no valid future covariates, fallback to %s", effective_mode)
    elif mode in ("past_covariates", "future_covariates") and not valid_past:
        effective_mode = "univariate"
        logger.info("no valid past covariates, fallback to univariate")

    try:
        result = await loop.run_in_executor(
            None,
            _run_chronos_predict,
            series, target, prediction_length, effective_mode,
            valid_past, valid_future,
        )
        return result
    except Exception as e:
        logger.warning("Chronos-2 预测失败，降级到本地趋势: %s", e)
        vals = [float(s.get(target, 0) or 0) for s in data]
        return _local_poly_forecast(np.array(vals), prediction_length)


def _run_chronos_predict(
    series: list,
    target: str,
    prediction_length: int,
    mode: str,
    past_covariates: dict[str, list[float]],
    future_covariates: dict[str, list[float]],
) -> dict:
    """在独立线程中运行 Chronos-2 预测。"""
    pipeline = _get_pipeline()

    times = [s.get("Time", "") for s in series]
    target_vals = [float(s.get(target, 0) or 0) for s in series]

    context_data = {"Time": pd.to_datetime(times), target: target_vals}
    for name, vals in past_covariates.items():
        context_data[name] = vals

    context_df = pd.DataFrame(context_data)
    context_df = context_df.sort_values("Time").reset_index(drop=True)
    context_df["item_id"] = "item_0"

    # 推断/标准化频率：重采样为等间隔，缺失值前向填充，确保 Chronos 能识别 freq
    time_diffs = context_df["Time"].diff().dropna()
    interval = time_diffs.mode().iloc[0] if len(time_diffs) > 0 else pd.Timedelta(minutes=30)
    try:
        freq = pd.tseries.frequencies.to_offset(interval)
    except Exception:
        freq = pd.offsets.Minute(30)

    context_df = context_df.set_index("Time").groupby("item_id").resample(freq).nearest(limit=1).reset_index(level=0, drop=True)
    # 前向填充 target 和协变量
    context_df[target] = context_df[target].ffill().bfill()
    for name in past_covariates:
        if name in context_df.columns:
            context_df[name] = context_df[name].ffill().bfill()
    context_df = context_df.reset_index()
    context_df["item_id"] = "item_0"

    last_time = context_df["Time"].iloc[-1]

    future_times = [last_time + freq * (i + 1) for i in range(prediction_length)]
    future_data = {"Time": future_times, "item_id": "item_0"}

    if mode == "future_covariates" and future_covariates:
        for name, vals in future_covariates.items():
            future_data[name] = [float(v) for v in vals]

    future_df = pd.DataFrame(future_data) if future_data else None

    logger.info("Chronos-2 predict: mode=%s, target=%s, history=%d, steps=%d, interval=%s, covariates=%s",
                mode, target, len(context_df), prediction_length, freq, list(past_covariates.keys()))

    with _predict_lock:
        pred_df = pipeline.predict_df(
            context_df,
            future_df=future_df,
            prediction_length=prediction_length,
            quantile_levels=[0.1, 0.5, 0.9],
            id_column="item_id",
            timestamp_column="Time",
            target=target,
        )

    # 提取预测值（优先取 target_q0.5，否则取第一个数值列或 q0.5 列）
    def _get_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return df[c].values
        return None

    pred_median = _get_col(pred_df, [f"{target}_q0.5", "0.5", "q0.5"])
    if pred_median is None:
        numeric_cols = pred_df.select_dtypes(include=[np.number]).columns.tolist()
        pred_median = pred_df[numeric_cols[0]].values if numeric_cols else np.zeros(prediction_length)

    preds = [round(float(v), 2) for v in pred_median]
    logger.info("Chronos-2 预测成功: mode=%s, target=%s, steps=%d", mode, target, len(preds))

    return {
        "model": "chronos-2",
        "mode": mode,
        "predictions": preds,
        "forecast": preds,
        "series": preds,
    }
