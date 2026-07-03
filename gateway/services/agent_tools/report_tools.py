import json
import logging

logger = logging.getLogger(__name__)
import subprocess
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ...config import settings
# 4. 报告（2 个）
# ---------------------------------------------------------------------------

class GenerateReportArgs(BaseModel):
    report_type: str = Field(default="daily", description="报告类型：daily / weekly / monthly")
    station_code: str = Field(default="", description="测站编码（可选，留空则覆盖全部站点）")
    date: str = Field(default="", description="日期，如 2026-06-15")

def generate_report(**kwargs) -> dict:
    args = GenerateReportArgs(**kwargs)
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    cmd = [
        "python", "-m", "gateway.scripts.generate_report",
        "--type", args.report_type,
        "--date", date,
    ]
    if args.station_code:
        cmd.extend(["--station", args.station_code])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"generate_report subprocess failed: {result.stderr}")
            return {"error": result.stderr, "cmd": " ".join(cmd)}
        output = json.loads(result.stdout)
        return output
    except Exception as ex:
        logger.error(f"generate_report exception: {ex}")
        return {"error": str(ex), "cmd": " ".join(cmd)}

class QueryReportsArgs(BaseModel):
    pass

def query_reports(**kwargs) -> dict:
    QueryReportsArgs(**kwargs)
    reports_dir = Path(settings.reports_dir)
    if not reports_dir.exists():
        return {"reports": []}
    files = sorted(reports_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "reports": [
            {
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
            for f in files
        ]
    }

# ---------------------------------------------------------------------------