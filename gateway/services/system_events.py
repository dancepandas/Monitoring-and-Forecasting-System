"""系统事件日志 — 统一持久化所有系统状态变更，Agent 通过工具查询历史。

用法:
    from gateway.services.system_events import write_event, query_events, init_db
    init_db()  # 服务启动时调用一次
    write_event("alert", "alert_triggered", "...", station_code="00125", severity="red")
    events = query_events(category="alert", hours=24)
"""

import sqlite3
import time
import threading
import logging
from pathlib import Path
from contextvars import ContextVar

from ..config import settings

logger = logging.getLogger(__name__)

# ── DB 路径 ──
DB_PATH = Path(__file__).parent.parent / "data" / "system_events.db"

# ── 当前操作者 session_id（Agent 流中由 stream() 设置，工具函数自动继承） ──
_current_session: ContextVar[str] = ContextVar("system_session", default="system")

# ── 写锁（SQLite 单写者模型，内部隐含 WAL 并发读；显式锁防多线程同时写） ──
_write_lock = threading.Lock()


def init_db():
    """初始化 system_events.db（建表 + 索引）。服务启动时调用，幂等。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                station_code TEXT DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                session_id TEXT DEFAULT 'system',
                severity TEXT DEFAULT 'info'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON system_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_category ON system_events(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_station ON system_events(station_code)")
        conn.commit()
        conn.close()
    logger.info("system_events.db initialized at %s", DB_PATH)


def write_event(
    category: str,
    event_type: str,
    summary: str,
    station_code: str = "",
    old_value: str = "",
    new_value: str = "",
    session_id: str = "",
    severity: str = "info",
):
    """写入一条系统事件。线程安全，可在任意线程/协程中调用。

    若不传 session_id，自动从 ContextVar 读取（由 Agent stream() 设置）。
    """
    sid = session_id or _current_session.get()
    ts = time.time()
    try:
        with _write_lock:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                "INSERT INTO system_events (ts, category, event_type, station_code, summary, old_value, new_value, session_id, severity) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, category, event_type, station_code or "", summary, old_value or "", new_value or "", sid, severity)
            )
            conn.commit()
            conn.close()
    except Exception as e:
        logger.warning("write_event failed: %s", e)


def query_events(
    category: str = "",
    hours: int = 24,
    limit: int = 100,
    station_code: str = "",
) -> list[dict]:
    """查询最近 N 小时的事件（可按 category / station_code 过滤）。

    返回 list[dict]，每个 dict 含所有字段。按时间倒序。
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cutoff = time.time() - hours * 3600

        where = ["ts >= ?"]
        params = [cutoff]

        if category:
            where.append("category = ?")
            params.append(category)
        if station_code:
            where.append("station_code = ?")
            params.append(station_code)

        clause = " AND ".join(where)
        rows = conn.execute(
            f"SELECT * FROM system_events WHERE {clause} ORDER BY ts DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("query_events failed: %s", e)
        return []


# ── ContextVar helpers ──

def set_session(sid: str):
    """设置当前 ContextVar 的 session_id，返回 token 供 reset 使用。"""
    return _current_session.set(sid)


def reset_session(token):
    """重置 ContextVar 的 session_id。"""
    _current_session.reset(token)


def get_session() -> str:
    """获取当前 ContextVar 的 session_id。"""
    return _current_session.get()
