# api/v1/plan.py
from fastapi import APIRouter, Request, Depends, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from core.dependencies import get_plan_cache, get_plan_service, parse_token
from config.settings import settings
from utils.json_util import UserRequest

router = APIRouter(prefix="/plan", tags=["训练计划"])
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
                "data": cached_plan
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成训练计划失败: {str(e)}")