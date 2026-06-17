"""会话管理 — 内存 + JSON 文件持久化，完全替代 floodmind 的 SQLite。"""

import json
import time
import threading
import uuid
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_SESSIONS_FILE = _DATA_DIR / "sessions.json"

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def _load():
    if _SESSIONS_FILE.exists():
        try:
            return json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save():
    try:
        tmp = _SESSIONS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_sessions, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(_SESSIONS_FILE)
    except Exception:
        pass


# 启动时加载
with _lock:
    _sessions = _load()


def create_session(session_id: Optional[str] = None, title: str = "") -> dict:
    sid = session_id or f"ses_{uuid.uuid4().hex[:12]}"
    now = time.time()
    s = {
        "id": sid, "title": title or "新对话",
        "created_at": now, "updated_at": now,
        "messages": [], "config": {},
        "sync_events": [],
    }
    with _lock:
        _sessions[sid] = s
        _save()
    return dict(s)


def get_session(session_id: str) -> Optional[dict]:
    with _lock:
        return dict(_sessions.get(session_id, {})) if _sessions.get(session_id) else None


def list_sessions() -> list[dict]:
    with _lock:
        result = []
        for sid, s in _sessions.items():
            msgs = s.get("messages", [])
            result.append({
                "id": sid,
                "title": s.get("title", "新对话"),
                "created_at": s.get("created_at", ""),
                "updated_at": s.get("updated_at", ""),
                "msg_count": len(msgs),
            })
        return sorted(result, key=lambda x: x.get("updated_at", 0), reverse=True)


def delete_session(session_id: str) -> bool:
    with _lock:
        if session_id in _sessions:
            del _sessions[session_id]
            _save()
            return True
        return False


def add_message(session_id: str, role: str, parts: list[dict]):
    with _lock:
        s = _sessions.get(session_id)
        if not s:
            return
        msg = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "role": role,
            "parts": list(parts),
            "created_at": time.time(),
        }
        s.setdefault("messages", []).append(msg)
        s["updated_at"] = time.time()
        _save()


def get_messages(session_id: str) -> list[dict]:
    with _lock:
        s = _sessions.get(session_id)
        if not s:
            return []
        return list(s.get("messages", []))


def rename_session(session_id: str, title: str):
    with _lock:
        s = _sessions.get(session_id)
        if s:
            s["title"] = title
            s["updated_at"] = time.time()
            _save()


def get_sync_events(session_id: str, after_index: int = 0) -> list[dict]:
    with _lock:
        s = _sessions.get(session_id)
        if not s:
            return []
        events = s.get("sync_events", [])
        return events[after_index:]


def get_or_create(session_id: Optional[str] = None, title: str = "新会话") -> dict:
    if session_id:
        existing = get_session(session_id)
        if existing:
            return existing
    return create_session(session_id, title)
