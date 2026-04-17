# main.py
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from config.settings import settings
from core.logger import setup_logger
from api.v1.plan import router as plan_router
from api.v1.training import router as training_router
from api.v1.login import router as login_router

# 初始化日志
setup_logger()
logger = logging.getLogger(__name__)

# 初始化 FastAPI
app = FastAPI()#title="健身计划生成API", version="1.0"

# 注册路由
app.include_router(plan_router)
app.include_router(training_router)
app.include_router(login_router)

# 配置限流
app.state.limiter = limiter  # 从plan.py导入或统一初始化
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 全局异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail, "data": None}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"服务器内部错误: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": f"服务器内部错误: {str(exc)}", "data": None}
    )

# 健康检查接口
@app.get("/test", tags=["健康检查"])
async def test():
    return {"code": 200, "msg": "服务器正常运行", "data": None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )