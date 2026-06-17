import time
import threading
import uuid
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    created_at: float
    updated_at: float
    title: str
    messages: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    pending_permission: Optional[dict] = None


_lock = threading.Lock()
_sessions: dict[str, Session] = {}


def create_session(session_id: Optional[str] = None, title: str = "新会话", config: Optional[dict] = None) -> Session:
    sid = session_id or str(uuid.uuid4())
    now = time.time()
    session = Session(
        session_id=sid,
        created_at=now,
        updated_at=now,
        title=title,
        messages=[],
        config=config or {},
        pending_permission=None,
    )
    with _lock:
        _sessions[sid] = session
    return session


def get_session(session_id: str) -> Optional[Session]:
    with _lock:
        return _sessions.get(session_id)


def list_sessions() -> list[Session]:
    with _lock:
        return sorted(_sessions.values(), key=lambda s: s.updated_at, reverse=True)


def delete_session(session_id: str) -> bool:
    with _lock:
        return _sessions.pop(session_id, None) is not None


def save_session(session: Optional[Session] = None, session_id: Optional[str] = None, updates: Optional[dict] = None) -> Optional[Session]:
    """保存会话：可传入 Session 对象，或 session_id + updates 字典。"""
    with _lock:
        if session is not None:
            session.updated_at = time.time()
            _sessions[session.session_id] = session
            return session
        if session_id is not None:
            s = _sessions.get(session_id)
            if s is None:
                return None
            s.updated_at = time.time()
            if updates:
                for k, v in updates.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            _sessions[session_id] = s
            return s
    return None


def get_or_create(session_id: Optional[str] = None, title: str = "新会话", config: Optional[dict] = None) -> Session:
    if session_id:
        existing = get_session(session_id)
        if existing:
            if config:
                existing.config.update(config)
            return existing
    return create_session(session_id, title, config)


def get_pending_permission(session_id: str) -> Optional[dict]:
    s = get_session(session_id)
    return s.pending_permission if s else None


def set_pending_permission(session_id: str, pending: dict) -> None:
    s = get_session(session_id)
    if s:
        s.pending_permission = pending
        save_session(s)


def clear_pending_permission(session_id: str) -> None:
    s = get_session(session_id)
    if s:
        s.pending_permission = None
        save_session(s)
