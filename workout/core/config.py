"""应用配置管理"""
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """应用配置"""
    # API Keys
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    
    # JWT
    JWT_SECRET: str = os.getenv("jwt_secret", "smartfit_default_secret_key_change_in_production")
    
    # Database
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASS: str = os.getenv("DB_PASS", "12345678")
    DB_NAME: str = os.getenv("DB_NAME", "smartfit")
    
    # Apple Login
    APPLE_CLIENT_ID: str = os.getenv("APPLE_CLIENT_ID", "")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    # Rate Limiting
    RATE_LIMIT: str = "100/minute"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    
    class Config:
        env_file = ".env"


# 全局配置实例
settings = Settings()
