"""Agent 轻量工具 — 非流式 LLM 调用，用于预报解读、告警复盘、报告生成等场景。"""

import logging
from ..config import settings

logger = logging.getLogger(__name__)


async def quick_ask(prompt: str, system: str = "", temperature: float = 0.3,
                     max_tokens: int = 800) -> str:
    """轻量 LLM 调用，返回纯文本回复。用于不需要工具调用的分析场景。"""
    import httpx

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"{settings.dashscope_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
                json={
                    "model": settings.agent_model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            logger.warning("quick_ask failed: %s", r.status_code)
        except Exception as e:
            logger.warning("quick_ask error: %s", e)
    return ""


async def interpret_forecast(station_code: str, station_name: str,
                              history: list[dict], forecast: list[dict],
                              field: str = "流量") -> str:
    """Agent 解读 Chronos-2 预报结果。"""
    if not forecast:
        return "暂无预报数据可供解读。"

    unit = "m³/s" if field == "流量" else "m"
    history_vals = [p["y"] for p in history[-24:] if p.get("y") is not None]
    forecast_vals = [p["y"] for p in forecast[:12] if p.get("y") is not None]
    if not forecast_vals:
        return "暂无有效预报数据可供解读。"
    all_future = forecast_vals
    peak_val = max(all_future) if all_future else 0
    peak_idx = all_future.index(peak_val) if all_future else 0
    peak_time = forecast[peak_idx]["t"] if peak_idx < len(forecast) else "—"
    latest = history_vals[-1] if history_vals else 0
    trend = "上涨" if len(forecast_vals) >= 2 and forecast_vals[-1] > forecast_vals[0] else "下降" if len(forecast_vals) >= 2 and forecast_vals[-1] < forecast_vals[0] else "平稳"

    # 构建数据上下文，处理无历史数据的情况
    data_lines = [
        f"- 站点：{station_name}（{station_code}）",
        f"- 指标：{field}",
        f"- 最新实测值：{latest:.1f} {unit}",
        f"- 未来 12 步预报趋势：{trend}",
        f"- 预报峰值：{peak_val:.1f} {unit}，出现于 {peak_time}",
    ]
    if history_vals:
        data_lines.append(f"- 历史均值：{sum(history_vals)/len(history_vals):.1f} {unit}（近 {len(history_vals)} 点）")
    else:
        data_lines.append("- 历史数据：暂无足够实测数据")

    prompt = f"""你是水文监测专家。请用 3-5 句简洁中文解读以下预报数据：

{chr(10).join(data_lines)}

要求：
1. 第一句概括整体趋势判断（正常/需关注/有风险）
2. 说明峰值是否接近警戒值、是否需要关注
3. 给出简明建议
4. 语言接地气，面向值班人员
5. 不要输出 markdown 代码块，直接输出纯文本"""

    system = "你是水文监测数据分析师，用中文输出简洁专业的预报解读，面向一线值班人员。"
    return await quick_ask(prompt, system, max_tokens=400)


async def generate_postmortem(event: dict, station_name: str = "") -> str:
    """为已解除的告警生成复盘总结。"""
    title = event.get("title", "")
    level = event.get("level", "")
    alert_type = event.get("alert_type", "")
    message = event.get("message", "")
    resolution = event.get("resolution", "")
    triggered_at = event.get("triggered_at", 0)
    resolved_at = event.get("resolved_at", 0)
    from datetime import datetime
    trigger_time = datetime.fromtimestamp(triggered_at).strftime("%m/%d %H:%M") if triggered_at else "?"
    resolve_time = datetime.fromtimestamp(resolved_at).strftime("%m/%d %H:%M") if resolved_at else "?"
    duration = ""
    if triggered_at and resolved_at:
        minutes = int((resolved_at - triggered_at) / 60)
        if minutes >= 60:
            duration = f"{minutes // 60}h{minutes % 60}min"
        else:
            duration = f"{minutes}min"

    prompt = f"""请为以下已解除的告警生成 2-3 句复盘总结：

- 站点：{station_name or '未知'}
- 事件：{title}
- 级别：{level}
- 类型：{alert_type}
- 描述：{message}
- 触发时间：{trigger_time}
- 解除时间：{resolve_time}
- 持续时长：{duration}
- 处置：{resolution}

要求：
1. 第一句概括事件经过
2. 第二句给出简要建议（如是否需要调整阈值、是否属于季节性常态）
3. 语言专业简洁，面向运维团队
4. 不要输出 markdown，直接纯文本"""

    system = "你是水文监测运维专家，用中文输出简洁专业的告警复盘，面向运维团队。"
    return await quick_ask(prompt, system, max_tokens=300)
