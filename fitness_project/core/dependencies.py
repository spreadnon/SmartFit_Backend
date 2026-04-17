# core/dependencies.py
from fastapi import Depends
from cache.impl import PlanCache
from services.plan_service import PlanGenerationService
from jwt_util import parse_token

# 单例模式提供缓存实例
_plan_cache = None
def get_plan_cache():
    global _plan_cache
    if _plan_cache is None:
        _plan_cache = PlanCache()
    return _plan_cache

# 单例模式提供计划生成服务
_plan_service = None
def get_plan_service():
    global _plan_service
    if _plan_service is None:
        _plan_service = PlanGenerationService()
    return _plan_service

# 假的 token 解析（先让项目跑起来）
def parse_token():
    return 10086
    
# 导出依赖
dependencies = {
    "parse_token": parse_token,
    "get_plan_cache": get_plan_cache,
    "get_plan_service": get_plan_service
}