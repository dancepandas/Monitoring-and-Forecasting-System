import asyncio
import contextvars
import json
import logging
import queue
import re
from typing import Optional, AsyncGenerator
from floodmind import Agent, ModelClient, build_agent_tool
from floodmind.agent.runtime.contracts.messages import Message, MessageStore
from floodmind.agent.runtime.contracts.permissions import PermissionBehavior, PermissionDecision
from floodmind.agent.runtime.services.tool_execution_service import ToolExecutionService

from ..config import settings
from .agent_tools import TOOLS_REGISTRY, TOOL_DESCRIPTIONS
from . import session_store
from .system_events import set_session, reset_session

logger = logging.getLogger(__name__)

# -- Patch MessageBuilder to handle dict-format messages and strip "human" role --
from floodmind.agent.native.message_builder import MessageBuilder as _MB
_orig_build_memory = _MB.build_memory_messages

def _fixed_build_memory(self, memory_messages):
    result = []
    for msg in (memory_messages or []):
        # Handle both dict and object formats
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or ""
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", None) or getattr(msg, "role", None) or ""
            content = getattr(msg, "content", "")
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        if role in ("user", "assistant", "system"):
            result.append({"role": role, "content": str(content)})
    return result

_MB.build_memory_messages = _fixed_build_memory
# -- End patch --


def _allow_all_permissions(tool_input: dict) -> PermissionDecision:
    return PermissionDecision(behavior=PermissionBehavior.ALLOW)


def _patched_check_permissions(self, tool, perm_input, session_id, agent_tier='main', mode='execution'):
    return PermissionDecision(behavior=PermissionBehavior.ALLOW)


ToolExecutionService._check_permissions = _patched_check_permissions


def _strip_internal_prefix(message: str) -> str:
    """把前端注入的'当前系统时间'前缀以及面板上下文包装剥离，返回用户原始问题。"""
    if not message:
        return message
    # 1. 去掉 [当前系统时间: ...] 前缀
    text = re.sub(r"^\[当前系统时间:[^\]]*\]\s*\n*", "", message.strip())
    # 2. 如果是面板上下文包装，提取真正的用户问题
    m = re.search(r"用户问题：(.*?)\n+请根据以上面板数据回答用户问题。", text, re.S)
    if m:
        return m.group(1).strip()
    return text.strip()


_SYSTEM_PROMPT = """你是 FloodMind 水文监测指挥智能体，负责郴州地区水文数据的实时监控、分析预警和报告生成，同时承担 7×24 无人值守场景下的自动告警研判与推送决策。

## 身份与职责
- 管理测站：郴州(00125)、郴州-坳上(00230)、郴州-鸡嘴桥下游(00231)、郴州-燕泉河(00234)，均位于湖南郴州
- 数据来源：aiflow2 平台 realTimeInfo 实时接口 + 本地累积缓存（每5分钟追加），冷启动初期历史数据有限
- 核心能力：水位/流量/流速查询、实时视频地址获取、时序预测(Chronos-2)、预警研判、报告生成、知识库检索、系统历史查询
- 不编写脚本、不生成图片、不操作文件系统
- 自动值守：收到以 **[值守任务]** 开头的消息时，进入 7×24 值守模式——独立调查核实、判断真实险情/设备故障/数据异常、决定是否推送告警

## 预警阈值体系
- 本系统采用**每站独立阈值**，每个测站的水位（level）和流量（flow）预警阈值可独立配置，不同河段断面可设置不同标准
- 查询阈值：get_station_thresholds（指定测站编码，返回该站专属水位+流量阈值，未配置时显示回退默认值）
- 修改阈值：update_station_threshold（指定测站编码 + 类别 level/flow + 级别 blue/yellow/orange/red + 新值）→ 立即生效并持久化
- update_warning_standard 仅修改全局默认值或变化率，不区分站点；优先使用 update_station_threshold 为单个站点调优
- 查询阈值历史：get_threshold_changes — 查看阈值变更日志（谁在什么时候改了什么）

## 工具使用指南
### 实时数据与设备
- query_latest（水位+流量+流速+视频地址，最快）→ query_water_level / query_flow（历史序列）→ compare_stations（多站统计对比）
- query_devices（设备在线状态）→ query_video_status（摄像头实时画面地址）
### 预警处置
- list_warnings / list_active_alerts（查看当前预警/告警）→ get_station_thresholds（查阈值）→ update_station_threshold（调阈值）
- generate_disposal（生成分级处置建议）→ send_notification（推送通知）
- acknowledge_alert（确认告警）/ resolve_alert（解除告警）
### 趋势预测
- analyze_trend（线性趋势，快）→ run_forecast（Chronos-2 预测，精度高）
### 报告
- generate_report（生成 docx 报告）→ query_reports（查看已有报告）
### 系统运维与历史
- diagnose_system（全系统健康检查）→ retry_failed_reports（重试失败报告）
- list_alert_history（±历史告警记录）→ get_threshold_changes（±阈值变更日志）→ get_system_diagnosis（±诊断历史）→ get_recent_events（±系统事件时间线）
- CreateScheduledTask / ListScheduledTasks / CancelScheduledTask
- Glob / Grep — 仅用于本地项目文件检索

## 值守模式规范（收到 [值守任务] 消息时遵循）
### 研判工具链（按优先级）
1. diagnose_system → 2. query_latest → 3. query_water_level / query_flow → 4. query_video_status → 5. analyze_trend / run_forecast → 6. list_active_alerts / get_station_thresholds → 7. get_threshold_changes（查看历史阈值） → 8. list_alert_history（查历史告警去重） → 9. send_notification
### 推送决策标准
| 事件类型 | 推送策略 |
|---|---|
| 红色/橙色水文预警 | 立即推送，附当前值、阈值、趋势 |
| 黄色水文预警 | 先看视频或近1小时趋势，确认风险再推送 |
| 数据缓存为空 / 全站无数据 | 若 30min 内未推送过同类事件，推送一次给管理员 |
| 数据停更 > 2 小时 | 黄色，推送给值班员 |
| 数据停更 > 4 小时 | 红色，推送给值班员 + 负责人 |
| 数据异常跳变 | 先看视频/历史判断传感器故障，确认非误报再推送 |
| 多站同时预警 | 升级推送，通知负责人 |
### 消息内容规范
调用 send_notification 时必须传入 `alert_id`，message 包含：异常现象简述 + 当前值与阈值对比 + 判断结论（真实险情/设备故障/数据异常/持续观察） + 建议处置措施
### 值守约束
- 不推测超出数据范围的结论
- 同一事件 30min 内不重复推送（先调 list_active_alerts 查 notify_count）
- 推送前尽量完成一次视频或数据复核
- 研判前先调用 get_station_thresholds 确认该站精确阈值

## 沟通规范
- 中文回复，专业简洁，直接给结论，不绕弯
- 数据用 Markdown 表格呈现，关键数值加粗
- 数据为空时明确告知用户并建议用 diagnose_system 排查
- 不寒暄、不客套、不推测超出数据范围的结论
- 涉及预警时明确级别（蓝/黄/橙/红）并给出处置建议
- 回答系统历史类问题前先调用对应的查询工具（list_alert_history / get_threshold_changes / get_system_diagnosis / get_recent_events），不要依赖记忆或猜测

## 时间格式
YYYY-MM-DD HH:MM:SS.000，根据用户说的"最近N小时"自行计算 begin/end。"""



def _build_tool_strategy(mcp_connected: bool) -> str:
    """根据 MCP 实际连接状态构建工具使用策略段落。不硬编码，MCP 不可用时知识库指导完全不出现。"""
    lines = []
    if mcp_connected:
        lines.append("""## 知识库工具（当前可用）
- search_knowledge_base：检索水文领域专业文档（原理、规范、处置标准、案例等）
- search_with_scores：检索并返回相似度分数，适合精确匹配
- list_partitions：查看知识库产品分区
- list_documents：查看知识库文档统计

**使用策略**：涉及水文专业原理、预报方法、处置规范等知识性问题时，优先用知识库检索。
实时监测数据（水位、流量）用内置 query 工具。两者互补：知识库提供"怎么做"，内置工具提供"现在是什么"。""")
    return "\n".join(lines) if lines else ""


class InMemoryStore:
    """轻量级内存记忆,确保 OpenAI 兼容的 role 值。超过 80% max_tokens 时自动压缩早期轮次。"""

    def __init__(self, llm=None, max_tokens: int = 65536):
        self._store = MessageStore()
        self._llm = llm
        self.max_tokens = max_tokens
        self._compressed_summary: str = ""
        self._last_full_rounds: int = 0  # 压缩时保留的最后完整轮次数

    def add_user_message(self, content: str) -> None:
        self._store.add_user_message(content)

    def add_ai_message(self, content: str) -> None:
        self._store.add_ai_message(content)

    def set_llm(self, llm) -> None:
        self._llm = llm

    def set_status_callback(self, callback) -> None:
        pass

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 2)  # 粗略估算: 2字符≈1token

    def _total_tokens(self, messages: list[dict]) -> int:
        return sum(self._estimate_tokens(m.get("content", "")) for m in messages)

    def get_openai_messages(self, system_prompt: str = None) -> list[dict]:
        all_msgs = []
        if system_prompt:
            all_msgs.append({"role": "system", "content": system_prompt})
        for msg in self._store.messages:
            role = "user" if msg.role == "human" else "assistant" if msg.role == "ai" else msg.role
            all_msgs.append({"role": role, "content": str(msg.content)})

        # 去掉最后一条 user 消息(executor 会单独添加,避免重复)
        if all_msgs and all_msgs[-1]["role"] == "user":
            all_msgs.pop()

        total = self._total_tokens(all_msgs)
        threshold = int(self.max_tokens * 0.8)

        if total <= threshold or len(self._store.messages) < 40:
            # 不需要压缩(<6轮对话)
            return all_msgs

        # 压缩: 保留前2轮 + 中间压缩 + 最后2轮
        msgs = list(self._store.messages)
        if msgs and msgs[-1].role == "human":
            msgs.pop()

        keep_first = 4   # 前2轮 (4条消息)
        keep_last = 4    # 最后2轮 (4条消息)
        if len(msgs) <= keep_first + keep_last:
            return all_msgs

        first = msgs[:keep_first]
        last = msgs[-keep_last:]
        to_compress = msgs[keep_first:-keep_last]

        # 生成压缩摘要
        if self._llm and not self._compressed_summary:
            try:
                conv_text = "\n".join(
                    f"{'用户' if m.role == 'human' else '助手'}: {str(m.content)[:300]}"
                    for m in to_compress
                )
                prompt = (
                    "将以下对话历史压缩为结构化摘要,保留关键信息(数据查询结果、工具调用、决策),"
                    "不要遗漏数值和结论。只输出摘要本身:\n\n" + conv_text
                )
                result = self._llm.invoke(prompt)
                self._compressed_summary = (result.content if hasattr(result, "content") else str(result)).strip()
            except Exception:
                self._compressed_summary = f"[已压缩 {len(to_compress)//2} 轮对话]"

        # 构建: 系统提示词 + 前2轮完整 + 压缩摘要 + 最后2轮完整
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        for m in first:
            role = "user" if m.role == "human" else "assistant"
            result.append({"role": role, "content": str(m.content)})

        if self._compressed_summary:
            result.append({"role": "system", "content": "[对话历史压缩]\n" + self._compressed_summary})

        for m in last:
            role = "user" if m.role == "human" else "assistant"
            result.append({"role": role, "content": str(m.content)})

        return result

    def get_full_messages(self) -> list[Message]:
        return list(self._store.messages)

    def get_messages(self) -> list[Message]:
        return list(self._store.messages)


class AgentService:
    """每个 session 复用一个 AgentService 实例。持久化用本地 session_store。"""

    _instances: dict[str, "AgentService"] = {}

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self._system_prompt = _SYSTEM_PROMPT
        self.model_client = ModelClient(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model_name=settings.agent_model_name,
            temperature=settings.agent_temperature,
            max_tokens=settings.agent_max_tokens,
        )
        tools = []
        for name, (schema_cls, fn) in TOOLS_REGISTRY.items():
            tool = build_agent_tool(
                name=name,
                description=TOOL_DESCRIPTIONS.get(name, schema_cls.__doc__ or f"Tool: {name}"),
                args_schema=schema_cls,
                func=fn,
                check_permissions_fn=_allow_all_permissions,
            )
            tools.append(tool)

        self.memory = InMemoryStore(
            llm=self.model_client,
            max_tokens=settings.agent_max_tokens,
        )

        # ── MCP 连接状态追踪 ──
        self._mcp_connected = False

        self.agent = Agent(
            llm=self.model_client,
            tools=tools,
            system_prompt=self._system_prompt,
            memory=self.memory,
            session_id=session_id or "",
        )

        # 连接 MCP 服务器 (如 HydroRAG 知识库)
        self._connect_mcp()

        # ── 确保自定义提示词实际送达 LLM ──
        kb_section = _build_tool_strategy(self._mcp_connected)
        custom_prompt = self._system_prompt
        if kb_section:
            custom_prompt += "\n\n" + kb_section
        self.agent.raw._agent_info.prompt = custom_prompt + """

{project_context}

## 当前时间
{current_time_context}

## 会话信息
{session_env}

## 可用工具
{tool_descriptions}"""
        self.agent.raw._rebuild_system_prompts()

        # 保存完整 system prompt 到文件，方便调试
        try:
            from pathlib import Path
            descs = self.agent.raw._build_tool_descriptions(self.agent.raw._orchestrator_registry)
            kb_section = _build_tool_strategy(self._mcp_connected)
            full_parts = [self._system_prompt]
            if kb_section:
                full_parts.append(kb_section)
            full_parts.append(f"## 工具描述（自动注入）\n{descs}")
            full = "# 系统提示词\n\n" + "\n\n".join(full_parts)
            p = Path(__file__).parent.parent / "data" / "last_system_prompt.txt"
            p.write_text(full, encoding="utf-8")
            logger.info(f"debug prompt saved to {p}")
        except Exception:
            pass

        # ── 验证：输出 actual system prompts ──
        try:
            executor = self.agent.raw._orchestrator_executor
            if executor and executor.system_prompts:
                for i, sp in enumerate(executor.system_prompts):
                    logger.info("Actual system_prompts[%d] (len=%d, first 200): %s",
                        i, len(sp), sp[:200])
            else:
                logger.warning("Actual system_prompts: EMPTY — 自定义提示词可能未生效！")
        except Exception as e:
            logger.warning("Failed to read actual system_prompts: %s", e)

        # 确保 session 存在于 SQLite（失败不阻塞，智能体仍可用）
        if session_id:
            try:
                existing = session_store.get_session(session_id)
                if not existing:
                    session_store.create_session(session_id=session_id)
            except Exception:
                logger.warning("floodmind session init failed for %s, agent continues without persistence", session_id)

    def _connect_mcp(self):
        """加载并连接 floodmind mcp.json 中配置的 MCP 服务器，记录连接状态。"""
        self._mcp_connected = False
        try:
            from floodmind.config.settings import settings as flood_settings
            from floodmind.agent.mcp_client import get_mcp_client_pool

            servers = flood_settings.mcp.servers if hasattr(flood_settings, 'mcp') else []
            if not servers:
                logger.info("MCP: 无配置的服务端")
                return

            pool = get_mcp_client_pool()
            connected = pool.connect_all(servers)
            if connected <= 0:
                logger.info("MCP: 所有服务端连接失败")
                return

            native = self.agent.raw
            registry = native._orchestrator_registry
            total = 0
            for server_name, conn in pool._connections.items():
                count = native._register_mcp_tools(server_name, conn, registry)
                logger.info("MCP [%s]: %d tools registered", server_name, count)
                total += count

            if total > 0:
                self._mcp_connected = True
                logger.info("MCP: 已连接，共 %d 个工具可用", total)
        except Exception as e:
            logger.warning("MCP connection failed: %s", e)
            self._mcp_connected = False

    @classmethod
    def get_or_create_agent(cls, session_id: str) -> "AgentService":
        if session_id not in cls._instances:
            cls._instances[session_id] = cls(session_id=session_id)
        return cls._instances[session_id]

    def _generate_title(self, user_message: str, answer_text: str) -> str:
        # 优先用模型生成标题；失败或返回空时基于用户问题做兜底
        fallback = self._fallback_title(user_message)
        try:
            prompt = (
                "根据以下对话生成3-8字简短标题,只返回标题:\n\n"
                f"用户: {user_message[:200]}\nAI: {answer_text[:300]}"
            )
            logger.info("title prompt: %s", prompt[:200])
            result = self.model_client.invoke(prompt)
            logger.info("title result type=%s repr=%s", type(result).__name__, repr(result)[:200])
            title = (result.content if hasattr(result, "content") else str(result)).strip()
            title = title.replace('"', '').replace("'", '').replace("标题：", "").replace("标题:", "").strip()
            logger.info("title cleaned: %s", title)
            if title and len(title) >= 2:
                logger.info("title generated: %s", title)
                return title[:20]
            logger.warning("title empty from model, fallback: %s", fallback)
        except Exception as e:
            logger.exception("title generation failed: %s, fallback: %s", e, fallback)
        return fallback

    @staticmethod
    def _fallback_title(user_message: str) -> str:
        text = (user_message or "").strip()
        if not text:
            return "新对话"
        # 去掉常见动词/疑问词后取前 8 字
        cleaned = re.sub(r"^[请帮我|帮我|请|请问|一下|查询|查一下|查|看看|看一下|分析|预测|生成|运行]+", "", text)
        cleaned = cleaned.strip("，,。.?？!！:\n ")
        if not cleaned:
            cleaned = text
        return cleaned[:8] or "新对话"

    def _sync_stream(self, message: str, q: queue.Queue) -> None:
        try:
            for event in self.agent.stream(message):
                q.put(event)
            q.put(None)
        except Exception as e:
            logger.exception("Agent sync stream error")
            q.put({"type": "error", "content": str(e)})
            q.put(None)

    async def stream(
        self, session_id: str, message: str, uploaded_files: Optional[list] = None,
    ) -> AsyncGenerator[dict, None]:
        # 首次调用时保存完整 system prompt
        if not getattr(self, '_prompt_saved', False):
            self._prompt_saved = True
            try:
                descs = self.agent.raw._build_tool_descriptions(self.agent.raw._orchestrator_registry)
                kb_section = _build_tool_strategy(self._mcp_connected)
                full_parts = [_SYSTEM_PROMPT]
                if kb_section:
                    full_parts.append(kb_section)
                full_parts.append(f"## 工具描述（自动注入）\n{descs}")
                full = "# 系统提示词\n\n" + "\n\n".join(full_parts)
                from pathlib import Path as _Path
                (_Path(__file__).parent.parent / "data" / "last_system_prompt.txt").write_text(full, encoding="utf-8")
                logger.info("debug prompt saved")
            except Exception as e:
                logger.warning("prompt save failed: %s", e)

        session_store.add_message(session_id, "user", parts=[{"type": "text", "text": _strip_internal_prefix(message)}])
        self.agent.raw.session_id = session_id

        # 设置当前操作者，工具中的 write_event 自动继承 session_id
        token = set_session(session_id)

        loop = asyncio.get_event_loop()
        q: queue.Queue = queue.Queue()
        ctx = contextvars.copy_context()
        future = loop.run_in_executor(None, ctx.run, self._sync_stream, message, q)

        def _on_stream_done(f):
            try:
                f.result()
            except Exception as ex:
                logger.exception("[agent] sync stream failed: %s", ex)
            finally:
                # 确保消费者能退出
                try:
                    q.put(None, block=False)
                except queue.Full:
                    pass

        future.add_done_callback(_on_stream_done)

        answer_text = ""
        reasoning_text = ""

        try:
            while True:
                event = await loop.run_in_executor(None, q.get)
                if event is None:
                    break
                t = event.get("type", "")
                if t == "answer_delta":
                    answer_text += event.get("content", "")
                elif t == "thought_delta":
                    reasoning_text += event.get("content", "")
                yield event

            # 保存助手消息（在流结束后，带上完整内容）
            parts = []
            if reasoning_text:
                parts.append({"type": "reasoning", "text": reasoning_text})
            if answer_text:
                parts.append({"type": "text", "text": answer_text})
            if parts:
                session_store.add_message(session_id, "assistant", parts=parts)

            session_info = session_store.get_session(session_id)
            current_title = session_info.get("title") if session_info else None
            if session_info and (not current_title or current_title == "新对话"):
                title = self._generate_title(_strip_internal_prefix(message), answer_text)
                logger.info("renaming session %s title from '%s' to '%s'", session_id, current_title, title)
                session_store.rename_session(session_id, title)

            yield {"type": "stream_end"}

        except Exception as e:
            logger.exception("Agent stream error")
            yield {"type": "error", "content": str(e)}
        finally:
            reset_session(token)

    async def respond_permission(self, session_id: str, ask_id: str, approved: bool) -> dict:
        return {"type": "error", "content": "权限系统暂未启用"}


async def stream_agent(
    session_id: str, message: str, uploaded_files: Optional[list] = None,
) -> AsyncGenerator[dict, None]:
    svc = AgentService.get_or_create_agent(session_id)
    async for event in svc.stream(session_id, message, uploaded_files):
        yield event


async def respond_permission(
    session_id: str, ask_id: str, approved: bool,
) -> dict:
    svc = AgentService.get_or_create_agent(session_id)
    return await svc.respond_permission(session_id, ask_id, approved)
