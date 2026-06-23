import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import HTTP_404_NOT_FOUND

from ..auth.middleware import get_current_user
from ..services.monitor_engine import get_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/active")
async def api_list_active_alerts(
    station_code: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    engine = get_engine()
    events = await engine._tracker.list_active(station_code=station_code, level=level)
    return {"alerts": [e.to_dict() for e in events], "total": len(events)}


@router.get("/history")
async def api_list_alert_history(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    engine = get_engine()
    events = await engine._tracker.list_all(limit=limit)
    return {"alerts": [e.to_dict() for e in events], "total": len(events)}


@router.get("/{alert_id}")
async def api_get_alert(alert_id: str, user: dict = Depends(get_current_user)):
    engine = get_engine()
    event = await engine._tracker.get(alert_id)
    if not event:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="告警不存在")
    return {"alert": event.to_dict()}


@router.post("/{alert_id}/acknowledge")
async def api_acknowledge_alert(
    alert_id: str,
    body: dict = {},
    user: dict = Depends(get_current_user),
):
    engine = get_engine()
    by = body.get("by") or user.get("username", "unknown")
    event = await engine._tracker.acknowledge(alert_id, by=by)
    if not event:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="告警不存在或已解除")
    return {"ok": True, "alert": event.to_dict()}


@router.post("/{alert_id}/resolve")
async def api_resolve_alert(
    alert_id: str,
    body: dict = {},
    user: dict = Depends(get_current_user),
):
    engine = get_engine()
    resolution = body.get("resolution", "已处理")
    by = body.get("by") or user.get("username", "unknown")
    event = await engine._tracker.resolve(alert_id, resolution=resolution, by=by)
    if not event:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="告警不存在或已解除")

    # 后台异步生成复盘总结
    import asyncio
    from ..services.agent_utils import generate_postmortem
    from ..services import station_names
    async def _do_postmortem():
        try:
            summary = await generate_postmortem(event.to_dict(),
                station_name=station_names.station_name(event.station_code))
            if summary:
                event.postmortem = summary
                await engine._tracker._save()
        except Exception:
            logger.exception("[postmortem] generation failed for %s", alert_id)
    asyncio.create_task(_do_postmortem())

    return {"ok": True, "alert": event.to_dict()}
