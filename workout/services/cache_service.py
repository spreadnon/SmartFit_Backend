"""缓存服务 - 多级缓存策略"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from core.constants import CACHE_EXPIRE_HOURS, CACHE_REDIS_TTL_SECONDS
from infrastructure.db.redis_client import redis_client


class CacheService:
    """多级缓存服务（内存 + Redis + MySQL）"""
    
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._expire_hours = CACHE_EXPIRE_HOURS
    
    def _get_cache_id(self, user_input: str, user_profile: Dict[str, Any]) -> str:
        """生成缓存唯一标识"""
        profile_str = json.dumps(user_profile, sort_keys=True, ensure_ascii=False)
        content = f"{user_input}_{profile_str}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def get(
        self, user_input: str, user_profile: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        获取缓存，返回 (数据, 来源)
        来源: "memory" | "redis" | None
        """
        cache_id = self._get_cache_id(user_input, user_profile)
        
        # 1. 检查内存缓存
        memory_result = self._get_from_memory(cache_id)
        if memory_result:
            return memory_result, "memory"
        
        # 2. 检查 Redis
        if redis_client.is_available:
            redis_result = self._get_from_redis(cache_id)
            if redis_result:
                # 回写到内存
                self._set_to_memory(cache_id, redis_result)
                return redis_result, "redis"
        
        return None, None
    
    def set(
        self, user_input: str, user_profile: Dict[str, Any], data: Dict[str, Any]
    ) -> None:
        """写入多级缓存"""
        cache_id = self._get_cache_id(user_input, user_profile)
        
        # 写入内存
        self._set_to_memory(cache_id, data)
        
        # 写入 Redis
        if redis_client.is_available:
            self._set_to_redis(cache_id, data)
    
    def _get_from_memory(self, cache_id: str) -> Optional[Dict[str, Any]]:
        """从内存获取缓存"""
        if cache_id not in self._memory_cache:
            return None
        
        cache_item = self._memory_cache[cache_id]
        cache_time = datetime.strptime(cache_item["timestamp"], "%Y-%m-%d %H:%M:%S")
        
        # 检查过期
        if datetime.now() - cache_time > timedelta(hours=self._expire_hours):
            del self._memory_cache[cache_id]
            return None
        
        return cache_item["data"]
    
    def _set_to_memory(self, cache_id: str, data: Dict[str, Any]) -> None:
        """写入内存缓存"""
        self._memory_cache[cache_id] = {
            "data": data,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def _get_from_redis(self, cache_id: str) -> Optional[Dict[str, Any]]:
        """从Redis获取缓存"""
        redis_key = f"plan_cache:{cache_id}"
        try:
            value = redis_client.get(redis_key)
            if value:
                return json.loads(value)
        except Exception as e:
            print(f"⚠️ Redis 读取失败: {e}")
        return None
    
    def _set_to_redis(self, cache_id: str, data: Dict[str, Any]) -> None:
        """写入Redis缓存"""
        redis_key = f"plan_cache:{cache_id}"
        try:
            redis_client.set(
                redis_key,
                json.dumps(data, ensure_ascii=False),
                ex=CACHE_REDIS_TTL_SECONDS
            )
        except Exception as e:
            print(f"⚠️ Redis 写入失败: {e}")
    
    def clear(self, user_input: str = None, user_profile: Dict[str, Any] = None) -> None:
        """清空缓存"""
        if user_input and user_profile:
            cache_id = self._get_cache_id(user_input, user_profile)
            self._memory_cache.pop(cache_id, None)
        else:
            self._memory_cache.clear()


# 全局缓存服务实例
cache_service = CacheService()
