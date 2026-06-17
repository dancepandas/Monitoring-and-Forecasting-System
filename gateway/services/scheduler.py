import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from ..config import settings
from . import data_cache, warning_config, system_status

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def init_scheduler(app=None) -> AsyncIOScheduler:
    global _scheduler
    db_path = settings.scheduled_tasks_db
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    jobstores = {
        "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}"),
    }
    _scheduler = AsyncIOScheduler(jobstores=jobstores)
    _scheduler.start()
    logger.info(f"Scheduler started with db: {db_path}")
    if app:
        app.state.scheduler = _scheduler
    return _scheduler


def create_task(task_type: str, cron: str, params: dict) -> str:
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized")
    job = _scheduler.add_job(
        _execute_task,
        trigger=CronTrigger.from_crontab(cron),
        id=f"{task_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        replace_existing=True,
        kwargs={"task_type": task_type, "params": params},
    )
    return job.id


def list_tasks(session_id=None) -> list[dict]:
    if _scheduler is None:
        return []
    jobs = _scheduler.get_jobs()
    result = []
    for job in jobs:
        result.append(
            {
                "task_id": job.id,
                "task_type": job.kwargs.get("task_type", "unknown"),
                "params": job.kwargs.get("params", {}),
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )
    return result


def cancel_task(task_id: str) -> bool:
    if _scheduler is None:
        return False
    try:
        _scheduler.remove_job(task_id)
        return True
    except Exception:
        return False


import asyncio

async def _execute_task(task_type: str, params: dict) -> None:
    logger.info(f"Executing scheduled task: {task_type} with params {params}")
    try:
        if task_type == "agent_daily_report":
            await _retry(lambda: _run_agent_daily_report(params), "agent_daily_report")
        elif task_type == "agent_weekly_report":
            await _retry(lambda: _run_agent_weekly_report(params), "agent_weekly_report")
        elif task_type == "agent_system_check":
            await _run_system_check(params)
        elif task_type == "generate_report":
            station = params.get("station_code", settings.station_codes.split(",")[0] if settings.station_codes else "00106")
            date = params.get("date", datetime.now().strftime("%Y-%m-%d"))
            cmd = ["python", "-m", "gateway.scripts.generate_report", "--type", params.get("report_type", "daily"), "--station", station, "--date", date]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                logger.info(f"generate_report finished: rc={proc.returncode}")
                if stderr: logger.warning(f"generate_report stderr: {stderr.decode('utf-8', errors='ignore')[:500]}")
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait()
                logger.error("generate_report timed out after 120s")
        elif task_type == "run_forecast":
            station = params.get("station_code", settings.station_codes.split(",")[0] if settings.station_codes else "00106")
            prediction_length = params.get("prediction_length", 72)
            flow_data = await data_cache.get(f"aiflow:flow_raw:{station}:{settings.default_device_code}", max_age=600)
            raw_items = (flow_data or {}).get("data", []) or []
            if raw_items:
                series = _time_series_for_forecast(raw_items, "virtualFlow")
                if len(series) >= 10:
                    from . import chronos_client
                    await chronos_client.predict_flow(series, prediction_length, context_length=min(len(series), 72))
        elif task_type == "check_warnings":
            logger.info("check_warnings: placeholder – no action yet")
        else:
            logger.warning(f"Unknown task_type: {task_type}")
    except Exception as e:
        logger.exception(f"Scheduled task {task_type} failed: {e}")


async def _retry(fn, name, max_retries=2, delay=30):
    """重试逻辑：日报/周报生成失败时自动重试 2 次，间隔 30 秒。"""
    for i in range(max_retries + 1):
        try:
            await fn()
            return
        except Exception as e:
            if i < max_retries:
                logger.warning(f"{name} failed (attempt {i+1}/{max_retries+1}): {e}, retrying in {delay}s")
                await asyncio.sleep(delay)
            else:
                logger.error(f"{name} failed after {max_retries+1} attempts: {e}")
                raise


STATIONS = [s.strip() for s in settings.station_codes.split(",")]
DEVICE = settings.default_device_code


async def _collect_all_data():
    """从缓存采集系统中所有站点的全部数据。"""
    standards = warning_config.get_standards()
    stations_info = []

    for code in STATIONS:
        # 水位
        level = await data_cache.get(f"aiflow:level:{code}", max_age=600)
        level_items = (level.get("data", []) or []) if level else []
        wl_vals = [float(it["waterLevel"]) for it in level_items if it.get("waterLevel") is not None]
        # fallback: 用 flow_raw 里的 waterLevel 补
        if not wl_vals:
            flow = await data_cache.get(f"aiflow:flow_raw:{code}:{DEVICE}", max_age=600)
            if flow:
                for it in (flow.get("data", []) or []):
                    wl = it.get("waterLevel")
                    if wl is not None:
                        wl_vals.append(float(wl))

        # 流量
        flow = await data_cache.get(f"aiflow:flow_raw:{code}:{DEVICE}", max_age=600)
        flow_items = (flow.get("data", []) or []) if flow else []
        flow_vals = [float(it["virtualFlow"]) for it in flow_items if it.get("virtualFlow") is not None]

        # 预警
        warn_list = []
        latest_wl = wl_vals[-1] if wl_vals else None
        if latest_wl:
            lv = warning_config.check_level(latest_wl, standards)
            if lv:
                warn_list.append(f"水位{lw_name(lv)}: {latest_wl:.2f}m")
        latest_flow = flow_vals[-1] if flow_vals else None
        if latest_flow:
            lv = warning_config.check_flow(latest_flow, standards)
            if lv:
                warn_list.append(f"流量{lw_name(lv)}: {latest_flow:.0f}m³/s")

        stations_info.append({
            "code": code,
            "wl_max": f"{max(wl_vals):.2f}" if wl_vals else "—",
            "wl_min": f"{min(wl_vals):.2f}" if wl_vals else "—",
            "wl_avg": f"{sum(wl_vals)/len(wl_vals):.2f}" if wl_vals else "—",
            "wl_latest": f"{wl_vals[-1]:.2f}m ({level_items[-1].get('measureTime','')})" if wl_vals and level_items else "—",
            "flow_max": f"{max(flow_vals):.0f}" if flow_vals else "—",
            "flow_min": f"{min(flow_vals):.0f}" if flow_vals else "—",
            "flow_avg": f"{sum(flow_vals)/len(flow_vals):.0f}" if flow_vals else "—",
            "flow_latest": f"{flow_vals[-1]:.0f}m³/s ({flow_items[-1].get('measureTime','')})" if flow_vals and flow_items else "—",
            "warnings": "、".join(warn_list) if warn_list else "无",
        })

    return stations_info, standards


async def _run_agent_daily_report(params: dict):
    """日报：读取系统全部站点水位/流量/预警 → LLM 整理 → 存 txt。"""
    date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    stations_info, standards = await _collect_all_data()

    # 构建数据上下文
    lines = [f"## 系统全量数据 ({date})"]
    for s in stations_info:
        lines.append(f"### {s['code']}站")
        lines.append(f"水位: 最新 {s['wl_latest']} | 最高 {s['wl_max']}m 最低 {s['wl_min']}m 平均 {s['wl_avg']}m")
        lines.append(f"流量: 最新 {s['flow_latest']} | 最大 {s['flow_max']}m³/s 最小 {s['flow_min']}m³/s 平均 {s['flow_avg']}m³/s")
        lines.append(f"预警: {s['warnings']}")
    lines.append(f"\n预警阈值: 水位 {standards.get('level',{})} | 流量 {standards.get('flow',{})}")

    data_context = "\n".join(lines)

    prompt = f"""你是专业水文日报编辑。根据以下全系统监测数据，生成一份完整日报。

{data_context}

请用以下格式直接输出（不要加```标记）：

## 水文监测日报
**日期**: {date}
**覆盖站点**: {', '.join(STATIONS)}

### 一、全流域水情综述
（2-3 句话概括当天水情）

### 二、各站水情
（按站点分节，简述各站水位/流量特征）

### 三、预警与处置
（当天预警触发情况及级别）

### 四、设备与视频巡检
（汇总设备在线情况）

### 五、关注要点与建议
（次日需关注 2-3 条）"""

    report_body = await _call_llm(prompt, data_context, date)

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_{date}.txt"
    (reports_dir / filename).write_text(report_body, encoding="utf-8")
    logger.info(f"daily report saved: {filename}")


async def _run_agent_weekly_report(params: dict):
    """周报：读取最近 7 天的日报 txt → LLM 汇总 → 存 txt。"""
    today = datetime.now()
    reports_dir = Path(settings.reports_dir)

    # 收集过去 7 天的日报内容
    daily_texts = []
    for i in range(7):
        d = (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        filepath = reports_dir / f"daily_{d}.txt"
        if filepath.exists():
            daily_texts.append(f"=== {d} ===\n{filepath.read_text(encoding='utf-8')[:2000]}")
        else:
            daily_texts.append(f"=== {d} ===\n（该日无日报）")

    week_data = "\n\n".join(daily_texts)
    week_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    prompt = f"""你是专业水文周报编辑。以下是过去 7 天各日日报内容。请汇总为一份周报。

{week_data}

请按以下格式输出：

## 水文监测周报
**周期**: {week_start} ~ {week_end}
**覆盖站点**: {', '.join(STATIONS)}

### 一、本周水情综述
（汇总 7 天水情整体趋势）

### 二、关键事件
（预警触发、极端值、设备异常等，按时间列出）

### 三、趋势分析
（水位/流量周变化趋势，与上周对比）

### 四、下周风险研判
（基于趋势给出下周关注要点）"""

    report_body = await _call_llm(prompt, week_data, week_end)

    filename = f"weekly_{week_start}_{week_end}.txt"
    (reports_dir / filename).write_text(report_body, encoding="utf-8")
    logger.info(f"weekly report saved: {filename}")


async def _run_system_check(params: dict):
    """系统自检：诊断所有站点缓存状态，写入 system_status.json。"""
    import time as _time
    trigger = params.get("trigger", "scheduled")
    now_ts = _time.time()
    stations_result = []
    issues_list = []

    for code in STATIONS:
        level_ok = await data_cache.get(f"aiflow:level:{code}", max_age=600)
        flow_raw = await data_cache.get(f"aiflow:flow_raw:{code}:{DEVICE}", max_age=600)
        flow_items = (flow_raw.get("data", []) or []) if flow_raw else []
        level_items = (level_ok.get("data", []) or []) if level_ok else []

        last_time = ""
        age_h = 0
        if flow_items:
            last_time = str(flow_items[0].get("measureTime", ""))
            ts = _parse_ts(last_time)
            age_h = (now_ts - ts) / 3600 if ts else 0

        null_count = sum(1 for it in flow_items[:10] if it.get("virtualFlow") is None)

        if age_h > 4:
            status = "critical"
            issues_list.append(f"测站 {code} 数据严重停更 {age_h:.1f}h")
        elif age_h > 2:
            status = "warning"
            issues_list.append(f"测站 {code} 数据 {age_h:.1f}h 未更新")
        elif not flow_items and not level_items:
            status = "no_data"
            issues_list.append(f"测站 {code} 全站数据不可用")
        else:
            status = "healthy"

        stations_result.append({
            "station_code": code, "status": status,
            "level_records": len(level_items), "flow_records": len(flow_items),
            "last_data_time": last_time, "data_age_hours": round(age_h, 1),
        })

    all_empty = all(s["flow_records"] == 0 for s in stations_result)
    if all_empty:
        diagnosis = "global_failure"
        summary = "全部站点数据不可用，疑似 aiflow2 数据平台整体故障或 collector 进程停止。请联系管理员排查。"
    elif any(s["status"] == "critical" for s in stations_result):
        diagnosis = "partial_failure"
        summary = f"部分站点数据严重停更：{'；'.join(issues_list)}。建议排查对应站点的遥测终端或数据链路。"
    elif any(s["status"] == "warning" for s in stations_result):
        diagnosis = "degraded"
        summary = "部分站点数据略有延迟，系统整体可用但需关注。"
    else:
        diagnosis = "healthy"
        summary = "系统自检正常，所有站点数据可用。"

    system_status.update_status(trigger, diagnosis, summary, stations_result, issues_list)

    if diagnosis != "healthy":
        log_path = Path(settings.reports_dir) / "system_check.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {diagnosis}: {summary}\n")

    logger.info("system_check done: %s, %d issues", diagnosis, len(issues_list))


def _parse_ts(t) -> float:
    """解析时间字符串为 Unix timestamp"""
    if not t: return 0
    if isinstance(t, dict): return 0
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try: return datetime.strptime(str(t), fmt).timestamp()
        except: pass
    return 0


async def _call_llm(prompt, data_fallback, date):
    """调 LLM 生成报告正文，不可达时返回纯数据版本。"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{settings.dashscope_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
                json={"model": settings.agent_model_name, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.3, "max_tokens": settings.agent_max_tokens},
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            logger.warning(f"LLM failed: {r.status_code}")
    except Exception as e:
        logger.warning(f"LLM error: {e}")

    return f"""{data_fallback}

---
（LLM 不可用，以上为原始数据汇总）"""


def lw_name(lv):
    return {"blue": "蓝", "yellow": "黄", "orange": "橙", "red": "红"}.get(lv, lv)


def _time_series_for_forecast(raw_data: list, value_key: str, time_key: str = "measureTime") -> list[dict]:
    result = []
    for item in (raw_data or []):
        t = item.get(time_key)
        if isinstance(t, dict):
            t = f"{t.get('year','')}-{str(t.get('month','')).zfill(2)}-{str(t.get('day','')).zfill(2)} {str(t.get('hours','')).zfill(2)}:{str(t.get('minutes','')).zfill(2)}"
        v = item.get(value_key)
        if t and v is not None:
            result.append({"Time": str(t), "Flow": float(v)})
    return result
