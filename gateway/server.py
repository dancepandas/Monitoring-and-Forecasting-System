import asyncio
import logging
import sys
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
from .routes import auth, data, forecast, agent, reports, system, notify, alerts, voice
from .services import scheduler
from .services.monitor_engine import get_engine as get_monitor_engine
from .services.agent_alert_dispatcher import init_dispatcher

_COLLECTOR_LOG = Path(__file__).parent / "data" / "collector.log"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting gateway...")
    if settings.jwt_secret == "change-me":
        logger.critical("SECURITY: jwt_secret is default 'change-me'. Set JWT_SECRET in environment!")
    seed()
    scheduler.init_scheduler(app)
    logger.info("Scheduler initialized")

    # 启动 24x7 值守引擎并注册智能体分发器
    monitor = get_monitor_engine()
    await monitor.start(scheduler.get_scheduler())
    init_dispatcher(monitor)
    logger.info("Monitor engine and alert dispatcher initialized")

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

    # collector 健康监控：每 60 秒检查子进程是否存活
    async def _watch_collector():
        nonlocal collector_proc, log_fh
        while True:
            await asyncio.sleep(60)
            if collector_proc.returncode is not None:
                logger.error(f"[collector] subprocess died (rc={collector_proc.returncode}), restarting...")
                try:
                    collector_proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "gateway.services.collector",
                        stdout=log_fh, stderr=log_fh,
                    )
                    app.state.collector_proc = collector_proc
                    logger.info(f"[collector] restarted: pid={collector_proc.pid}")
                except Exception as e:
                    logger.exception(f"[collector] restart failed: {e}")

    watcher_task = asyncio.create_task(_watch_collector())

    logger.info("Gateway ready on port 15002")
    yield
    logger.info("Gateway shutting down")
    watcher_task.cancel()
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

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gateway"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.server:app", host="0.0.0.0", port=15002, reload=True)
