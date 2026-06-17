from fastapi import APIRouter, Depends

from ..auth.middleware import get_current_user
from ..services import system_status

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
async def get_system_status(user: dict = Depends(get_current_user)):
    """返回最近一次系统自检结果。"""
    return system_status.get_status()


@router.post("/check")
async def trigger_system_check(user: dict = Depends(get_current_user)):
    """手动触发系统自检（供智能体调用）。"""
    import asyncio
    from ..services.scheduler import _run_system_check
    await _run_system_check({"trigger": "manual"})
    return system_status.get_status()
