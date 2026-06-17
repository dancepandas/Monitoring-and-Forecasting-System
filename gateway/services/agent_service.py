import asyncio
import json
import logging
import queue
from floodmind import Agent, ModelClient, build_agent_tool
from floodmind.agent.runtime.contracts.messages import Message, MessageStore
from floodmind.agent.runtime.contracts.permissions import PermissionBehavior, PermissionDecision
from floodmind.agent.runtime.services.tool_execution_service import ToolExecutionService

from ..config import settings
from .agent_tools import TOOLS_REGISTRY, TOOL_DESCRIPTIONS
from . import session_store

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

# -- Force re-resolve ModelClient to ensure patches apply --
from floodmind.agent.native.model_client import ModelClient as _MC  # noqa: F811


def _allow_all_permissions(tool_input: dict) -> PermissionDecision:
    return PermissionDecision(behavior=PermissionBehavior.ALLOW)


def _patched_check_permissions(self, tool, perm_input, session_id):
    return PermissionDecision(behavior=PermissionBehavior.ALLOW)


ToolExecutionService._check_permissions = _patched_check_permissions

_SYSTEM_PROMPT = """\
你是 FloodMind 水文监测指挥智能体,服务于"水文监测指挥核心"系统。可调用工具获取数据、生成处置建议、运行预报、生成报告、检索文件、管理定时任务。

## 工作原则
1. 理解用户意图后,优先调用工具获取结构化数据。
2. 不要编写脚本、不要生成图片、不要直接操作文件(除非使用报告/文件检索/定时任务工具)。
3. 解释结果时使用中文,简洁专业;前端负责渲染表格、图表和地图。
4. 当工具需要人工确认时,必须向用户说明原因并等待批准。
5. 纯文本回答。
6. 回答要高效精简,直接给出结论和数据,不要寒暄、不要客套话、不要冗长的解释。
7. 输出使用标准 Markdown 格式:标题用 #/##/###,列表用 -,表格用 |,代码用 ```,数据用加粗 **值** 突出。

## 时间参数格式
所有时间参数必须使用格式: YYYY-MM-DD HH:MM:SS.000
示例: begin="2026-06-14 18:00:00.000", end="2026-06-15 18:00:00.000"
当用户说"最近N小时"时,你需要根据当前时间计算出 begin 和 end。

## 核心工具详解

### 数据查询
- query_water_level(station_code, begin, end, count)
  查询测站的水位原始数据。station_code 必填(如"00106"),begin/end 为时间范围,count 默认200。
  返回: {code, msg, data: [{measureTime, waterLevel, status}], pageInfo}

- query_flow(station_code, begin, end, count)
  查询测站的流量原始数据。参数同上,data 中字段为 virtualFlow。

- query_latest(station_codes)
  查询测站最新一条水位上报数据(reportDataPage)。station_codes 逗号分隔,默认"00106"。
  返回: {stations: {code: {level: {...}}}, updated}。优先用此接口快速获取最新状态。

- list_stations()
  列出系统已接入的测站清单,返回测站编码、名称、所在河流。

- compare_stations(station_codes, metric, begin, end)
  对比多个测站的水位或流量统计(max/min/avg)。metric 为 "level" 或 "flow"。

- query_devices(station_code)
  查询测站下的设备清单及在线状态。

- query_video_status(station_code)
  查询测站的视频监控摄像头状态。

### 预警处置
- list_warnings(station_codes, level)
  从实时数据中检测超过预警标准的测站。station_codes 逗号分隔(默认查全部),level 筛选指定级别。
  返回: {warnings, total, standards: {level: {...}, flow: {...}}}。自动比对水位和流量。

- generate_disposal(station_code, level, metric)
  针对指定测站和预警级别生成分级处置建议。level: blue/yellow/orange/red, metric: level/flow。

- update_warning_standard(category, level, value)
  修改预警标准阈值。category: level(水位,m)/flow(流量,m³/s), level: blue/yellow/orange/red, value: 新阈值。

### 预报分析
- run_forecast(station_code, prediction_length, target)
  基于过去3天历史流量运行Chronos时序预测。prediction_length默认72,target默认"Flow"。

- analyze_trend(station_code, metric, days)
  分析水位或流量的变化趋势(最小二乘法),返回斜率、趋势方向和最新值。

### 报告生成
- generate_report(report_type, station_code, date)
  生成Word格式水文报告。type: daily/weekly/monthly,date格式YYYY-MM-DD。

- query_reports()
  列出已生成的所有报告文件。

### 文件检索
- Glob(pattern, path)
  按glob模式搜索文件。

- Grep(pattern, path, glob)
  按正则表达式搜索文件内容。

### 定时任务
- CreateScheduledTask(task_type, cron, params)
  创建定时任务。task_type: generate_report/run_forecast/check_warnings。cron如"0 8 * * *"。

- ListScheduledTasks()
  列出所有定时任务。

- CancelScheduledTask(task_id)
  取消指定定时任务。

## 常见场景指导
- 用户问"最新水位": 调用 list_stations 获取编码,然后调 query_latest。
- 用户问"过去N小时数据": 先调 query_latest 快速确认有数据,再调 query_water_level 或 query_flow 指定时间范围。时间格式必须包含 .000 毫秒后缀。
- 数据返回为空: 告知用户无数据,建议用 query_latest 查看最新记录,或调 query_devices 检查设备状态。
- 用户问设备/视频: 调 query_devices 和 query_video_status。
- 用户问"预测/预报": 调 run_forecast 和 analyze_trend。"""


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
        self.agent = Agent(
            llm=self.model_client,
            tools=tools,
            system_prompt=_SYSTEM_PROMPT,
            memory=self.memory,
            session_id=session_id or "",
        )

        # 连接 MCP 服务器 (如 HydroRAG 知识库)
        self._connect_mcp()

        # 确保 session 存在于 SQLite（失败不阻塞，智能体仍可用）
        if session_id:
            try:
                existing = session_store.get_session(session_id)
                if not existing:
                    session_store.create_session(session_id=session_id)
            except Exception:
                logger.warning("floodmind session init failed for %s, agent continues without persistence", session_id)

    def _connect_mcp(self):
        """加载并连接 floodmind mcp.json 中配置的 MCP 服务器"""
        try:
            from floodmind.config.settings import settings as flood_settings
            from floodmind.agent.mcp_client import get_mcp_client_pool

            servers = flood_settings.mcp.servers if hasattr(flood_settings, 'mcp') else []
            if not servers:
                return

            pool = get_mcp_client_pool()
            connected = pool.connect_all(servers)
            if connected <= 0:
                return

            native = self.agent.raw
            registry = native._orchestrator_registry
            for server_name, conn in pool._connections.items():
                count = native._register_mcp_tools(server_name, conn, registry)
                logger.info("MCP [%s]: %d tools registered", server_name, count)
        except Exception as e:
            logger.warning("MCP connection failed: %s", e)

    @classmethod
    def get_or_create_agent(cls, session_id: str) -> "AgentService":
        if session_id not in cls._instances:
            cls._instances[session_id] = cls(session_id=session_id)
        return cls._instances[session_id]

    def _generate_title(self, user_message: str, answer_text: str) -> str:
        try:
            prompt = (
                "根据以下对话生成3-8字简短标题,只返回标题:\n\n"
                f"用户: {user_message[:200]}\nAI: {answer_text[:300]}"
            )
            result = self.model_client.invoke(prompt)
            title = (result.content if hasattr(result, "content") else str(result)).strip()
            title = title.replace('"', '').replace("'", '')
            return title[:20] or "新对话"
        except Exception:
            return "新对话"

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
        session_store.add_message(session_id, "user", parts=[{"type": "text", "text": message}])
        self.agent.raw.session_id = session_id

        loop = asyncio.get_event_loop()
        q: queue.Queue = queue.Queue()
        loop.run_in_executor(None, self._sync_stream, message, q)

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
            if session_info and (not session_info.get("title")):
                title = self._generate_title(message, answer_text)
                session_store.rename_session(session_id, title)

            yield {"type": "stream_end"}

        except Exception as e:
            logger.exception("Agent stream error")
            yield {"type": "error", "content": str(e)}

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
