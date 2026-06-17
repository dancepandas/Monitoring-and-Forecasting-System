from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from ..auth.middleware import get_current_user
from ..schemas import ForecastRequest
from ..services import data_cache, chronos_client

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

_cache = {}


@router.post("/run")
async def run_forecast(req: ForecastRequest, user: dict = Depends(get_current_user)):
    series = await data_cache.get_aligned_chronos(
        req.station_code,
        mode=getattr(req, "mode", "univariate") or "univariate",
        context_length=getattr(req, "context_length", 72) or 72,
        max_age=600,
    )
    if len(series) < 10:
        raise HTTPException(status_code=400, detail=f"历史数据不足（仅 {len(series)} 条），至少需要 10 条")

    mode = getattr(req, "mode", "univariate") or "univariate"
    result = await chronos_client.predict_flow(
        series, req.prediction_length,
        context_length=min(len(series), getattr(req, "context_length", 72) or 72),
        mode=mode,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])

    _cache[req.station_code] = {
        "input_series": series,
        "result": result,
        "generated": datetime.now().isoformat(),
    }
    return _cache[req.station_code]


@router.get("/result")
async def get_result(station_code: str, user: dict = Depends(get_current_user)):
    if station_code not in _cache:
        raise HTTPException(status_code=404, detail="该站暂无预报结果，请先触发预报")
    return _cache[station_code]
