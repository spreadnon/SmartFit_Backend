"""应用主入口"""
import os
import sys

# 将项目根目录加入Python路径，确保能找到workout包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from core.config import settings
from api.v1 import router as api_router


# 创建FastAPI应用
app = FastAPI(
    title="SmartFit API",
    description="智能健身训练计划API",
    version="1.0.0"
)

# 初始化限流器
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# 挂载路由
app.include_router(api_router)


@app.get("/test")
def test():
    """健康检查接口"""
    return {"code": 200, "msg": "服务器正常运行"}


# 全局异常处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一处理HTTP异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail, "data": None}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """统一处理系统异常"""
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": f"服务器内部错误: {str(exc)}", "data": None}
    )


if __name__ == "__main__":
    import uvicorn
    # 使用 __main__:app 因为我们通过 sys.path 直接运行
    uvicorn.run(
        "__main__:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
