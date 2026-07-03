import json
import logging
import os
from datetime import datetime, timedelta
from .time_utils import parse_ts, default_times
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from ..config import settings
from . import data_cache, system_status, station_names

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


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized")
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


# 启动时幂等播种的稳定 job id 与 cron（错峰避开 0 点 + 防 LLM 并发）
_DAILY_REPORT_SEEDS = [
    ("seed_report_daily",  "generate_report", "3 0 * * *",  {"report_type": "daily"}),
    ("seed_report_review", "generate_report", "8 0 * * *",  {"report_type": "review"}),
    ("seed_report_device", "generate_report", "13 0 * * *", {"report_type": "device"}),
    ("seed_report_model",  "generate_report", "18 0 * * *", {"report_type": "model"}),
]


def seed_daily_reports():
    """启动时幂等注册 4 类日报的每日自动生成任务（docx）。

    - 清掉旧的 agent_daily_report 任务（产出单薄 txt，已弃用）
    - 用稳定 job id + replace_existing 保证不重复注册
    """
    if _scheduler is None:
        logger.warning("seed_daily_reports skipped — scheduler not initialized")
        return
    # 清理旧的单薄 txt daily 任务
    for j in list(_scheduler.get_jobs()):
        if j.kwargs.get("task_type") == "agent_daily_report":
            try:
                _scheduler.remove_job(j.id)
                logger.info("removed stale thin-txt daily job: %s", j.id)
            except Exception:
                pass
    for job_id, task_type, cron, params in _DAILY_REPORT_SEEDS:
        if _scheduler.get_job(job_id) is None:
            _scheduler.add_job(
                _execute_task,
                trigger=CronTrigger.from_crontab(cron),
                id=job_id,
                replace_existing=True,
                kwargs={"task_type": task_type, "params": params},
            )
            logger.info("seeded daily report job: %s (%s %s)", job_id, task_type, cron)


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
            # 调度归档约定：未指定 date → 取昨日（00:0X 跑出的是刚结束那一天）；按需路由会显式传今天
            date = params.get("date", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
            cmd = ["python", "-m", "gateway.scripts.generate_report", "--type", params.get("report_type", "daily"), "--date", date]
            station = params.get("station_code", "")
            if station:
                cmd.extend(["--station", station])
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
                logger.info(f"generate_report finished: rc={proc.returncode}")
                if stderr: logger.warning(f"generate_report stderr: {stderr.decode('utf-8', errors='ignore')[:500]}")
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait()
                logger.error("generate_report timed out after 120s")
        elif task_type == "run_forecast":
            station = params.get("station_code", settings.station_codes.split(",")[0] if settings.station_codes else "00106")
            try:
                await data_cache.rebuild_aligned(station)
                logger.info("scheduled forecast: aligned rebuilt for %s", station)
            except Exception as e:
                logger.exception("scheduled forecast failed for %s: %s", station, e)
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


def _device(code: str) -> str:
    return station_names.station_device(code) or settings.default_device_code


async def _run_agent_daily_report(params: dict):
    """日报（agent 触发/重试）：委托给 generate_report 统一 docx 生成器（数据表 + LLM 综述 + 全站名）。

    全部文档一律存 docx，不再产出 txt。
    """
    from gateway.scripts.generate_report import generate_report
    date = params.get("date") or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = await generate_report("daily", None, date)
    logger.info(f"daily report saved: {result.get('filename')}")


def _read_daily_text(reports_dir: Path, date_str: str) -> str:
    """读取某日日报文本：docx 优先（抽段落），txt 兼容旧文件。无则返回占位。"""
    docx_path = reports_dir / f"daily_{date_str}.docx"
    if docx_path.exists():
        try:
            from docx import Document
            doc = Document(str(docx_path))
            lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n".join(lines)[:2000] if lines else "（该日日报为空）"
        except Exception as e:
            logger.warning(f"read daily docx {date_str} failed: {e}")
    txt_path = reports_dir / f"daily_{date_str}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")[:2000]
    return "（该日无日报）"


def _save_llm_docx(filepath: Path, title: str, info_line: str, body_text: str):
    """把 LLM 生成的 markdown 风格文本存为 docx（## / ### 解析为标题）。全部文档一律 docx，不存 txt。"""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    t = doc.add_heading(title, level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if info_line:
        info = doc.add_paragraph()
        info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        info.add_run(info_line).font.size = Pt(10)

    for raw in (body_text or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=2)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=1)
        elif line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=0)
        else:
            doc.add_paragraph(line)
    doc.save(filepath)


async def _run_agent_weekly_report(params: dict):
    """周报：读取最近 7 天的日报（docx 优先，txt 兼容） → LLM 汇总 → 存 txt。"""
    today = datetime.now()
    reports_dir = Path(settings.reports_dir)

    # 收集过去 7 天的日报内容
    daily_texts = []
    for i in range(7):
        d = (today - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        daily_texts.append(f"=== {d} ===\n{_read_daily_text(reports_dir, d)}")

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

    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_{week_start}_{week_end}.docx"
    _save_llm_docx(reports_dir / filename, "水文监测周报",
                   f"周期: {week_start} ~ {week_end}　|　覆盖站点: {', '.join(STATIONS)}", report_body)
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
        flow_raw = await data_cache.get(f"aiflow:flow_raw:{code}:{_device(code)}", max_age=600)
        flow_items = (flow_raw.get("data", []) or []) if flow_raw else []
        level_items = (level_ok.get("data", []) or []) if level_ok else []

        last_time = ""
        age_h = 0
        if flow_items:
            last_time = str(flow_items[0].get("measureTime", ""))
            ts = parse_ts(last_time)
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


async def _call_llm(prompt, data_fallback, date):
    """调 LLM 生成报告正文，不可达时返回纯数据版本。"""
    from .agent_utils import quick_ask
    text = await quick_ask(prompt, max_tokens=settings.agent_max_tokens)
    if text:
        return text
    return f"""{data_fallback}

---
（LLM 不可用，以上为原始数据汇总）"""


