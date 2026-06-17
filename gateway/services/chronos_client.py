import httpx
import logging
import numpy as np
from ..config import settings

logger = logging.getLogger(__name__)


def _local_forecast(series: list[dict], prediction_length: int) -> dict:
    """Chronos 服务不可达时的本地 fallback：用多项式趋势 + 均值水平做短期预报。"""
    values = np.array([float(s["Flow"]) for s in series if s.get("Flow") is not None])
    if len(values) == 0:
        return {"error": "无有效历史流量数据"}

    n = len(values)
    x = np.arange(n, dtype=float)
    degree = 2 if n >= 5 else 1
    coeffs = np.polyfit(x, values, degree)
    poly = np.poly1d(coeffs)

    base = float(np.mean(values[-min(n, 24):]))
    preds = []
    for i in range(prediction_length):
        trend = float(poly(n + i))
        # 让长期趋势向近期均值回归，避免二次多项式发散
        w = min(1.0, i / 24.0)
        val = trend * (1 - w) + base * w
        preds.append(round(val, 2))

    low = [round(v * 0.92, 2) for v in preds]
    high = [round(v * 1.08, 2) for v in preds]
    return {
        "model": "local_trend_fallback",
        "predictions": preds,
        "forecast": preds,
        "series": preds,
        "quantiles": {"0.1": low, "0.5": preds, "0.9": high},
    }


async def predict_flow(
    data: list[dict],
    prediction_length: int = 72,
    target: str = "Flow",
    context_length: int = 72,
    mode: str = "univariate"
) -> dict:
    """优先调用 Chronos 服务；不可达时使用本地趋势 fallback，保证预报流程可跑通。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.chronos_url}/predict",
                json={
                    "mode": mode,
                    "data": data,
                    "prediction_length": prediction_length,
                    "target": target,
                    "timestamp_column": "Time",
                    "context_length": context_length,
                    "quantile_levels": [0.1, 0.5, 0.9]
                }
            )
            r.raise_for_status()
            result = r.json()
            logger.info("Chronos service returned forecast")
            return result
    except httpx.ConnectError:
        logger.warning("Chronos service not reachable, using local trend fallback")
        return _local_forecast(data[-context_length:], prediction_length)
    except Exception as e:
        logger.error(f"Chronos predict failed: {e}, using local trend fallback")
        return _local_forecast(data[-context_length:], prediction_length)
