"""统一日报生成器 —— 四类报告共用同一套 docx 骨架：

标题 + 日期 → 一、LLM 综述 → 二、真实数据明细表 → 三、异常/未处置清单 → 四、LLM 关注要点

全文用站点名（不用编码）；LLM 不可用时「综述/要点」自动回退为原始数据句。
所有报告一律存 docx（Word），不存 txt。支持类型: daily / review / device / model
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gateway.config import settings
from gateway.services import data_cache, station_names, station_collector
from gateway.services.system_events import write_event
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ALL_STATIONS = list(station_names.ALL_CODES)


# ─────────────────────────── LLM 叙述（不可用回退原始数据） ───────────────────────────

async def _llm(prompt: str, fallback: str) -> str:
    """调 LLM 生成一段叙述，失败/不可达时返回 fallback 原始数据句。"""
    try:
        from gateway.services.agent_utils import quick_ask
        text = await quick_ask(prompt)
        return text.strip() if text and text.strip() else fallback
    except Exception as e:
        logger.warning(f"LLM narrate failed, using fallback: {e}")
        return fallback


# ─────────────────────────── docx 公共构建工具 ───────────────────────────

def _new_doc(title: str, info_line: str):
    """新建 docx，写入居中标题 + 信息行。"""
    doc = Document()
    t = doc.add_heading(title, level=0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = info.add_run(info_line)
    run.font.size = Pt(10)
    return doc


def _add_table(doc, headers: list, rows: list, style: str = "Light Grid Accent 1"):
    """添加一个带表头的数据表。rows 为 list[list]。"""
    table = doc.add_table(rows=1, cols=len(headers))
    try:
        table.style = style
    except KeyError:
        pass
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    doc.add_paragraph("")  # 间隔
    return table


def _fmt_ts(ts) -> str:
    """unix 时间戳 → 'MM-DD HH:MM'，无效返回 '—'。"""
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return "—"


# ════════════════════════════ daily（流域运行日报） ════════════════════════════

async def _gen_daily(date_str: str, station_code=None) -> dict:
    stations_to_report = [station_code] if station_code else ALL_STATIONS
    station_reports = []
    all_wl, all_flow = [], []
    total_wl_count = total_flow_count = 0

    for code in stations_to_report:
        sd = await station_collector.collect_station_data(code)
        wl_vals, flow_vals = sd["wl_vals"], sd["flow_vals"]
        level_items, flow_items = sd["level_items"], sd["flow_items"]
        name = sd["name"]
        total_wl_count += len(wl_vals)
        total_flow_count += len(flow_vals)
        all_wl.extend(wl_vals)
        all_flow.extend(flow_vals)
        station_reports.append({
            "code": code, "name": name,
            "wl_count": len(wl_vals), "flow_count": len(flow_vals),
            "wl_values": wl_vals, "flow_values": flow_vals,
            "latest_wl": f"{wl_vals[-1]:.2f}m" if wl_vals else "—",
            "latest_flow": f"{flow_vals[-1]:.0f}m³/s" if flow_vals else "—",
            "wl_range": f"{min(wl_vals):.2f} ~ {max(wl_vals):.2f}m" if wl_vals else "—",
            "flow_range": f"{min(flow_vals):.0f} ~ {max(flow_vals):.0f}m³/s" if flow_vals else "—",
            "level_items": level_items, "flow_items": flow_items,
        })

    # ── 原始数据兜底句（LLM 不可用时用） ──
    fb_overview = "、".join(filter(None, [
        f"覆盖 {len(stations_to_report)} 个站点" if stations_to_report else "",
        f"水位范围 {min(all_wl):.2f}~{max(all_wl):.2f}m" if all_wl else "",
        f"流量范围 {min(all_flow):.0f}~{max(all_flow):.0f}m³/s" if all_flow else "",
        f"共水位 {total_wl_count} 条、流量 {total_flow_count} 条",
    ])) or "当日无可用数据。"

    # ── LLM 综述 ──
    ctx = "\n".join(
        f"- {s['name']}：最新水位 {s['latest_wl']}（区间 {s['wl_range']}，{s['wl_count']} 条），"
        f"最新流量 {s['latest_flow']}（区间 {s['flow_range']}，{s['flow_count']} 条）"
        for s in station_reports
    )
    overview = await _llm(
        f"你是水文值班编辑。下面是 {date_str} 各站实测数据，请用 2~4 句话写一段「全流域水情综述」，"
        f"概括整体水情、突出极值与异常站点，用站点名（不要出现编码），直接输出正文：\n{ctx}",
        fb_overview,
    )

    # ── LLM 关注要点 ──
    notes_fb = []
    if all_wl:
        mx = max(station_reports, key=lambda s: max(s["wl_values"]) if s["wl_values"] else -1e9)
        notes_fb.append(f"• 最高水位出现在 {mx['name']}（{max(all_wl):.2f}m）")
    if all_flow:
        mx = max(station_reports, key=lambda s: max(s["flow_values"]) if s["flow_values"] else -1e9)
        notes_fb.append(f"• 最大流量出现在 {mx['name']}（{max(all_flow):.0f}m³/s）")
    inactive = [s["name"] for s in station_reports if s["wl_count"] == 0 and s["flow_count"] == 0]
    if inactive:
        notes_fb.append(f"• 关注无数据站点：{('、'.join(inactive))}")
    if not notes_fb:
        notes_fb.append("• 当日水情平稳，无特别关注事项。")
    notes = await _llm(
        f"基于以下 {date_str} 各站数据，给出 2~4 条「关注要点与建议」，用站点名，直接输出要点：\n{ctx}",
        "\n".join(notes_fb),
    )

    active = [s for s in station_reports if s["wl_count"] > 0 or s["flow_count"] > 0]
    inactive_stations = [s["name"] for s in station_reports if s["wl_count"] == 0 and s["flow_count"] == 0]

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_{date_str}_{station_code}.docx" if station_code else f"daily_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("水文监测日报",
                   f"日期: {date_str}　|　覆盖站点: {len(stations_to_report)} 个　|　生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_heading("一、全流域水情综述", level=1)
    doc.add_paragraph(overview)
    doc.add_heading("二、各站水情", level=1)
    for sr in station_reports:
        doc.add_heading(sr["name"], level=2)
        doc.add_paragraph(
            f"水位: 最新 {sr['latest_wl']}，区间 {sr['wl_range']}（{sr['wl_count']} 条记录）\n"
            f"流量: 最新 {sr['latest_flow']}，区间 {sr['flow_range']}（{sr['flow_count']} 条记录）"
        )
        if sr["wl_values"]:
            doc.add_paragraph("水位明细：")
            _add_table(doc, ["时间", "水位 (m)"],
                       [[it.get("measureTime", ""), it.get("waterLevel", "")] for it in sr["level_items"][:30]])
    doc.add_heading("三、设备与数据质量", level=1)
    doc.add_paragraph(f"数据活跃站点: {len(active)}/{len(stations_to_report)}")
    doc.add_paragraph(f"无数据站点: {('、'.join(inactive_stations)) if inactive_stations else '无'}")
    doc.add_heading("四、关注要点", level=1)
    doc.add_paragraph(notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    summary = f"{date_str} {len(stations_to_report)} 站 · 水位 {total_wl_count} 条 · 流量 {total_flow_count} 条"
    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size, "summary": summary}


# ════════════════════════════ review（预警处置复盘） ════════════════════════════

async def _collect_alerts(limit: int = 1000) -> list:
    """从 AlertTracker 读取近期告警（含已处置/未解除）。"""
    from gateway.services.alert_tracker import AlertTracker
    tracker = AlertTracker()
    await tracker.load()
    return await tracker.list_all(limit=limit)


def _alert_rows(alerts: list) -> list:
    rows = []
    for a in alerts:
        disposed = "是" if a.resolved_at else ("已确认" if a.acknowledged else "否")
        rows.append([
            station_names.station_name(a.station_code) or a.station_code,
            a.level, a.alert_type, _fmt_ts(a.triggered_at),
            disposed, _fmt_ts(a.resolved_at), (a.resolution or "—")[:40],
        ])
    return rows


async def _gen_review(date_str: str) -> dict:
    alerts = await _collect_alerts()
    # 仅统计本日触发的告警；当日无则用全部近期告警兜底
    day_start = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
    day_end = day_start + 86400
    day_alerts = [a for a in alerts if day_start <= (a.triggered_at or 0) <= day_end] or alerts
    unresolved = [a for a in day_alerts if not a.resolved_at]
    disposed = [a for a in day_alerts if a.resolved_at]

    level_count = {}
    for a in day_alerts:
        level_count[a.level] = level_count.get(a.level, 0) + 1
    level_str = "、".join(f"{k}{v}条" for k, v in level_count.items()) or "无"

    fb = (f"本日共告警 {len(day_alerts)} 条（{level_str}），已处置 {len(disposed)} 条，"
          f"未解除 {len(unresolved)} 条。")
    ctx = "\n".join(
        f"- {station_names.station_name(a.station_code)}|{a.level}|{a.alert_type}|"
        f"触发{_fmt_ts(a.triggered_at)}|{'已处置' if a.resolved_at else '未解除'}|{(a.resolution or '')[:30]}"
        for a in day_alerts[:40]
    ) or "（本日无告警）"
    overview = await _llm(
        f"你是水文预警复盘编辑。以下是 {date_str} 的告警记录，请用 2~4 句话写「复盘综述」，"
        f"概括告警规模、响应是否及时、有无遗留，用站点名，直接输出正文：\n{ctx}",
        fb,
    )
    notes = await _llm(
        f"基于以下 {date_str} 告警数据，给出 2~3 条「关注要点」（处置改进/未解除跟进），用站点名：\n{ctx}",
        "• 建议持续关注未解除告警并完善处置记录。" if unresolved else "• 当日告警均已妥善处置。",
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"review_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("预警处置复盘日报",
                   f"日期: {date_str}　|　告警 {len(day_alerts)} 条　|　已处置 {len(disposed)} · 未解除 {len(unresolved)}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、复盘综述", level=1)
    doc.add_paragraph(overview)
    doc.add_heading("二、告警明细", level=1)
    if day_alerts:
        _add_table(doc, ["站点", "级别", "类型", "触发时间", "是否处置", "解除时间", "处置说明"],
                   _alert_rows(day_alerts))
    else:
        doc.add_paragraph("（本日无告警记录）")
    doc.add_heading("三、未解除告警", level=1)
    if unresolved:
        _add_table(doc, ["站点", "级别", "类型", "触发时间", "处置说明"],
                   [[station_names.station_name(a.station_code) or a.station_code, a.level, a.alert_type,
                     _fmt_ts(a.triggered_at), (a.resolution or "—")[:40]] for a in unresolved])
    else:
        doc.add_paragraph("（无未解除告警）")
    doc.add_heading("四、关注要点", level=1)
    doc.add_paragraph(notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"{'复盘' if 'review' in filename else '设备' if 'device' in filename else '模型'}日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size,
            "summary": f"{date_str} 告警 {len(day_alerts)} · 已处置 {len(disposed)} · 未解除 {len(unresolved)}"}


# ════════════════════════════ device（设备在线率日报） ════════════════════════════

async def _gen_device(date_str: str) -> dict:
    stats = await station_collector.collect_device_stats()
    detail = stats["detail"]
    offline_items = [d for d in detail if d["status"] != "online"]
    rate = (stats["online"] / stats["total"] * 100) if stats["total"] else 0
    collector_str = "正常" if stats.get("collector_healthy") else f"异常(心跳{stats.get('collector_heartbeat_age_s')}s)"

    fb = (f"共 {stats['total']} 台设备，在线 {stats['online']} 台（{rate:.0f}%），"
          f"离线/无数据 {stats['offline']} 台；采集器{collector_str}。")
    ctx = "\n".join(
        f"- {d['station_name']}：RTU {d['rtu']}，流量计 {d['flow_meter']}，摄像头 {d['camera']}"
        for d in detail
    ) or "（无设备数据）"
    overview = await _llm(
        f"你是设备巡检编辑。以下是 {date_str} 各站设备状态，请用 2~3 句话写「巡检综述」，"
        f"概括在线率与异常设备，用站点名，直接输出正文：\n{ctx}\n在线率 {rate:.0f}%，采集器{collector_str}。",
        fb,
    )
    notes = await _llm(
        f"基于以下 {date_str} 设备状态，给出 2~3 条「关注要点」（离线排查/采集器健康），用站点名：\n{ctx}",
        "• 建议排查离线/无数据站点的设备与通信链路。" if offline_items else "• 全部设备在线，状态正常。",
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"device_{date_str}.docx"
    filepath = reports_dir / filename

    rows = [[d["station_name"], d["rtu"], d["flow_meter"], d["camera"],
             f"{d['water_level']:.2f}" if d.get("waterLevel") is not None else "—"] for d in detail]

    doc = _new_doc("设备在线率日报",
                   f"日期: {date_str}　|　在线 {stats['online']}/{stats['total']}（{rate:.0f}%）　|　采集器: {collector_str}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、巡检综述", level=1)
    doc.add_paragraph(overview)
    doc.add_heading("二、设备状态", level=1)
    _add_table(doc, ["站点", "RTU", "流量计", "摄像头", "最新水位(m)"], rows)
    doc.add_heading("三、离线/异常清单", level=1)
    if offline_items:
        _add_table(doc, ["站点", "RTU", "摄像头", "最新水位(m)"],
                   [[d["station_name"], d["rtu"], d["camera"],
                     f"{d['water_level']:.2f}" if d.get("waterLevel") is not None else "—"] for d in offline_items])
    else:
        doc.add_paragraph("（全部设备在线）")
    doc.add_heading("四、关注要点", level=1)
    doc.add_paragraph(notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"{'复盘' if 'review' in filename else '设备' if 'device' in filename else '模型'}日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size,
            "summary": f"{date_str} 设备在线 {stats['online']}/{stats['total']}（{rate:.0f}%）采集器{collector_str}"}


# ════════════════════════════ model（模型预报一致性日报） ════════════════════════════

async def _gen_model(date_str: str) -> dict:
    from gateway.services import chronos_client

    health = chronos_client.get_forecast_health()
    rows = []
    for code in ALL_STATIONS:
        name = station_names.station_name(code) or code
        wl_stats = await data_cache.get_stats(code, "waterLevel") or {}
        flow_stats = await data_cache.get_stats(code, "virtualFlow") or {}
        rows.append([
            name,
            f"{wl_stats.get('filled_points', 0)}（实测 {wl_stats.get('measured_points', 0)}）",
            f"{flow_stats.get('filled_points', 0)}（实测 {flow_stats.get('measured_points', 0)}）",
        ])
    total_fill = sum(int(r[1].split("（")[0]) for r in rows) if rows else 0

    fb = (f"Chronos 预报健康：成功 {health.get('successes', 0)} 次、失败 {health.get('failures', 0)} 次，"
          f"状态{'正常' if health.get('healthy') else '异常'}；当日共填补 {total_fill} 个空缺点。")
    ctx = "\n".join(f"- {r[0]}：水位填补 {r[1]}，流量填补 {r[2]}" for r in rows) or "（无预报数据）"
    overview = await _llm(
        f"你是预报质量分析编辑。以下是 {date_str} Chronos 模型对各站的预报填补情况，请用 2~3 句话写「模型综述」，"
        f"概括模型健康与填补密度，用站点名，直接输出正文：\n{ctx}\n模型健康：成功 {health.get('successes',0)} 失败 {health.get('failures',0)}。",
        fb,
    )
    notes = await _llm(
        f"基于以下 {date_str} 预报填补数据，给出 2~3 条「关注要点」（填补过多/模型异常），用站点名：\n{ctx}",
        "• 预报填补正常，模型运行稳定。" if health.get("healthy") else "• 模型存在失败，建议检查 Chronos 推理与数据质量。",
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"model_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("模型预报一致性日报",
                   f"日期: {date_str}　|　Chronos 成功 {health.get('successes', 0)}/失败 {health.get('failures', 0)}　|　填补点 {total_fill}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、模型综述", level=1)
    doc.add_paragraph(overview)
    doc.add_heading("二、各站预报填补", level=1)
    _add_table(doc, ["站点", "水位填补(实测)", "流量填补(实测)"], rows)
    doc.add_heading("三、模型健康", level=1)
    doc.add_paragraph(f"推理成功 {health.get('successes', 0)} 次，失败 {health.get('failures', 0)} 次；整体状态：{'正常' if health.get('healthy') else '异常'}。")
    doc.add_heading("四、关注要点", level=1)
    doc.add_paragraph(notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"{'复盘' if 'review' in filename else '设备' if 'device' in filename else '模型'}日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size,
            "summary": f"{date_str} 预报成功 {health.get('successes', 0)}/失败 {health.get('failures', 0)} · 填补 {total_fill} 点"}


# ════════════════════════════ dispatcher ════════════════════════════

async def generate_report(report_type, station_code=None, date_str=None):
    """统一入口：按 report_type 分派到对应生成器，输出 docx。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if report_type == "daily":
        return await _gen_daily(date_str, station_code)
    if report_type == "review":
        return await _gen_review(date_str)
    if report_type == "device":
        return await _gen_device(date_str)
    if report_type == "model":
        return await _gen_model(date_str)
    raise ValueError(f"unknown report_type: {report_type}（支持 daily/review/device/model）")


def main():
    parser = argparse.ArgumentParser(description="统一日报生成器（daily/review/device/model，输出 docx）")
    parser.add_argument("--type", default="daily", choices=["daily", "review", "device", "model"])
    parser.add_argument("--station", default=None, help="可选：仅生成 daily 指定站点报告")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="日期 YYYY-MM-DD")
    args = parser.parse_args()

    result = asyncio.run(generate_report(args.type, args.station, args.date))
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
