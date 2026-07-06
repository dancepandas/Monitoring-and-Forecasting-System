import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from .config import settings
from .seed import seed
from .routes import auth, data, forecast, agent, reports, system, notify, alerts, voice, notify_inbox
from .services import scheduler
from .services.monitor_engine import get_engine as get_monitor_engine
from .services.agent_alert_dispatcher import init_dispatcher
from .services.system_events import init_db

_COLLECTOR_LOG = Path(__file__).parent / "data" / "collector.log"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting gateway...")
    if settings.jwt_secret == "change-me":
        logger.critical("SECURITY: jwt_secret is default 'change-me'. Set JWT_SECRET in environment!")
    seed()
    init_db()
    logger.info("system_events.db initialized")
    sched = None
    try:
        scheduler.init_scheduler(app)
        sched = scheduler.get_scheduler()
        logger.info("Scheduler initialized")
        # 幂等播种 4 类日报的每日自动生成（docx）
        try:
            scheduler.seed_daily_reports()
        except Exception as e:
            logger.warning(f"seed_daily_reports failed (non-fatal): {e}")
    except Exception as e:
        logger.critical(f"Scheduler init failed: {e} — continuing without scheduled tasks")

    # 启动 24x7 值守引擎并注册智能体分发器（scheduler 可能为 None，降级模式）
    monitor = get_monitor_engine()
    if sched is not None:
        await monitor.start(sched)
        logger.info("Monitor engine and alert dispatcher initialized")
    else:
        logger.critical("Monitor engine skipped (no scheduler) — scheduled monitoring disabled")
    init_dispatcher(monitor)

    # 把数据收集放到独立子进程，stdout/stderr 重定向到日志文件以便诊断
    log_fh = open(str(_COLLECTOR_LOG), "a", encoding="utf-8")
    collector_proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "gateway.services.collector",
        stdout=log_fh,
        stderr=log_fh,
    )
    app.state.collector_proc = collector_proc
    app.state.collector_log = log_fh
    logger.info(f"[collector] subprocess started: pid={collector_proc.pid}")

    # collector 健康监控：每 30 秒检查子进程存活 + 心跳文件时效
    # 心跳路径与 collector.py 保持一致（项目根/data/）
    heartbeat_file = Path(__file__).parent / "data" / "collector_heartbeat.txt"
    restart_count = 0  # 连续重启计数，用于退避

    async def _watch_collector():
        nonlocal collector_proc, restart_count
        while True:
            await asyncio.sleep(30)
            needs_restart = False
            # 进程已死 → 重启
            if collector_proc.returncode is not None:
                logger.error(f"[collector] subprocess died (rc={collector_proc.returncode}), restarting...")
                needs_restart = True
            else:
                # 进程存活但心跳过期 → 可能卡死，强制重启
                try:
                    if heartbeat_file.exists():
                        age = time.time() - float(heartbeat_file.read_text().strip())
                        if age > 600:  # 10 分钟无心跳
                            logger.error(f"[collector] heartbeat stale ({age:.0f}s), force restarting...")
                            collector_proc.terminate()
                            try:
                                await asyncio.wait_for(collector_proc.wait(), timeout=5)
                            except Exception:
                                collector_proc.kill()
                                await collector_proc.wait()
                            needs_restart = True
                except Exception as e:
                    logger.warning(f"[collector] heartbeat check failed: {e}")

            if not needs_restart:
                restart_count = 0  # 本轮健康，重置退避计数
                continue

            # 退避保护：连续重启超过 5 次后停止自动重启，仅告警
            restart_count += 1
            if restart_count > 5:
                logger.critical(f"[collector] restarted {restart_count} times, giving up auto-restart (manual intervention needed)")
                continue

            try:
                collector_proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "gateway.services.collector",
                    stdout=log_fh, stderr=log_fh,
                )
                app.state.collector_proc = collector_proc
                logger.info(f"[collector] restarted (attempt {restart_count}): pid={collector_proc.pid}")
            except Exception as e:
                logger.exception(f"[collector] restart failed: {e}")

    watcher_task = asyncio.create_task(_watch_collector())

    logger.info("Gateway ready on port 15002")
    yield
    logger.info("Gateway shutting down")
    watcher_task.cancel()
    # 关闭线程池
    from .services import aiflow_client, agent_alert_dispatcher
    for name, ex in [("aiflow", getattr(aiflow_client, '_executor', None)),
                      ("alert-dispatch", getattr(agent_alert_dispatcher, '_dispatch_executor', None))]:
        if ex:
            logger.info(f"Shutting down {name} executor")
            ex.shutdown(wait=True)
    try:
        collector_proc.terminate()
        await asyncio.wait_for(collector_proc.wait(), timeout=5)
    except Exception:
        collector_proc.kill()
        await collector_proc.wait()
    finally:
        log_fh.close()

app = FastAPI(
    title="水文监测指挥核心 API Gateway",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(data.router)
app.include_router(forecast.router)
app.include_router(agent.router)
app.include_router(reports.router)
app.include_router(system.router)
app.include_router(notify.router)
app.include_router(alerts.router)
app.include_router(voice.router)
app.include_router(notify_inbox.router)

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gateway"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.server:app", host="0.0.0.0", port=15002, reload=True)
