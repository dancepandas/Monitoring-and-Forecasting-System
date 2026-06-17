"""系统诊断状态 — 统一所有诊断路径（定时/异常触发/手动）的结果存储。"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_FILE = Path(__file__).parent.parent / "data" / "system_status.json"
_lock = threading.Lock()

DEFAULT_STATUS = {
    "checked_at": "",
    "trigger": "init",
    "diagnosis": "unknown",
    "summary": "系统状态未知，尚未完成首次自检。",
    "issues": [],
    "stations": [],
}


def _load() -> dict:
    if not STATUS_FILE.exists():
        return dict(DEFAULT_STATUS)
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_STATUS)


def _save(data: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = STATUS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        tmp.replace(STATUS_FILE)
    except Exception as e:
        logger.warning(f"save system_status failed: {e}")


def get_status() -> dict:
    with _lock:
        return _load()


def update_status(trigger: str, diagnosis: str, summary: str, stations: list, issues: list):
    """由调度器/agent 工具/异常触发路径调用，写入诊断结果。"""
    data = {
        "checked_at": datetime.now().isoformat(),
        "trigger": trigger,
        "diagnosis": diagnosis,
        "summary": summary,
        "issues": issues,
        "stations": stations,
    }
    with _lock:
        _save(data)
    logger.info("system_status updated: trigger=%s diagnosis=%s issues=%d", trigger, diagnosis, len(issues))
