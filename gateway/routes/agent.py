import json
import logging
import os
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_400_BAD_REQUEST

from ..auth.middleware import get_current_user
from ..config import settings
from floodmind.memory import session_store as flood_sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

from ..services import session_store, agent_service, scheduler


async def _ndjson_stream(gen: AsyncGenerator[dict, None]) -> AsyncGenerator[str, None]:
    async for event in gen:
        yield json.dumps(event, ensure_ascii=False) + "\n"


# ===== 1. 会话列表（floodmind SQLite） =====
@router.get("/sessions")
async def api_list_sessions(user: dict = Depends(get_current_user)):
    sessions = flood_sessions.list_sessions()
    result = []
    for s in sessions:
        result.append({
            "session_id": s["id"],
            "title": s.get("title") or "新对话",
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
            "msg_count": s.get("msg_count", 0),
        })
    return {"sessions": result}


@router.get("/sessions/{session_id}")
async def api_get_session(session_id: str, user: dict = Depends(get_current_user)):
    s = flood_sessions.get_session(session_id)
    if not s:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="会话不存在")
    return {"session": s}


# ===== 2. 会话消息历史 =====
@router.get("/sessions/{session_id}/messages")
async def api_get_messages(session_id: str, user: dict = Depends(get_current_user)):
    messages = flood_sessions.get_messages(session_id)
    result = []
    for msg in messages:
        item = {
            "id": msg["id"],
            "role": msg["role"],
            "created_at": msg.get("created_at", ""),
        }
        parts = msg.get("parts", [])
        texts = [p["text"] for p in parts if p["type"] == "text"]
        item["content"] = "\n".join(texts)
        result.append(item)
    return {"messages": result}


@router.delete("/sessions/{session_id}")
async def api_delete_session(session_id: str, user: dict = Depends(get_current_user)):
    try:
        flood_sessions.delete_session(session_id)
    except Exception:
        pass
    return {"ok": True}


@router.post("/sessions/save")
async def api_save_session(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="session_id 不能为空")
    return {"session": flood_sessions.get_session(session_id)}


# ===== 3. 初始化 =====
@router.post("/init")
async def api_init(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    if not session_id:
        session_id = f"ses_{uuid.uuid4().hex[:12]}"
    existing = flood_sessions.get_session(session_id)
    if not existing:
        flood_sessions.create_session(session_id=session_id, title="")
    session_store.get_or_create(session_id)
    return {"session": {"session_id": session_id}}


# ===== 4. 模型 =====
@router.get("/models")
async def api_models(user: dict = Depends(get_current_user)):
    return [{"id": settings.agent_model_name, "name": settings.agent_model_name}]


# ===== 5. 聊天 =====
@router.post("/chat")
async def api_chat(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    message = body.get("message", "")
    uploaded_files = body.get("uploaded_files") or []

    if not session_id:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="session_id 不能为空")

    svc = agent_service.AgentService.get_or_create_agent(session_id)
    stream_gen = svc.stream(session_id, message, uploaded_files=uploaded_files)

    return StreamingResponse(
        _ndjson_stream(stream_gen),
        media_type="application/x-ndjson",
        headers={"X-Session-Id": session_id}
    )


# ===== 6. 流恢复 =====
@router.get("/stream/resume")
async def api_stream_resume(
    session_id: str = Query(...),
    after_index: int = Query(0),
    user: dict = Depends(get_current_user)
):
    s = flood_sessions.get_session(session_id)
    if not s:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="会话不存在")

    async def _resume():
        events = flood_sessions.get_sync_events(session_id, after_index)
        for ev in events:
            yield {"type": ev["event_type"], "data": json.loads(ev.get("event_data", "{}"))}

    return StreamingResponse(
        _ndjson_stream(_resume()),
        media_type="application/x-ndjson",
        headers={"X-Session-Id": session_id}
    )


# ===== 7. 会话状态 =====
@router.get("/session/status")
async def api_session_status(session_id: str = Query(...), user: dict = Depends(get_current_user)):
    s = session_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="会话不存在")
    return {"status": s.config.get("status", "active"), "session_id": session_id}


@router.post("/session/pause")
async def api_session_pause(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="session_id 不能为空")
    s = session_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="会话不存在")
    s.config["status"] = "paused"
    session_store.save_session(s)
    return {"status": "paused", "session_id": session_id}


@router.post("/session/resume")
async def api_session_resume(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="session_id 不能为空")
    s = session_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="会话不存在")
    s.config["status"] = "active"
    session_store.save_session(s)
    return {"status": "active", "session_id": session_id}


# ===== 8. 权限 =====
@router.post("/permission/respond")
async def api_permission_respond(body: dict, user: dict = Depends(get_current_user)):
    ask_id = body.get("ask_id")
    approved = body.get("approved")
    session_id = body.get("session_id")
    if not ask_id or approved is None or not session_id:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="ask_id, approved, session_id 均不能为空")
    svc = agent_service.AgentService.get_or_create_agent(session_id)
    result = await svc.respond_permission(session_id, ask_id, approved)
    return {"ok": True, "result": result}


# ===== 9. 文件上传 =====
@router.post("/upload")
async def api_upload(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    user: dict = Depends(get_current_user)
):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1]
    safe_name = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    return {"file_id": file_id, "name": file.filename or safe_name, "url": f"/api/files/{file_id}"}


@router.get("/files/{file_id}")
async def api_get_file(file_id: str, user: dict = Depends(get_current_user)):
    for name in os.listdir(UPLOAD_DIR):
        if name.startswith(file_id):
            return FileResponse(os.path.join(UPLOAD_DIR, name))
    raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="文件不存在")


# ===== 10. 定时任务 =====
@router.get("/scheduled-tasks")
async def api_list_tasks(
    session_id: Optional[str] = Query(None),
    include_all: bool = Query(False),
    user: dict = Depends(get_current_user)
):
    tasks = scheduler.list_tasks(session_id=session_id if not include_all else None)
    return {"tasks": tasks}


@router.post("/scheduled-tasks")
async def api_create_task(body: dict, user: dict = Depends(get_current_user)):
    session_id = body.get("session_id")
    task_type = body.get("task_type")
    cron = body.get("cron")
    params = body.get("params") or {}
    if not session_id or not task_type or not cron:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="session_id, task_type, cron 均不能为空")
    merged_params = {**params, "session_id": session_id}
    task_id = scheduler.create_task(task_type, cron, merged_params)
    return {"task": {"task_id": task_id, "task_type": task_type, "cron": cron, "params": merged_params}}


@router.delete("/scheduled-tasks/{task_id}")
async def api_cancel_task(task_id: str, user: dict = Depends(get_current_user)):
    ok = scheduler.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="任务不存在")
    return {"ok": True}


# ===== 11. 健康检查 =====
@router.get("/health")
async def api_health():
    return {"available": True, "service": "gateway-agent"}


@router.get("/agent/health")
async def api_health_legacy():
    return {"available": True, "service": "gateway-agent"}
