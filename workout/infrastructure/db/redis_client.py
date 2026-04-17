"""Redis客户端"""
import json
import redis
from typing import Optional
from core.config import settings


class RedisClient:
    """Redis连接管理"""
    _instance = None
    _client = None
    _available = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        try:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2
            )
            self._client.ping()
            self._available = True
            print("✅ Redis 连接成功")
        except Exception as e:
            print(f"⚠️ Redis 连接失败: {e}")
            self._available = False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def get(self, key: str) -> Optional[str]:
        if not self._available:
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            print(f"⚠️ Redis get 失败: {e}")
            return None
    
    def set(self, key: str, value: str, ex: int = 604800) -> bool:
        if not self._available:
            return False
        try:
            self._client.set(key, value, ex=ex)
            return True
        except Exception as e:
            print(f"⚠️ Redis set 失败: {e}")
            return False


# 全局Redis客户端实例
redis_client = RedisClient()
