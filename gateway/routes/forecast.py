from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime

from ..auth.middleware import get_current_user
from ..schemas import ForecastRequest
from ..services import data_cache, chronos_client, station_names
from ..services.agent_utils import interpret_forecast

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

_cache: dict[str, dict] = {}


@router.get("/interpret")
async def get_forecast_interpret(
    station_code: str = Query("00106"),
    field: str = Query("virtualFlow"),
    user: dict = Depends(get_current_user),
):
    """Agent 解读最新预报结果，返回自然语言总结。"""
    chart = await data_cache.get_aligned_chart(station_code, field)
    if not chart:
        return {"interpretation": "缓存未就绪，请等待数据采集后重试。", "generated": datetime.now().isoformat()}
    history = chart.get("history", [])
    forecast = chart.get("forecast", [])

    label = "流量" if field == "virtualFlow" else "水位"
    text = await interpret_forecast(
        station_code=station_code,
        station_name=station_names.station_name(station_code),
        history=history,
        forecast=forecast,
        field=label,
    )
    return {
        "interpretation": text or "Agent 暂时无法生成解读，请稍后重试。",
        "generated": datetime.now().isoformat(),
    }


@router.post("/run")
async def run_forecast(req: ForecastRequest, user: dict = Depends(get_current_user)):
    series = await data_cache.get_aligned_chronos(
        req.station_code,
        mode=getattr(req, "mode", "univariate") or "univariate",
        context_length=getattr(req, "context_length", 72) or 72,
        max_age=600,
    )
    if not series or len(series) < 10:
        raise HTTPException(status_code=400, detail=f"历史数据不足（仅 {len(series) if series else 0} 条），至少需要 10 条")

    mode = getattr(req, "mode", "univariate") or "univariate"
    try:
        result = await chronos_client.predict_flow(
            series, req.prediction_length,
            context_length=min(len(series), getattr(req, "context_length", 72) or 72),
            mode=mode,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Chronos-2 预测失败: {e}")

    if result.get("error"):
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
