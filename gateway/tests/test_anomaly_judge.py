"""anomaly_judge.py 单元测试 — 预筛纯函数 + 裁决降级路径。

覆盖：
- prefilter 在 6 类序列上的命中（正常/流量突刺/水位突刺/冻结/负值/缺测伪装）；
- _has_spike 在常量基线（IQR=0）上的水位大基数小倍率跳变；
- judge_station 三态降级：LLM 正常裁决 / 智能体覆盖预筛 / LLM 失败回退预筛。
"""
import asyncio
import json

import pytest

from gateway.services import anomaly_judge


# ── 测试夹具：构造序列 ──────────────────────────────────────

def _series(levels, flows, source="measured"):
    """levels / flows 等长列表（None 表示该点缺值），按时间对齐。"""
    n = max(len(levels), len(flows))
    out = []
    for i in range(n):
        lv = levels[i] if i < len(levels) else None
        fv = flows[i] if i < len(flows) else None
        out.append({
            "time": f"2026-07-19 10:{i:02d}:00",
            "waterLevel": lv,
            "virtualFlow": fv,
            "waterLevel_source": source if lv is not None else None,
            "virtualFlow_source": source if fv is not None else None,
        })
    return out


def _keys(reasons):
    return {k for k, _ in reasons}


# ── 预筛纯函数 ─────────────────────────────────────────────

class TestPrefilter:
    def test_normal_correlated_no_anomaly(self):
        # 水位与流量同向缓慢变化，无突刺
        s = _series(
            [34.00, 34.05, 34.10, 34.15, 34.20, 34.25, 34.30, 34.35],
            [10, 12, 14, 16, 18, 20, 24, 30],
        )
        assert anomaly_judge.prefilter(s) == []

    def test_flow_spike_level_flat(self):
        # 水位纹丝不动，流量夹一个 220 突刺（用户描述的核心场景）
        s = _series(
            [34.10] * 8,
            [12, 12, 12, 12, 220, 12, 12, 12],
        )
        keys = _keys(anomaly_judge.prefilter(s))
        assert "flow_level_inconsistency" in keys

    def test_level_spike_flow_flat(self):
        # 水位突刺（大基数小倍率：34.10 → 38.50），流量平稳 —— "水位同理"
        s = _series(
            [34.10, 34.10, 34.10, 34.10, 34.10, 38.50, 34.10, 34.10],
            [20.0] * 8,
        )
        keys = _keys(anomaly_judge.prefilter(s))
        assert "level_flow_inconsistency" in keys

    def test_frozen_detected(self):
        # 数值位级不变 → 传感器/上游卡死
        s = _series([34.10] * 8, [12.0] * 8)
        keys = _keys(anomaly_judge.prefilter(s))
        assert "frozen" in keys

    def test_invalid_negative_value(self):
        s = _series(
            [34.10, 34.08, -1.0, 34.12, 34.10, 34.09, 34.11, 34.10],
            [12, 13, 12, 14, 13, 12, 14, 13],
        )
        keys = _keys(anomaly_judge.prefilter(s))
        assert "invalid_value" in keys

    def test_gap_masking(self):
        # 实测占比过低却显示稳定（多数为补齐值）
        s = _series(
            [34.10, 34.10, 34.12, 34.10, 34.11, 34.10, 34.10, 34.11],
            [12, 12, 13, 12, 12, 13, 12, 12],
            source="forecast",
        )
        # 把前两点标成实测，其余仍 forecast → 实测占比 2/8 = 0.25 < 0.5
        s[0]["waterLevel_source"] = "measured"
        s[0]["virtualFlow_source"] = "measured"
        s[1]["waterLevel_source"] = "measured"
        s[1]["virtualFlow_source"] = "measured"
        keys = _keys(anomaly_judge.prefilter(s))
        assert "gap_masking" in keys

    def test_too_few_points_skips_consistency(self):
        # 配对点不足 6 → 一致性检查跳过（但仍可能命中 frozen/invalid）
        s = _series([34.10, 34.11, 34.10], [12, 12, 12])
        keys = _keys(anomaly_judge.prefilter(s))
        assert "flow_level_inconsistency" not in keys
        assert "level_flow_inconsistency" not in keys


# ── 统计小工具 ─────────────────────────────────────────────

class TestStats:
    def test_quartiles_basic(self):
        q1, q3 = anomaly_judge._quartiles([1, 2, 3, 4, 5, 6, 7, 8])
        assert q1 == 2.5
        assert q3 == 6.5

    def test_has_spike_constant_baseline_flow(self):
        # 12×7 + 220：IQR=0，回退到相对极差 → 命中
        assert anomaly_judge._has_spike([12, 12, 12, 12, 220, 12, 12, 12]) is True

    def test_has_spike_constant_baseline_level(self):
        # 水位大基数小倍率跳变 34.10 → 38.50：IQR=0，相对极差 12.9% > 5% → 命中
        assert anomaly_judge._has_spike([34.10, 34.10, 34.10, 34.10, 34.10, 38.50, 34.10, 34.10]) is True

    def test_has_spike_tiny_jitter_not_flagged(self):
        # 1cm 抖动不应被判突刺
        assert anomaly_judge._has_spike([34.10, 34.10, 34.10, 34.10, 34.10, 34.11, 34.09, 34.10]) is False

    def test_is_flat_constant(self):
        assert anomaly_judge._is_flat([34.10] * 8) is True

    def test_is_flat_real_rise(self):
        # 真实上涨事件：流量 10→60，相对极差大 → 非平稳
        assert anomaly_judge._is_flat([10, 20, 30, 40, 50, 60]) is False


# ── judge_station 降级路径（mock LLM） ────────────────────

def _setup_mocks(monkeypatch, tmp_path, llm_text):
    """统一 mock：data_cache.get_aligned / quick_ask / station_name / 落盘路径。"""
    spike_series = _series([34.10] * 8, [12, 12, 12, 12, 220, 12, 12, 12])

    async def fake_get_aligned(code, max_age=600):
        return {"records": spike_series}

    async def fake_quick_ask(prompt, system="", temperature=0.3, max_tokens=800):
        return llm_text

    monkeypatch.setattr(anomaly_judge.data_cache, "get_aligned", fake_get_aligned)
    monkeypatch.setattr(anomaly_judge, "quick_ask", fake_quick_ask)
    monkeypatch.setattr(anomaly_judge, "station_name", lambda c: "测试站")
    monkeypatch.setattr(anomaly_judge, "_VERDICTS_FILE", tmp_path / "anomaly_verdicts.json")


class TestJudgeStation:
    def test_clean_series_not_flagged(self, monkeypatch, tmp_path):
        # 无突刺的干净序列 → quick_ask 不应被调用，直接判正常
        async def fake_get_aligned(code, max_age=600):
            return {"records": _series(
                [34.00, 34.05, 34.10, 34.15, 34.20, 34.25, 34.30, 34.35],
                [10, 12, 14, 16, 18, 20, 24, 30],
            )}
        called = {"n": 0}

        async def fake_quick_ask(*a, **k):
            called["n"] += 1
            return ""

        monkeypatch.setattr(anomaly_judge.data_cache, "get_aligned", fake_get_aligned)
        monkeypatch.setattr(anomaly_judge, "quick_ask", fake_quick_ask)
        monkeypatch.setattr(anomaly_judge, "station_name", lambda c: "测试站")
        monkeypatch.setattr(anomaly_judge, "_VERDICTS_FILE", tmp_path / "v.json")

        v = asyncio.run(anomaly_judge.judge_station("00125"))
        assert v["flagged"] is False
        assert v["source"] == "none"
        assert called["n"] == 0  # 预筛未命中 → 不调 LLM

    def test_llm_confirms_anomaly(self, monkeypatch, tmp_path):
        llm = json.dumps({
            "is_anomaly": True,
            "type": "flow_level_inconsistency",
            "severity": "high",
            "reason": "流量出现突刺而水位平稳，疑似流量计故障。",
            "confidence": 0.9,
        })
        _setup_mocks(monkeypatch, tmp_path, llm)
        v = asyncio.run(anomaly_judge.judge_station("00125"))
        assert v["flagged"] is True
        assert v["source"] == "llm"
        assert v["type"] == "flow_level_inconsistency"
        assert "流量" in v["message"]

    def test_llm_overrides_prefilter(self, monkeypatch, tmp_path):
        # 预筛命中突刺，但智能体判定为正常（如确认是真实开闸放水）→ 采纳智能体
        llm = json.dumps({
            "is_anomaly": False,
            "type": "none",
            "severity": "none",
            "reason": "经核查为闸门调度引起的真实流量变化。",
            "confidence": 0.85,
        })
        _setup_mocks(monkeypatch, tmp_path, llm)
        v = asyncio.run(anomaly_judge.judge_station("00125"))
        assert v["flagged"] is False
        assert v["source"] == "llm"

    def test_llm_garbage_falls_back_to_prefilter(self, monkeypatch, tmp_path):
        _setup_mocks(monkeypatch, tmp_path, "这不是JSON，模型乱说话")
        v = asyncio.run(anomaly_judge.judge_station("00125"))
        assert v["flagged"] is True
        assert v["source"] == "prefilter"

    def test_llm_empty_falls_back_to_prefilter(self, monkeypatch, tmp_path):
        _setup_mocks(monkeypatch, tmp_path, "")
        v = asyncio.run(anomaly_judge.judge_station("00125"))
        assert v["flagged"] is True
        assert v["source"] == "prefilter"

    def test_verdict_for_expiry(self, monkeypatch, tmp_path):
        # 裁决落盘后 verdict_for 能读到；过期后视为未标注
        _setup_mocks(monkeypatch, tmp_path, json.dumps({
            "is_anomaly": True, "type": "frozen", "severity": "medium",
            "reason": "x", "confidence": 0.7,
        }))
        asyncio.run(anomaly_judge.judge_station("00125"))
        v = asyncio.run(anomaly_judge.verdict_for("00125"))
        assert v["flagged"] is True

        # 篡改时间戳为很久以前 → 过期清除
        all_v = asyncio.run(anomaly_judge._load_all())
        all_v["00125"]["evaluated_ts"] = 0.0
        asyncio.run(anomaly_judge._write_all(all_v))
        v2 = asyncio.run(anomaly_judge.verdict_for("00125"))
        assert v2["flagged"] is False
