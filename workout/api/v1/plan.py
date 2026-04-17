"""训练计划路由"""
import time
from fastapi import APIRouter, Depends, Request
from typing import Any
from api.deps import get_current_user, get_request_body
from services.plan_service import plan_service

router = APIRouter(prefix="/plans", tags=["训练计划"])


@router.post("/generate")
async def generate_plan(
    request: Request,
    user_id: int = Depends(get_current_user),
) -> Any:
    """生成智能训练计划"""
    start_total = time.perf_counter()
    
    # 解析请求体
    t0 = time.perf_counter()
    request_body = await get_request_body(request)
    print(f"⏱️  解析请求体耗时: {time.perf_counter() - t0:.4f}s")
    
    # 提取参数
    user_input = request_body.get("user_input", "")
    user_profile = request_body.get("user_profile", {})
    
    # 校验参数
    if not user_input:
        return {"code": 400, "msg": "user_input 不能为空", "data": None}
    
    # 调用服务生成计划
    result = plan_service.generate_plan(
        user_input=user_input,
        user_profile=user_profile,
        user_id=user_id
    )
    
    print(f"📤 接口返回数据 (耗时: {time.perf_counter() - start_total:.4f}s)")
    return result
