# core/dependencies.py
from fitness_project.cache.impl import PlanCache
from fitness_project.services.plan_service import PlanGenerationService
from fitness_project.core.security import parse_token

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

# 导出依赖
dependencies = {
    "parse_token": parse_token,
    "get_plan_cache": get_plan_cache,
    "get_plan_service": get_plan_service
}