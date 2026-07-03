from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from ...config import settings
from ._helpers import _safe_sync, _get_cached_records
from ..time_utils import parse_ts
# 6.5 系统自诊断与自愈
# ---------------------------------------------------------------------------

class DiagnoseSystemArgs(BaseModel):
    """系统诊断：检查所有站点缓存状态、数据时效。"""

def diagnose_system(**kwargs) -> dict:
    """诊断系统缓存状态，判断是单站故障还是全局故障。"""
    import time as _time
    DiagnoseSystemArgs(**kwargs)
    codes = [s.strip() for s in settings.station_codes.split(",")]
    now_ts = _time.time()
    stations_result = []

    for code in codes:
        records = _safe_sync(_get_cached_records(code, max_age=600)) or []

        last_time = str(records[0].get("measureTime", "")) if records else ""
        ts = parse_ts(last_time)
        age_h = (now_ts - ts) / 3600 if ts else 0

        null_count = sum(1 for it in records[:10] if it.get("virtualFlow") is None)

        stations_result.append({
            "station_code": code,
            "level_records": sum(1 for r in records if r.get("waterLevel") is not None),
            "flow_records": sum(1 for r in records if (r.get("virtualFlow") or r.get("waterFlow")) is not None),
            "last_data_time": last_time,
            "data_age_hours": round(age_h, 1),
            "recent_nulls": null_count,
            "status": "healthy" if records and age_h < 2 else "warning" if age_h < 4 else "critical" if records else "no_data",
        })

    all_empty = all(s["flow_records"] == 0 for s in stations_result)
    diagnosis = "global_failure" if all_empty else \
                "partial_failure" if any(s["status"] == "critical" for s in stations_result) else \
                "degraded" if any(s["status"] == "warning" for s in stations_result) else \
                "healthy"

    conclusion_map = {
        "global_failure": "全部站点无数据，疑似 aiflow2 数据平台整体故障或 collector 进程停止。请联系管理员检查 aiflow2 服务和 collector 进程。",
        "partial_failure": "部分站点数据严重停更，可能是对应站点的遥测终端或 aiflow2 数据链路故障。建议排查具体站点设备。",
        "degraded": "部分站点数据略有延迟或少量缺测，系统整体可用但需关注。",
        "healthy": "所有站点数据正常，缓存有效，系统运行正常。",
    }

    return {
        "diagnosis": diagnosis,
        "conclusion": conclusion_map.get(diagnosis, ""),
        "stations": stations_result,
        "checked_at": datetime.now().isoformat(),
    }

class RetryFailedReportsArgs(BaseModel):
    """重试生成失败的日报/周报。"""
    report_type: str = Field(default="daily", description="daily 或 weekly")
    date: str = Field(default="", description="日期 YYYY-MM-DD，空则默认昨天")

def retry_failed_reports(**kwargs) -> dict:
    """重试失败的报告生成。日报默认重试昨天的，周报重试过去一周。"""
    from .. import scheduler as _sched
    args = RetryFailedReportsArgs(**kwargs)

    if args.report_type == "daily":
        param = {"date": args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")}
        task_type = "agent_daily_report"
    else:
        param = {}
        task_type = "agent_weekly_report"

    try:
        _safe_sync(_sched._retry(
            lambda: _sched._run_agent_daily_report(param) if task_type == "agent_daily_report"
                   else _sched._run_agent_weekly_report(param),
            f"retry_{task_type}",
            max_retries=1, delay=5
        ))
        return {"success": True, "report_type": args.report_type, "message": f"{args.report_type} 重试成功"}
    except Exception as e:
        return {"success": False, "report_type": args.report_type, "error": str(e), "message": f"重试失败: {e}。建议检查缓存数据是否可用，或联系管理员手动生成。"}

# ---------------------------------------------------------------------------