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
    floodmind_url: str = "http://localhost:13014"

    # Agent LLM (DashScope / OpenAI-compatible)
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    agent_model_name: str = "qwen-plus"
    agent_temperature: float = 0.3
    agent_max_tokens: int = 4096

    # Agent paths
    reports_dir: str = "./reports"
    scheduled_tasks_db: str = "./data/scheduled_tasks.db"

    # ── 缓存与采集配置 ──
    station_codes: str = "00106,00107,00108"
    default_device_code: str = "FD000489923695"
    collector_interval: int = 300
    cache_max_raw: int = 2000
    cache_max_aligned: int = 2000
    cache_ttl: int = 600
    aligned_fill_max: int = 10
    aligned_context_max: int = 72

    class Config:
        env_file = [_aiflow_profile, _env_path]  # aiflow_profile 优先于 .env
        env_file_encoding = "utf-8"


settings = Settings()
