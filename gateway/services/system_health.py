"""
系统健康状态日志 — 定期快照到 data/health_snapshot.json，崩了直接查。
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOT_FILE = DATA_DIR / "health_snapshot.json"
HISTORY_FILE = DATA_DIR / "health_history.jsonl"
_MAX_HISTORY = 288  # ~24h (每5分钟)

_started_at = datetime.now().isoformat()


def snapshot(collector_pid=None):
    """采集全系统状态快照。可被定时任务或手动调用。"""
    now = time.time()
    dt_iso = datetime.now().isoformat()

    s = {
        "at": dt_iso,
        "uptime_seconds": int(now - datetime.fromisoformat(_started_at).timestamp()),
        "server": {"started_at": _started_at, "port": 15002},
        "collector": _collector(collector_pid),
        "cache": _cache(),
        "alerts": _alerts(),
    }

    _write_snapshot(s)
    _append_history(s)
    return s


def _collector(pid):
    s = {"alive": False, "pid": pid, "heartbeat_age_sec": None}
    hb = DATA_DIR / "collector_heartbeat.txt"
    if hb.exists():
        try:
            age = time.time() - float(hb.read_text().strip())
            s["heartbeat_age_sec"] = int(age)
            s["alive"] = age < 600  # 10分钟内有心跳
        except Exception:
            pass

    # collector 日志最后几行的错误
    clog = DATA_DIR / "collector.log"
    if clog.exists():
        try:
            lines = clog.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            errors = [l for l in lines[-20:] if "ERROR" in l or "CRITICAL" in l or "Traceback" in l]
            if errors:
                s["recent_errors"] = errors[-5:]
        except Exception:
            pass

    return s


def _cache():
    s = {}
    cf = DATA_DIR / "hydro_cache.json"
    if cf.exists():
        try:
            s["file_size_kb"] = round(cf.stat().st_size / 1024, 1)
            s["file_mtime"] = datetime.fromtimestamp(cf.stat().st_mtime).isoformat()
            raw = json.loads(cf.read_text(encoding="utf-8"))
            raw_stations = raw.get("raw", {})
            aligned = raw.get("aligned", {})
            for code in raw_stations:
                types = raw_stations[code]
                for dtype, v in types.items():
                    s.setdefault("raw", {})[f"{code}/{dtype}"] = len(v.get("records", []))
            for code in aligned:
                s.setdefault("aligned", {})[code] = len(aligned[code].get("records", []))
        except Exception as e:
            s["read_error"] = str(e)
    else:
        s["file_missing"] = True
    return s


def _alerts():
    s = {"active": 0, "by_level": {}}
    af = DATA_DIR / "active_alerts.json"
    if af.exists():
        try:
            data = json.loads(af.read_text(encoding="utf-8"))
            unresolved = [v for v in data.values() if not v.get("resolved_at")]
            s["active"] = len(unresolved)
            for v in unresolved:
                lv = v.get("level", "?")
                s["by_level"][lv] = s["by_level"].get(lv, 0) + 1
        except Exception as e:
            s["read_error"] = str(e)
    return s


def _write_snapshot(data):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SNAPSHOT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(SNAPSHOT_FILE)
    except Exception as e:
        logger.warning(f"health snapshot write: {e}")


def _append_history(data):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        # 环形裁剪
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > _MAX_HISTORY:
            HISTORY_FILE.write_text("\n".join(lines[-_MAX_HISTORY:]) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"health history: {e}")
