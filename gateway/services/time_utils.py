"""共享时间工具 —— 全项目统一的时间解析和默认时间范围。"""

from datetime import datetime


def parse_ts(t) -> float:
    """解析字符串或字典格式的时间为 Unix timestamp。

    支持: ISO 字符串、aiflow2 字典格式 {year, month, day, hours, minutes, seconds}。
    """
    if not t:
        return 0
    if isinstance(t, dict):
        try:
            return datetime(
                t.get("year", 2000), t.get("month", 1), t.get("day", 1),
                t.get("hours", 0), t.get("minutes", 0), t.get("seconds", 0)
            ).timestamp()
        except Exception:
            return 0
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(t), fmt).timestamp()
        except Exception:
            pass
    return 0


def default_times() -> tuple[str, str]:
    """返回今天 00:00:00 到 23:59:59 的时间范围字符串。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    return f"{today} 00:00:00.000", f"{today} 23:59:59.999"
