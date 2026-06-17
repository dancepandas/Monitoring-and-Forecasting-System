import json
import os
import subprocess
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..auth.middleware import get_current_user
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORTS_DIR = Path(settings.reports_dir)


def _parse_filename(filename: str) -> dict | None:
    """Parse report filename like 00106_daily_2026-06-15.docx -> metadata."""
    name = filename.rsplit(".", 1)[0]
    parts = name.split("_")
    if len(parts) >= 3:
        return {
            "station_code": parts[0],
            "type": parts[1],
            "date": parts[2],
        }
    return None


@router.get("/list")
async def list_reports(
    report_type: str = Query(default="", description="日报/daily 复盘/review 设备/device 模型/model"),
    user: dict = Depends(get_current_user),
):
    """列出所有已生成的报告文件，可按类型筛选，按日期倒序。"""
    type_map = {
        "日报": "daily", "daily": "daily",
        "复盘": "review", "review": "review",
        "设备": "device", "device": "device",
        "模型": "model", "model": "model",
    }
    filter_type = type_map.get(report_type, report_type)

    if not REPORTS_DIR.exists():
        return {"reports": [], "total": 0}

    files = []
    for f in sorted(REPORTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_dir():
            continue
        meta = _parse_filename(f.name) or {}
        if filter_type and meta.get("type") != filter_type:
            continue
        files.append({
            "filename": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "station_code": meta.get("station_code", ""),
            "type": meta.get("type", ""),
            "date": meta.get("date", ""),
        })

    return {"reports": files, "total": len(files)}


@router.get("/download/{filename:path}")
async def download_report(filename: str, user: dict = Depends(get_current_user)):
    """下载指定的报告文件。"""
    filepath = REPORTS_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if filename.endswith(".docx") else "text/plain",
    )


@router.get("/preview/{filename:path}")
async def preview_report(filename: str, user: dict = Depends(get_current_user)):
    """预览报告文件的文本内容。docx 会抽取纯文本。"""
    filepath = REPORTS_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    if filename.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(str(filepath))
            lines = []
            for para in doc.paragraphs:
                if para.text.strip():
                    lines.append(para.text.strip())
            return {"filename": filename, "content": "\n\n".join(lines), "type": "docx"}
        except ImportError:
            return {"filename": filename, "content": "（无法预览 docx 文件，请下载后查看）", "type": "docx"}
    else:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        return {"filename": filename, "content": text, "type": "text"}


@router.post("/generate")
async def generate_report_api(body: dict, user: dict = Depends(get_current_user)):
    """在线生成报告。参数: report_type(daily/weekly/monthly), station_code, date(可选,默认昨天)。"""
    report_type = body.get("report_type", "daily")
    station_code = body.get("station_code", "00106")
    date = body.get("date", "")

    cmd = [
        "python", "-m", "gateway.scripts.generate_report",
        "--type", report_type,
        "--station", station_code,
    ]
    if date:
        cmd.extend(["--date", date])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="ignore")
            logger.error(f"generate_report failed: {err}")
            raise HTTPException(status_code=500, detail=err[:500])
        result = json.loads(stdout.decode("utf-8", errors="ignore"))
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="报告生成超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
