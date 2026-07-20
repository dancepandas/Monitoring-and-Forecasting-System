"""统一日报生成器 —— 四类报告共用同一套 docx 骨架：

标题 + 日期 → 一、LLM 综述 → 二、真实数据明细表 → 三、异常/未处置清单 → 四、LLM 关注要点

全文用站点名（不用编码）；LLM 不可用时「综述/要点」自动回退为原始数据句。
所有报告一律存 docx（Word），不存 txt。支持类型: daily / review / device / model
"""
import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gateway.config import settings
from gateway.services import data_cache, station_names, station_collector
from gateway.services.system_events import write_event
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import markdown

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ALL_STATIONS = list(station_names.ALL_CODES)

# ── 预警等级颜色 ──
LEVEL_COLORS = {"red": "FF0000", "orange": "FF8C00", "yellow": "DAA520", "blue": "0066CC"}
LEVEL_LABELS = {"red": "红色", "orange": "橙色", "yellow": "黄色", "blue": "蓝色"}


# ─────────────────────────── LLM 叙述（不可用回退原始数据） ───────────────────────────

async def _llm(prompt: str, fallback: str, max_tokens: int = 1000) -> str:
    """调 LLM 生成一段叙述，失败/不可达时返回 fallback 原始数据句。"""
    try:
        from gateway.services.agent_utils import quick_ask
        text = await quick_ask(prompt, max_tokens=max_tokens)
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
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    return doc


class _MdRenderer(HTMLParser):
    """将 Markdown→HTML 渲染为 python-docx 元素（段落、粗体、斜体、列表、标题）。"""

    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self._p: list = []            # 当前段落 runs: [(text, bold, italic), ...]
        self._stack: list[str] = []   # 标签栈
        self._list_level = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4"):
            self._flush()
            self._stack.append("heading")
        elif tag == "p":
            self._flush()
            self._stack.append("p")
        elif tag in ("strong", "b"):
            self._stack.append("bold")
        elif tag in ("em", "i"):
            self._stack.append("italic")
        elif tag == "li":
            self._flush()
            self._stack.append("li")
        elif tag in ("ul", "ol"):
            self._list_level += 1
        elif tag == "br":
            self._p.append(("\n", False, False))

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4"):
            self._flush_heading(tag)
        elif tag == "p":
            self._flush_para(add_gap=False)
        elif tag in ("strong", "b"):
            self._pop_tag("bold")
        elif tag in ("em", "i"):
            self._pop_tag("italic")
        elif tag == "li":
            self._flush_li()
        elif tag in ("ul", "ol"):
            self._list_level = max(0, self._list_level - 1)

    def handle_data(self, data):
        if data.strip():
            bold = "bold" in self._stack
            italic = "italic" in self._stack
            self._p.append((data, bold, italic))

    def _pop_tag(self, tag):
        try:
            self._stack.remove(tag)
        except ValueError:
            pass

    def _flush(self):
        if self._p:
            self._p = []

    def _flush_heading(self, tag):
        level = int(tag[1]) + 1  # h1→2, h2→3, h3→4
        text = "".join(t[0] for t in self._p).strip()
        self._p = []
        if text:
            h = self.doc.add_heading(text, level=min(level, 4))
            for run in h.runs:
                run.font.size = Pt({2: 16, 3: 14, 4: 13}.get(level, 13))
        self._pop_tag("heading")

    def _flush_para(self, add_gap=True):
        text = "".join(t[0] for t in self._p).strip()
        if text:
            para = self.doc.add_paragraph()
            self._build_runs(para)
            if add_gap:
                para.paragraph_format.space_after = Pt(4)
        self._p = []

    def _flush_li(self):
        text = "".join(t[0] for t in self._p).strip()
        self._p = []
        if text:
            para = self.doc.add_paragraph(style="List Bullet")
            # 清除默认样式文本，手动写入 runs
            para.clear()
            self._build_runs(para)
        self._pop_tag("li")

    def _build_runs(self, para):
        """将 _p 中的片段合并为连续 runs。"""
        merged = []
        for text, bold, italic in self._p:
            if merged and (merged[-1][1] == bold and merged[-1][2] == italic):
                merged[-1] = (merged[-1][0] + text, bold, italic)
            else:
                merged.append((text, bold, italic))
        for text, bold, italic in merged:
            run = para.add_run(text)
            run.font.size = Pt(10.5)
            if bold:
                run.bold = True
            if italic:
                run.italic = True
        self._p = []


def _add_markdown(doc, md_text: str):
    """将 LLM 输出的 Markdown 文本渲染为 docx 元素。"""
    if not md_text or not md_text.strip():
        return
    # 清理 LLM 可能输出的 fence（```）
    md_text = re.sub(r'^```[a-z]*\n?', '', md_text.strip(), flags=re.MULTILINE)
    md_text = re.sub(r'\n?```$', '', md_text.strip())
    html = markdown.markdown(md_text, extensions=['extra'])
    renderer = _MdRenderer(doc)
    renderer.feed(html)
    renderer._flush_para()  # 刷出最后一段


def _add_table(doc, headers: list, rows: list, style: str = "Light Grid Accent 1",
               col_widths: list = None):
    """添加一个带表头的数据表。rows 为 list[list]。"""
    table = doc.add_table(rows=1, cols=len(headers))
    try:
        table.style = style
    except KeyError:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 表头加粗
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = str(h)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)

    # 数据行
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
            for p in cells[i].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)

    # 列宽
    if col_widths:
        for row_obj in table.rows:
            for i, w in enumerate(col_widths):
                if i < len(row_obj.cells):
                    row_obj.cells[i].width = Cm(w)

    doc.add_paragraph("")
    return table


def _add_highlight_para(doc, text: str, color: str = None):
    """添加带可选颜色的段落。"""
    p = doc.add_paragraph()
    run = p.add_run(text)
    if color:
        run.font.color.rgb = RGBColor(*_hex_to_rgb(color))
    return p


def _hex_to_rgb(hex_str: str) -> tuple:
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _fmt_ts(ts) -> str:
    """unix 时间戳 → 'MM-DD HH:MM'，无效返回 '—'。"""
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return "—"


def _get_station_thresholds(code: str) -> dict:
    """获取站点预警阈值，失败返回空。"""
    try:
        from gateway.services.warning_config import get_station_thresholds
        return get_station_thresholds(code)
    except Exception:
        return {"level": {}, "flow": {}}


def _calc_trend(values: list) -> str:
    """计算趋势：取后 1/3 与前 1/3 均值比较。"""
    if len(values) < 6:
        return "→"
    n = max(len(values) // 3, 3)
    head_avg = sum(values[:n]) / n
    tail_avg = sum(values[-n:]) / n
    diff_pct = (tail_avg - head_avg) / head_avg * 100 if head_avg != 0 else 0
    if diff_pct > 3:
        return "↑ 上升"
    elif diff_pct < -3:
        return "↓ 下降"
    return "→ 平稳"


def _stat_line(values: list, unit: str = "") -> str:
    """生成统计行：条数、最新值、最小值、最大值、均值。"""
    if not values:
        return "无数据"
    latest = values[-1]
    v_min, v_max = min(values), max(values)
    avg = sum(values) / len(values)
    if unit:
        return f"共 {len(values)} 条　|　最新 {latest:.2f}{unit}　|　最低 {v_min:.2f}　|　最高 {v_max:.2f}　|　均值 {avg:.2f}{unit}"
    return f"共 {len(values)} 条　|　最新 {latest:.2f}　|　最低 {v_min:.2f}　|　最高 {v_max:.2f}　|　均值 {avg:.2f}"


def _threshold_line(thresholds: dict, key: str, latest_val: float, unit: str) -> str:
    """生成阈值对比行：当前值 vs blue/yellow/orange/red。"""
    t = thresholds.get(key, {})
    if not t or latest_val is None:
        return ""
    parts = []
    current_level = ""
    for lv in ("blue", "yellow", "orange", "red"):
        thresh = t.get(lv)
        if thresh is None:
            continue
        marker = ""
        if latest_val >= thresh:
            current_level = LEVEL_LABELS.get(lv, lv)
            marker = " ◀"
        parts.append(f"{LEVEL_LABELS.get(lv, lv)}: {thresh}{unit}{marker}")
    if parts:
        line = "预警阈值：" + " ｜ ".join(parts)
        if current_level:
            line += f"　→ 当前达 {current_level}"
        return line
    return ""


# ════════════════════════════ daily（流域运行日报） ════════════════════════════

async def _gen_daily(date_str: str, station_code=None) -> dict:
    stations_to_report = [station_code] if station_code else ALL_STATIONS
    station_reports = []
    all_wl, all_flow = [], []
    total_wl_count = total_flow_count = 0
    active_count = 0

    for code in stations_to_report:
        sd = await station_collector.collect_station_data(code)
        wl_vals, flow_vals = sd["wl_vals"], sd["flow_vals"]
        level_items, flow_items = sd["level_items"], sd["flow_items"]
        name = sd["name"]
        total_wl_count += len(wl_vals)
        total_flow_count += len(flow_vals)
        all_wl.extend(wl_vals)
        all_flow.extend(flow_vals)

        has_data = len(wl_vals) > 0 or len(flow_vals) > 0
        if has_data:
            active_count += 1

        thresholds = _get_station_thresholds(code)
        wl_trend = _calc_trend(wl_vals)
        flow_trend = _calc_trend(flow_vals)
        latest_wl = wl_vals[-1] if wl_vals else None
        latest_flow = flow_vals[-1] if flow_vals else None

        station_reports.append({
            "code": code, "name": name,
            "wl_count": len(wl_vals), "flow_count": len(flow_vals),
            "wl_values": wl_vals, "flow_values": flow_vals,
            "wl_trend": wl_trend, "flow_trend": flow_trend,
            "latest_wl": f"{latest_wl:.2f}m" if latest_wl is not None else "—",
            "latest_flow": f"{latest_flow:.0f}m³/s" if latest_flow is not None else "—",
            "wl_range": f"{min(wl_vals):.2f} ~ {max(wl_vals):.2f}m" if wl_vals else "—",
            "flow_range": f"{min(flow_vals):.0f} ~ {max(flow_vals):.0f}m³/s" if flow_vals else "—",
            "wl_stat": _stat_line(wl_vals, "m") if wl_vals else "无水位数据",
            "flow_stat": _stat_line(flow_vals, "m³/s") if flow_vals else "无流量数据",
            "wl_threshold_line": _threshold_line(thresholds, "level", latest_wl, "m"),
            "flow_threshold_line": _threshold_line(thresholds, "flow", latest_flow, "m³/s"),
            "level_items": level_items, "flow_items": flow_items,
        })

    # ── 原始数据兜底句 ──
    fb_overview = "、".join(filter(None, [
        f"覆盖 {len(stations_to_report)} 个站点（{active_count} 个有数据）",
        f"水位范围 {min(all_wl):.2f}~{max(all_wl):.2f}m" if all_wl else "",
        f"流量范围 {min(all_flow):.0f}~{max(all_flow):.0f}m³/s" if all_flow else "",
        f"共水位 {total_wl_count} 条、流量 {total_flow_count} 条",
    ])) or "当日无可用数据。"

    # ── LLM 综述（含趋势+阈值） ──
    ctx_lines = []
    for s in station_reports:
        line = (f"- {s['name']}：水位 {s['latest_wl']}（{s['wl_stat']}）趋势{s['wl_trend']}；"
                f"流量 {s['latest_flow']}（{s['flow_stat']}）趋势{s['flow_trend']}")
        if s["wl_threshold_line"]:
            line += f"；阈值: {s['wl_threshold_line']}"
        ctx_lines.append(line)
    ctx = "\n".join(ctx_lines)
    overview = await _llm(
        f"你是水文值班编辑。下面是 {date_str} 郴州流域各站实测水文数据（含24h统计、趋势、预警阈值对照），"
        f"请用 3~5 句话写一段「全流域水情综述」，"
        f"重点概括：整体水情态势、是否有站点接近/超过预警线、趋势变化方向、与昨日对比推测。"
        f"用站点名（不用编码），语气专业简洁，直接输出正文：\n{ctx}",
        fb_overview, max_tokens=800,
    )

    # ── LLM 关注要点 ──
    notes_fb = []
    if all_wl:
        mx_wl = max(station_reports, key=lambda s: max(s["wl_values"]) if s["wl_values"] else -1e9)
        notes_fb.append(f"• 最高水位出现在 {mx_wl['name']}（{max(all_wl):.2f}m），趋势{mx_wl['wl_trend']}")
    if all_flow:
        mx_f = max(station_reports, key=lambda s: max(s["flow_values"]) if s["flow_values"] else -1e9)
        notes_fb.append(f"• 最大流量出现在 {mx_f['name']}（{max(all_flow):.0f}m³/s）")
    rising = [s["name"] for s in station_reports if "上升" in s.get("wl_trend", "")]
    if rising:
        notes_fb.append(f"• 水位上升站点：{'、'.join(rising)}，需加强关注")
    inactive = [s["name"] for s in station_reports if s["wl_count"] == 0 and s["flow_count"] == 0]
    if inactive:
        notes_fb.append(f"• 无数据站点：{'、'.join(inactive)}，请排查设备与通信")
    if not notes_fb:
        notes_fb.append("• 当日水情平稳，无特别关注事项。")
    notes = await _llm(
        f"你是水文分析师。基于 {date_str} 郴州流域各站数据（含趋势、阈值对照），"
        f"给出 3~4 条「关注要点与建议」。要点应具体到站名和数据，"
        f"关注：超阈值风险、快速上升趋势、数据缺失、上下游联动。直接输出要点：\n{ctx}",
        "\n".join(notes_fb), max_tokens=1600,
    )

    active = [s for s in station_reports if s["wl_count"] > 0 or s["flow_count"] > 0]
    inactive_stations = [s["name"] for s in station_reports if s["wl_count"] == 0 and s["flow_count"] == 0]

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_{date_str}_{station_code}.docx" if station_code else f"daily_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("水文监测日报",
                   f"日期: {date_str}　|　覆盖站点: {len(stations_to_report)} 个（{active_count} 个有数据）　|　生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_heading("一、全流域水情综述", level=1)
    _add_markdown(doc, overview)
    doc.add_heading("二、各站水情明细", level=1)

    for sr in station_reports:
        doc.add_heading(sr["name"], level=2)

        # 水位统计
        doc.add_paragraph(f"【水位】趋势: {sr['wl_trend']}")
        doc.add_paragraph(sr["wl_stat"])
        if sr["wl_threshold_line"]:
            _add_highlight_para(doc, sr["wl_threshold_line"], LEVEL_COLORS.get(
                _resolve_level(sr["wl_threshold_line"]), None))
        if sr["wl_values"]:
            doc.add_paragraph("水位明细（最近记录）：")
            wl_rows = []
            # level_items 优先，为空时回退到 flow_items（flow_items 也含 waterLevel 字段）
            src_items = sr["level_items"] if sr["level_items"] else sr["flow_items"]
            for it in src_items[:12]:
                t = it.get("time") or it.get("measureTime") or "—"
                wl_raw = it.get("waterLevel")
                if wl_raw is not None:
                    try:
                        wl_rows.append([t, f"{float(wl_raw):.2f}m"])
                    except (ValueError, TypeError):
                        wl_rows.append([t, str(wl_raw)])
            if wl_rows:
                _add_table(doc, ["时间", "水位 (m)"], wl_rows, col_widths=[6, 4])
            else:
                doc.add_paragraph("（暂无水位明细）")

        # 流量统计
        doc.add_paragraph(f"【流量】趋势: {sr['flow_trend']}")
        doc.add_paragraph(sr["flow_stat"])
        if sr["flow_threshold_line"]:
            _add_highlight_para(doc, sr["flow_threshold_line"], LEVEL_COLORS.get(
                _resolve_level(sr["flow_threshold_line"]), None))
        if sr["flow_values"]:
            doc.add_paragraph("流量明细（最近记录）：")
            flow_rows = []
            for it in sr["flow_items"][:12]:
                t = it.get("time") or it.get("measureTime") or "—"
                vf_raw = it.get("virtualFlow")
                if vf_raw is not None:
                    try:
                        flow_rows.append([t, f"{float(vf_raw):.0f}m³/s"])
                    except (ValueError, TypeError):
                        flow_rows.append([t, str(vf_raw)])
            if flow_rows:
                _add_table(doc, ["时间", "流量 (m³/s)"], flow_rows, col_widths=[6, 4])
            else:
                doc.add_paragraph("（暂无流量明细）")
        else:
            doc.add_paragraph("（无流量数据）")

    doc.add_heading("三、设备与数据质量", level=1)
    doc.add_paragraph(f"数据活跃站点: {active_count}/{len(stations_to_report)}")
    if inactive_stations:
        doc.add_paragraph(f"无数据站点: {'、'.join(inactive_stations)}，建议排查设备通信状态。")
    else:
        doc.add_paragraph("无数据站点: 无")
    doc.add_paragraph(f"水位总记录: {total_wl_count} 条　|　流量总记录: {total_flow_count} 条")

    doc.add_heading("四、关注要点与建议", level=1)
    _add_markdown(doc, notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    summary = f"{date_str} {len(stations_to_report)} 站 · 水位 {total_wl_count} 条 · 流量 {total_flow_count} 条"
    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size, "summary": summary}


def _resolve_level(threshold_line: str) -> str:
    """从阈值行中解析当前预警等级。"""
    for lv in ("红色", "橙色", "黄色", "蓝色"):
        if f"达 {lv}" in threshold_line:
            return {"红色": "red", "橙色": "orange", "黄色": "yellow", "蓝色": "blue"}.get(lv, "")
    return ""


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
        # 计算响应时长
        resp_time = ""
        if a.triggered_at and a.resolved_at:
            dur_h = (a.resolved_at - a.triggered_at) / 3600
            resp_time = f"{dur_h:.1f}h" if dur_h >= 1 else f"{dur_h * 60:.0f}min"
        rows.append([
            station_names.station_name(a.station_code) or a.station_code,
            a.level, a.alert_type, _fmt_ts(a.triggered_at),
            disposed, _fmt_ts(a.resolved_at), resp_time,
            (a.resolution or "—")[:40],
        ])
    return rows


async def _gen_review(date_str: str) -> dict:
    alerts = await _collect_alerts()
    day_start = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
    day_end = day_start + 86400
    day_alerts = [a for a in alerts if day_start <= (a.triggered_at or 0) <= day_end] or alerts
    unresolved = [a for a in day_alerts if not a.resolved_at]
    disposed = [a for a in day_alerts if a.resolved_at]

    level_count = {}
    type_count = {}
    for a in day_alerts:
        level_count[a.level] = level_count.get(a.level, 0) + 1
        type_count[a.alert_type] = type_count.get(a.alert_type, 0) + 1
    level_str = "、".join(f"{k}{v}条" for k, v in level_count.items()) or "无"
    type_str = "、".join(f"{k}: {v}" for k, v in type_count.items())

    # 响应时间统计
    resp_times = [(a.resolved_at - a.triggered_at) for a in disposed if a.triggered_at and a.resolved_at]
    resp_summary = ""
    if resp_times:
        avg_min = sum(resp_times) / len(resp_times) / 60
        resp_summary = f"已处置告警平均响应 {avg_min:.0f} 分钟"

    fb = (f"本日共告警 {len(day_alerts)} 条（{level_str}），已处置 {len(disposed)} 条，"
          f"未解除 {len(unresolved)} 条。{resp_summary} 告警类型分布: {type_str}")
    ctx = "\n".join(
        f"- {station_names.station_name(a.station_code)}|{a.level}|{a.alert_type}|"
        f"触发{_fmt_ts(a.triggered_at)}|{'已处置' if a.resolved_at else '未解除'}|{(a.resolution or '')[:30]}"
        for a in day_alerts[:50]
    ) or "（本日无告警）"
    overview = await _llm(
        f"你是水文预警复盘编辑。以下是 {date_str} 的告警记录（含响应时长、类型分布），"
        f"请用 3~4 句话写「复盘综述」，概括告警规模、响应是否及时、类型分布、有无遗留风险，"
        f"用站点名，直接输出正文：\n{ctx}\n{fb}",
        fb, max_tokens=800,
    )
    notes = await _llm(
        f"基于以下 {date_str} 告警数据，给出 3~4 条「关注要点」（处置改进/未解除跟进/系统优化建议），"
        f"用站点名，要具体到站和告警类型：\n{ctx}",
        "• 建议持续关注未解除告警并完善处置记录。" if unresolved else "• 当日告警均已妥善处置。",
        max_tokens=1600,
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"review_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("预警处置复盘日报",
                   f"日期: {date_str}　|　告警 {len(day_alerts)} 条　|　已处置 {len(disposed)} · 未解除 {len(unresolved)}　|　{resp_summary}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、复盘综述", level=1)
    _add_markdown(doc, overview)
    doc.add_heading("二、告警明细", level=1)
    if day_alerts:
        _add_table(doc, ["站点", "级别", "类型", "触发时间", "是否处置", "解除时间", "响应时长", "处置说明"],
                   _alert_rows(day_alerts), col_widths=[2.5, 1, 2, 2, 1.2, 2, 1.2, 3])
    else:
        doc.add_paragraph("（本日无告警记录）")
    doc.add_heading("三、未解除告警", level=1)
    if unresolved:
        _add_table(doc, ["站点", "级别", "类型", "触发时间", "持续时间", "处置说明"],
                   [[station_names.station_name(a.station_code) or a.station_code, a.level, a.alert_type,
                     _fmt_ts(a.triggered_at),
                     f"{(datetime.now().timestamp() - (a.triggered_at or 0)) / 3600:.1f}h",
                     (a.resolution or "—")[:40]] for a in unresolved],
                   col_widths=[2.5, 1, 2, 2, 1.5, 4])
    else:
        doc.add_paragraph("（无未解除告警）")
    doc.add_heading("四、关注要点与建议", level=1)
    _add_markdown(doc, notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"复盘日报已生成: {filename}（{filepath.stat().st_size} bytes）")

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
        f"- {d['station_name']}：RTU {d['rtu']}，流量计 {d['flow_meter']}，摄像头 {d['camera']}，"
        f"水位 {d.get('water_level', '—')}"
        for d in detail
    ) or "（无设备数据）"
    overview = await _llm(
        f"你是设备巡检编辑。以下是 {date_str} 各站设备状态，请用 3~4 句话写「巡检综述」，"
        f"概括在线率、异常设备及影响、采集器状态，用站点名，直接输出正文：\n{ctx}\n在线率 {rate:.0f}%，采集器{collector_str}。",
        fb, max_tokens=800,
    )
    notes = await _llm(
        f"基于以下 {date_str} 设备状态，给出 3~4 条「关注要点」（离线排查步骤/采集器健康/重点设备跟进），"
        f"用站点名，要具体到设备类型：\n{ctx}",
        "• 建议排查离线/无数据站点的设备与通信链路。" if offline_items else "• 全部设备在线，状态正常。",
        max_tokens=1600,
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"device_{date_str}.docx"
    filepath = reports_dir / filename

    rows = [[d["station_name"], d["rtu"], d["flow_meter"], d["camera"],
             f"{d['water_level']:.2f}" if d.get("water_level") is not None else "—"] for d in detail]

    doc = _new_doc("设备在线率日报",
                   f"日期: {date_str}　|　在线 {stats['online']}/{stats['total']}（{rate:.0f}%）　|　采集器: {collector_str}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、巡检综述", level=1)
    _add_markdown(doc, overview)
    doc.add_heading("二、设备状态总览", level=1)
    _add_table(doc, ["站点", "RTU", "流量计", "摄像头", "最新水位(m)"], rows,
               col_widths=[3, 2.5, 2.5, 2.5, 3])
    doc.add_heading("三、离线/异常清单", level=1)
    if offline_items:
        _add_table(doc, ["站点", "RTU", "摄像头", "最新水位(m)", "建议操作"],
                   [[d["station_name"], d["rtu"], d["camera"],
                     f"{d['water_level']:.2f}" if d.get("water_level") is not None else "—",
                     "排查供电与通信" if d["rtu"] == "offline" else "检查传感器配置"]
                    for d in offline_items],
                   col_widths=[3, 2, 2, 2.5, 3.5])
    else:
        doc.add_paragraph("（全部设备在线）")
    doc.add_heading("四、关注要点", level=1)
    _add_markdown(doc, notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"设备日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    summary = f"{date_str} 设备在线 {stats['online']}/{stats['total']}（{rate:.0f}%）采集器{collector_str}"
    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size, "summary": summary}


# ════════════════════════════ model（模型预报一致性日报） ════════════════════════════

async def _gen_model(date_str: str) -> dict:
    from gateway.services import chronos_client

    health = chronos_client.get_forecast_health()
    rows = []
    total_fill = 0
    total_measured = 0
    for code in ALL_STATIONS:
        name = station_names.station_name(code) or code
        wl_stats = await data_cache.get_stats(code, "waterLevel") or {}
        flow_stats = await data_cache.get_stats(code, "virtualFlow") or {}
        wl_fill = wl_stats.get("filled_points", 0)
        fl_fill = flow_stats.get("filled_points", 0)
        wl_meas = wl_stats.get("measured_points", 0)
        fl_meas = flow_stats.get("measured_points", 0)
        total_fill += wl_fill + fl_fill
        total_measured += wl_meas + fl_meas

        # 填补率
        wl_total = wl_fill + wl_meas
        fl_total = fl_fill + fl_meas
        fill_rate_wl = f"{(wl_fill / wl_total * 100):.0f}%" if wl_total > 0 else "—"
        fill_rate_fl = f"{(fl_fill / fl_total * 100):.0f}%" if fl_total > 0 else "—"

        rows.append([
            name,
            f"{wl_fill}（实测 {wl_meas}，{fill_rate_wl}）",
            f"{fl_fill}（实测 {fl_meas}，{fill_rate_fl}）",
            f"{wl_stats.get('min', '—')}~{wl_stats.get('max', '—')}" if wl_stats.get('max') is not None else "—",
        ])

    # 生成更有意义的上下文
    status_text = "正常" if health.get("healthy") else "异常"
    fb = (f"Chronos 预报状态：{'正常' if health.get('healthy') else '异常'}，"
          f"成功 {health.get('successes', 0)} 次、失败 {health.get('failures', 0)} 次；"
          f"当日共填补 {total_fill} 个空缺点（实测点 {total_measured}）。")

    ctx = "\n".join(
        f"- {r[0]}：水位填补 {r[1]}，流量填补 {r[2]}，水位区间 {r[3]}"
        for r in rows
    ) or "（无预报数据）"

    overview = await _llm(
        f"你是预报质量分析编辑。以下是 {date_str} Chronos 模型对各站的预报填补情况（含填补率），"
        f"请用 3~4 句话写「模型综述」，概括模型健康、填补密度、各站差异，用站点名，直接输出正文：\n{ctx}\n{fb}",
        fb, max_tokens=800,
    )
    notes = await _llm(
        f"基于以下 {date_str} 预报填补数据，给出 2~3 条「关注要点」（填补率偏高/偏低站点、模型预警、数据质量建议），"
        f"用站点名，要具体到数据：\n{ctx}\n模型状态:{status_text}",
        "• 预报填补正常，模型运行稳定。" if health.get("healthy") else "• 模型存在失败，建议检查 Chronos 推理与数据质量。",
        max_tokens=1600,
    )

    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"model_{date_str}.docx"
    filepath = reports_dir / filename

    doc = _new_doc("模型预报一致性日报",
                   f"日期: {date_str}　|　Chronos 成功 {health.get('successes', 0)}/失败 {health.get('failures', 0)}　|　填补点 {total_fill}　|　生成时间: {datetime.now().strftime('%H:%M:%S')}")
    doc.add_heading("一、模型综述", level=1)
    _add_markdown(doc, overview)
    doc.add_heading("二、各站预报填补详情", level=1)
    _add_table(doc, ["站点", "水位填补(实测，填补率)", "流量填补(实测，填补率)", "水位区间(m)"], rows,
               col_widths=[2.5, 4.5, 4.5, 2.5])
    doc.add_heading("三、模型健康状态", level=1)
    doc.add_paragraph(
        f"推理成功 {health.get('successes', 0)} 次，失败 {health.get('failures', 0)} 次；"
        f"整体状态：{status_text}。\n当日总实测点: {total_measured}，总填补点: {total_fill}。"
    )
    doc.add_heading("四、关注要点", level=1)
    _add_markdown(doc, notes)
    doc.save(filepath)
    write_event("report", "report_generated", f"模型日报已生成: {filename}（{filepath.stat().st_size} bytes）")

    summary = f"{date_str} 预报成功 {health.get('successes', 0)}/失败 {health.get('failures', 0)} · 填补 {total_fill} 点"
    return {"path": str(filepath), "filename": filename, "size": filepath.stat().st_size, "summary": summary}


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
