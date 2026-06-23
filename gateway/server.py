import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from .config import settings
from .seed import seed
from .routes import auth, data, forecast, agent, reports, system, notify, alerts
from .services import scheduler
from .services.monitor_engine import get_engine as get_monitor_engine
from .services.agent_alert_dispatcher import init_dispatcher

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting gateway...")
    seed()
    scheduler.init_scheduler(app)
    logger.info("Scheduler initialized")

    # 启动 24x7 值守引擎并注册智能体分发器
    monitor = get_monitor_engine()
    monitor.start(scheduler.get_scheduler())
    init_dispatcher(monitor)
    logger.info("Monitor engine and alert dispatcher initialized")

    # 把数据收集放到独立子进程，避免 aiflow2 的阻塞 IO/ThreadPoolExecutor 影响主 ASGI 事件循环
    collector_proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "gateway.services.collector",
        stdout=None,
        stderr=None,
    )
    app.state.collector_proc = collector_proc
    logger.info(f"[collector] subprocess started: pid={collector_proc.pid}")

    # collector 健康监控：每 60 秒检查子进程是否存活
    async def _watch_collector():
        while True:
            await asyncio.sleep(60)
            if collector_proc.returncode is not None:
                logger.error(f"[collector] subprocess died (rc={collector_proc.returncode}), restarting...")
                try:
                    new_proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "gateway.services.collector",
                        stdout=None, stderr=None,
                    )
                    app.state.collector_proc = new_proc
                    logger.info(f"[collector] restarted: pid={new_proc.pid}")
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

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gateway"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.server:app", host="0.0.0.0", port=15002, reload=True)
