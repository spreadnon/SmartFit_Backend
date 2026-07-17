# config/settings.py
try:
    from pydantic import BaseSettings
except ImportError:
    from pydantic_settings import BaseSettings
from pathlib import Path
import os

class Settings(BaseSettings):
    # 项目配置
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_CONNECT_TIMEOUT: float = 2.0
    # 千问 API 配置
    QWEN_API_KEY: str = ""
    QWEN_API_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    QWEN_MODEL: str = "qwen-turbo"
    QWEN_TEMPERATURE: float = 0.3
    # 缓存配置
    CACHE_EXPIRE_HOURS: int = 24
    REDIS_CACHE_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7
    # 限流配置
    RATE_LIMIT: str = "100/minute"
    # 数据库配置
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASS: str = os.getenv("DB_PASS", "12345678")
    DB_NAME: str = os.getenv("DB_NAME", "smartfit")
    # 鉴权配置
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "smartfit_default_secret_key_change_in_production",
    )
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
    APPLE_CLIENT_ID: str = os.getenv("APPLE_CLIENT_ID", "com.SmartFitness")
    # 动作库路径
    EXERCISE_DB_PATH: Path = Path("free-exercise-db-main/dist/exercisesCN.json")

    class Config:
        env_file = ".env"  # 加载 .env 文件
        env_file_encoding = "utf-8"

# 全局配置实例
settings = Settings()