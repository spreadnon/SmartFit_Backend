"""依赖注入"""
from fastapi import Request, HTTPException, Depends
from workout.core.security import parse_token


async def get_current_user(user_id: int = Depends(parse_token)) -> int:
    """获取当前用户ID"""
    return user_id


async def get_request_body(request: Request) -> dict:
    """获取请求体"""
    try:
        return await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {str(e)}")
