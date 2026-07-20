# api/v1/plan.py
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from fitness_project.core.dependencies import (
    get_plan_cache,
    get_plan_service,
    parse_token,
)
from fitness_project.config.settings import settings
from fitness_project.services.plan_service import PlanGenerationError, normalize_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plans", tags=["训练计划"])
limiter = Limiter(key_func=get_remote_address)

@router.post("/generate")
@limiter.limit(settings.RATE_LIMIT)
async def generate_plan(
    request: Request,
    user_id: int = Depends(parse_token),
    plan_cache = Depends(get_plan_cache),
    plan_service = Depends(get_plan_service)
):
    """生成训练计划接口"""
    try:
        # 1. 解析请求体
        request_body = await request.json()
        user_input = request_body.get("user_input")
        user_profile = request_body.get("user_profile", {})
        if not user_input:
            raise HTTPException(status_code=400, detail="user_input 不能为空")
        
        # 2. 检查缓存
        cached_plan = plan_cache.get_cached_plan(user_input, user_profile, user_id)
        if cached_plan:
            return {
                "code": 200,
                "msg": "命中缓存，训练计划生成成功",
                "data": normalize_plan(cached_plan),
            }
        
        # 3. 生成计划
        plan = await plan_service.generate_plan(user_input, user_profile)
        
        # 4. 写入缓存
        plan_cache.set_cached_plan(user_input, user_profile, plan, user_id)
        
        return {
            "code": 200,
            "msg": "训练计划生成成功",
            "data": plan
        }
    except HTTPException:
        raise
    except PlanGenerationError as e:
        # e 的文案已经是可以直接展示给用户的友好提示，技术细节在 plan_service 里记过日志了。
        # 沿用 500（而不是更语义化的 503），是因为 iOS 端 NetworkManager 目前只对
        # code == 500 的响应特殊处理、直接展示 msg；其余 5xx 只会显示通用的
        # "服务器错误: xxx"，反而丢失了这里准备的友好文案。
        logger.warning("训练计划生成失败（AI 服务侧）: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        logger.exception("训练计划生成失败（未知异常）")
        raise HTTPException(status_code=500, detail="生成训练计划失败，请稍后重试")