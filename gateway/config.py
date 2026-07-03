import os
from pydantic_settings import BaseSettings

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_aiflow_profile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiflow_profile.env")


class Settings(BaseSettings):
    aiflow_username: str = ""
    aiflow_password: str = ""
    aiflow_base_url: str = "https://aiflow2.dashuiyun.cn:9999/prod-api"
    jwt_secret: str = "change-me"
    jwt_expire_hours: int = 24
    chronos_url: str = "http://localhost:15001"
    # floodmind_url 已废弃，系统直接运行 FastAPI 网关，不再需要代理

    # Agent LLM (DashScope / OpenAI-compatible)
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    agent_model_name: str = "qwen-plus"
    agent_temperature: float = 0.3
    agent_max_tokens: int = 4096

    # 百炼语音（CosyVoice TTS + Paraformer ASR），复用 dashscope_api_key，不新增密钥
    dashscope_workspace_id: str = "llm-3kqn1siocgzbz9sp"   # TTS WebSocket 业务空间专属域名
    tts_model: str = "cosyvoice-v3-flash"
    tts_voice: str = "longanyang"                           # v3-flash 系统音色（v2 不接受公共音色，已弃用）
    asr_model: str = "paraformer-realtime-v2"
    ffmpeg_path: str = "ffmpeg"                              # conda 自带，PATH 可用

    # Agent paths
    reports_dir: str = "./reports"
    scheduled_tasks_db: str = "./data/scheduled_tasks.db"

    # ── 缓存与采集配置 ──
    # 注意：此处默认站点列表需与 station_names.STATIONS 保持一致（新增站点两处都改）。
    # config 是底层模块，不能在初始化时反向 import services（会循环导入），故不做自动填充。
    station_codes: str = "00125,00230,00231,00234"
    default_device_code: str = "FD000848891909"   # 主站(郴州)设备码；其余站点设备码见 station_names.STATIONS
    collector_interval: int = 300
    cache_max_raw: int = 2000
    cache_max_aligned: int = 2000
    cache_ttl: int = 600
    aligned_fill_max: int = 10
    aligned_context_max: int = 72

    class Config:
        env_file = [_aiflow_profile, _env_path]  # aiflow_profile 优先于 .env
        env_file_encoding = "utf-8"
        extra = "ignore"  # 容忍 .env 中已删除的历史字段（如 floodmind_url）


settings = Settings()
