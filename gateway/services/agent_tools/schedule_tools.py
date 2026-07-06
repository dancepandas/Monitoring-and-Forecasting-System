
from pydantic import BaseModel, Field

# 6. 定时任务（3 个）
# ---------------------------------------------------------------------------

class CreateScheduledTaskArgs(BaseModel):
    task_type: str = Field(..., description="任务类型：generate_report / run_forecast")
    cron: str = Field(..., description="cron 表达式，如 0 9 * * *")
    params: dict = Field(default_factory=dict, description="任务参数 JSON")

def create_scheduled_task(**kwargs) -> dict:
    args = CreateScheduledTaskArgs(**kwargs)
    from .. import scheduler
    task_id = scheduler.create_task(args.task_type, args.cron, args.params)
    return {"task_id": task_id, "task_type": args.task_type, "cron": args.cron}

class ListScheduledTasksArgs(BaseModel):
    pass

def list_scheduled_tasks(**kwargs) -> dict:
    ListScheduledTasksArgs(**kwargs)
    from .. import scheduler
    tasks = scheduler.list_tasks()
    return {"tasks": tasks}

class CancelScheduledTaskArgs(BaseModel):
    task_id: str = Field(..., description="任务 ID")

def cancel_scheduled_task(**kwargs) -> dict:
    args = CancelScheduledTaskArgs(**kwargs)
    from .. import scheduler
    ok = scheduler.cancel_task(args.task_id)
    return {"success": ok, "task_id": args.task_id}

# ---------------------------------------------------------------------------