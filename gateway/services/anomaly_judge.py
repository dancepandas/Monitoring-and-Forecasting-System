"""数据异常智能裁决 — 水位↔流量物理一致性 + 明显脏数据。

设计要点（详见 docs/superpowers/specs/2026-07-19-data-anomaly-judge-design.md）：
- 廉价统计预筛（中位数 + 四分位距 + 乘性突刺，稳健不退化）决定是否值得花一次 LLM 调用；
- 命中才调 quick_ask(qwen-plus) 出结构化裁决，未命中即判正常；
- 预筛是固定统计门，非人工配置阈值（满足"不要人设阈值、要智能体灵活判断"）；
- 裁决落盘 anomaly_verdicts.json，供 /latest、/flow-raw 读数挂标注；
- LLM 熔断/超时/解析失败 → 退化为预筛弱标注（source=prefilter），不阻塞主数据。

由 MonitorEngine._check_station 每 5 分钟调用一次。
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import data_cache
from .station_names import station_name
from .agent_utils import quick_ask

logger = logging.getLogger(__name__)

_VERDICTS_FILE = Path(__file__).parent.parent / "data" / "anomaly_verdicts.json"
_MAX_AGE_SECS = 900          # 裁决超过 15 分钟视为过期，清除标注
_WINDOW_POINTS = 12          # 近 1h（5 分钟网格 ≈ 12 点）
_MIN_POINTS = 6              # 低于此数不评判

# 预筛门（固定统计门，非配置阈值；非按站配置的预警阈值）
_SPIKE_FACTOR = 3.0          # 最大值超过中位数 N 倍 → 乘性突刺（如 12 → 220）
_SPIKE_IQR_K = 3.0           # 最大值偏离中位数超过 N×IQR → 加性突刺（IQR>0 时）
_SPIKE_REL = 0.05            # IQR=0（基线恒定）时：极差/中位数 > 5% → 突刺
_FLAT_REL = 0.02             # 极差/中位数 < 2% → 该指标"平稳"
_MEASURED_RATIO_MIN = 0.5    # 实测占比低于此值 → 缺测伪装稳定

# 异常类型 → 中文标签
_LABEL = {
    "flow_level_inconsistency": "流量-水位不一致",
    "level_flow_inconsistency": "水位-流量不一致",
    "frozen": "数据疑似冻结",
    "invalid_value": "数值异常",
    "gap_masking": "缺测伪装稳定",
}


# ──────────────────────────────────────────────────────────────
# 统计工具（纯函数）
# ──────────────────────────────────────────────────────────────

def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _quartiles(xs):
    """返回 (Q1, Q3)，基于中位数分割法。"""
    s = sorted(xs)
    n = len(s)
    if n < 2:
        m = _median(s)
        return m, m
    mid = n // 2
    lower = s[:mid]
    upper = s[mid + (n % 2):]   # 奇数个时排除中位数本身
    return _median(lower), _median(upper)


def _has_spike(xs) -> bool:
    """序列中是否存在突刺点（最大值显著偏离主体）。

    用乘性 + 加性双判据，并在 IQR=0（基线恒定）时回退到相对极差，
    避免单一统计量在水文"常量基线"上退化：
    - 乘性：max > SPIKE_FACTOR × 中位数（catch 12→220 这类倍数级跳变）；
    - 加性：max − 中位数 > SPIKE_IQR_K × IQR（IQR>0 时，catch 有真实波动的加性跳变）；
    - IQR=0 回退：极差/中位数 > SPIKE_REL（catch 34.10→38.5 这类水位大基数小倍率跳变）。
    """
    if len(xs) < 4:
        return False
    med = _median(xs)
    mx = max(xs)
    rng = mx - min(xs)
    if med <= 0:
        return rng > 0
    if mx > _SPIKE_FACTOR * med:
        return True
    q1, q3 = _quartiles(xs)
    iqr = q3 - q1
    if iqr > 0:
        return (mx - med) > _SPIKE_IQR_K * iqr
    # IQR=0：基线恒定，任何显著相对偏离都是突刺
    return (rng / med) > _SPIKE_REL


def _is_flat(xs) -> bool:
    """序列是否基本平稳（极差相对中位数很小）。"""
    if len(xs) < 3:
        return False
    med = _median(xs)
    rng = max(xs) - min(xs)
    if med <= 0:
        return rng == 0
    return (rng / med) < _FLAT_REL


def prefilter(series):
    """统计预筛：纯函数、无 IO、无配置。

    Args:
        series: list[dict]，每条含 waterLevel / virtualFlow（float|None）及
                waterLevel_source / virtualFlow_source（"measured" 等）。

    Returns:
        list[tuple(reason_key, detail_dict)]。空列表表示无可疑。
    """
    reasons = []
    wl_pts = [float(r["waterLevel"]) for r in series if r.get("waterLevel") is not None]
    vf_pts = [float(r["virtualFlow"]) for r in series if r.get("virtualFlow") is not None]
    total = len(series)
    measured_count = sum(
        1 for r in series
        if r.get("waterLevel_source") == "measured" or r.get("virtualFlow_source") == "measured"
    )

    # 1. 负值 / 物理不可能值
    if any(v < 0 for v in wl_pts + vf_pts):
        reasons.append(("invalid_value", {}))

    # 2. 数据冻结（数值几乎位级不变 = 传感器/上游卡死）
    if len(wl_pts) >= 3 and (max(wl_pts) - min(wl_pts)) < 1e-6:
        reasons.append(("frozen", {"metric": "waterLevel"}))
    if len(vf_pts) >= 3 and (max(vf_pts) - min(vf_pts)) < 1e-6:
        reasons.append(("frozen", {"metric": "virtualFlow"}))

    # 3. 缺测伪装稳定：实测占比过低却显示稳定序列
    if total > 0 and measured_count / total < _MEASURED_RATIO_MIN:
        reasons.append(("gap_masking", {"measured_ratio": round(measured_count / total, 2)}))

    # 4. 水位↔流量一致性：需要同一时间点同时有水位和流量
    paired = [
        (float(r["waterLevel"]), float(r["virtualFlow"]))
        for r in series
        if r.get("waterLevel") is not None and r.get("virtualFlow") is not None
    ]
    if len(paired) >= _MIN_POINTS:
        wls = [p[0] for p in paired]
        vfs = [p[1] for p in paired]
        flow_spike = _has_spike(vfs)
        level_spike = _has_spike(wls)
        level_flat = _is_flat(wls)
        flow_flat = _is_flat(vfs)
        # 流量突刺而水位平稳
        if flow_spike and level_flat:
            reasons.append(("flow_level_inconsistency", {"flow_max": round(max(vfs), 1), "level_range": round(max(wls) - min(wls), 3)}))
        # 水位突刺而流量平稳（"水位同理"）
        elif level_spike and flow_flat:
            reasons.append(("level_flow_inconsistency", {"level_max": round(max(wls), 2), "flow_range": round(max(vfs) - min(vfs), 1)}))

    return reasons


# ──────────────────────────────────────────────────────────────
# 裁决主流程
# ──────────────────────────────────────────────────────────────

async def judge_station(code: str) -> dict:
    """对单站近 1h 数据做异常裁决，返回 Verdict 并落盘。"""
    aligned = await data_cache.get_aligned(code, max_age=600)
    records = (aligned or {}).get("records", [])
    recent = records[-_WINDOW_POINTS:] if records else []

    series = [
        {
            "time": r.get("time"),
            "waterLevel": r.get("waterLevel"),
            "virtualFlow": r.get("virtualFlow"),
            "waterLevel_source": r.get("waterLevel_source"),
            "virtualFlow_source": r.get("virtualFlow_source"),
        }
        for r in recent
    ]

    has_vals = [r for r in series if r["waterLevel"] is not None or r["virtualFlow"] is not None]
    if len(has_vals) < _MIN_POINTS:
        verdict = _clean_verdict()
        await _save_verdict(code, verdict)
        return verdict

    reasons = prefilter(series)
    if not reasons:
        verdict = _clean_verdict()
        await _save_verdict(code, verdict)
        return verdict

    verdict = await _llm_judge(code, series, reasons)
    await _save_verdict(code, verdict)
    return verdict


def _clean_verdict() -> dict:
    return {
        "flagged": False,
        "type": "none",
        "severity": "none",
        "reason": "",
        "message": "",
        "source": "none",
        "confidence": 0.0,
        "evaluated_ts": time.time(),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


async def _llm_judge(code: str, series: list, reasons: list) -> dict:
    """调 LLM 出结构化裁决；失败则退化为预筛弱标注。"""
    name = station_name(code)
    reason_lines = "\n".join(
        f"- {_LABEL.get(k, k)}（{detail}）" for k, detail in reasons
    )
    data_lines = []
    for r in series:
        wl = r["waterLevel"]
        vf = r["virtualFlow"]
        data_lines.append(
            f"  {r.get('time', '')}: 水位={_fmt(wl)}m, 流量={_fmt(vf)}"
        )
    series_txt = "\n".join(data_lines)

    prompt = f"""你是水文数据质量裁判。判断下面站点近 1h 数据是否可信。

站点：{name}（{code}）
近 1h 序列（实测/补齐，由旧到新）：
{series_txt}

统计预筛已命中以下可疑项：
{reason_lines}

物理常识：同一断面，水位不变则流量不应突变；水位与流量一般同向变化。
请综合判断这是真实水情，还是流量计/水位计/上游 virtualFlow 计算的数据异常。

只输出严格 JSON，不要 markdown 代码块、不要任何解释：
{{
  "is_anomaly": true,
  "type": "flow_level_inconsistency | level_flow_inconsistency | frozen | invalid_value | gap_masking | none",
  "severity": "low | medium | high",
  "reason": "一句话中文：现象 + 可能原因",
  "confidence": 0.8
}}"""
    system = "你是水文监测数据质量裁判，用中文输出严格 JSON，不输出任何额外文字或代码块。"

    text = await quick_ask(prompt, system, temperature=0.2, max_tokens=300)
    parsed = _parse_json(text)

    if not parsed:
        return _prefilter_fallback(reasons)

    is_anom = bool(parsed.get("is_anomaly"))
    atype = str(parsed.get("type") or "").strip().lower()
    if (not is_anom) or atype == "none" or atype not in _LABEL:
        # 智能体判定为正常 → 采纳（灵活判断，覆盖预筛的误报）
        v = _clean_verdict()
        v["source"] = "llm"
        return v

    reason = str(parsed.get("reason") or _LABEL.get(atype, "数据异常")).strip()
    return {
        "flagged": True,
        "type": atype,
        "severity": str(parsed.get("severity") or "medium"),
        "reason": reason,
        "message": _compose_message(atype, reason),
        "source": "llm",
        "confidence": _clamp(float(parsed.get("confidence") or 0.7)),
        "evaluated_ts": time.time(),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _prefilter_fallback(reasons: list) -> dict:
    """LLM 不可用时：用预筛结果兜底（弱标注）。"""
    atype = reasons[0][0]
    reason = f"{_LABEL.get(atype, '数据异常')}（预筛命中，AI 解读暂不可用）"
    return {
        "flagged": True,
        "type": atype,
        "severity": "medium",
        "reason": reason,
        "message": _compose_message(atype, reason),
        "source": "prefilter",
        "confidence": 0.5,
        "evaluated_ts": time.time(),
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _compose_message(atype: str, reason: str) -> str:
    """生成预警/标注用的富文本（前端 renderMessage 支持 **加粗**）。"""
    label = _LABEL.get(atype, "数据异常")
    field = "流量值" if atype in ("flow_level_inconsistency",) else \
            "水位值" if atype in ("level_flow_inconsistency",) else "该数值"
    return f"**{label}**：{reason}。建议核查设备并暂缓采信{field}。"


# ──────────────────────────────────────────────────────────────
# 落盘 / 读取（供 routes/data.py 用）
# ──────────────────────────────────────────────────────────────

async def _load_all() -> dict:
    if not _VERDICTS_FILE.exists():
        return {}
    try:
        txt = await asyncio.to_thread(_VERDICTS_FILE.read_text, encoding="utf-8")
        return json.loads(txt)
    except Exception as e:
        logger.warning("load anomaly_verdicts failed: %s", e)
        return {}


async def _write_all(data: dict):
    try:
        _VERDICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _VERDICTS_FILE.with_suffix(".tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        await asyncio.to_thread(tmp.write_text, payload, encoding="utf-8")
        await asyncio.to_thread(tmp.replace, _VERDICTS_FILE)
    except Exception as e:
        logger.warning("save anomaly_verdicts failed: %s", e)


async def _save_verdict(code: str, verdict: dict):
    data = await _load_all()
    data[code] = verdict
    await _write_all(data)


async def verdicts_for_all() -> dict:
    """读取侧批量取裁决，带过期判定。返回 {code: verdict}。"""
    data = await _load_all()
    now = time.time()
    out = {}
    for code, v in data.items():
        try:
            age = now - float(v.get("evaluated_ts", 0) if isinstance(v, dict) else 0)
            expired = age > _MAX_AGE_SECS
        except (TypeError, ValueError):
            expired = True
        if expired or not isinstance(v, dict):
            out[code] = {"flagged": False, "source": "none", "reason": ""}
        else:
            out[code] = v
    return out


async def verdict_for(code: str) -> dict:
    """读取侧单站取裁决（带过期）。"""
    all_v = await verdicts_for_all()
    return all_v.get(code) or {"flagged": False, "source": "none", "reason": ""}


# ──────────────────────────────────────────────────────────────
# 小工具
# ──────────────────────────────────────────────────────────────

def _fmt(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:.1f}" if f == int(f) else f"{f:.2f}"
    except Exception:
        return str(v)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _parse_json(text: str) -> Optional[dict]:
    """容错解析 LLM 返回（剥离 markdown 围栏、截取首个 {...}）。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    # 截取首个 {...} 块
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None
