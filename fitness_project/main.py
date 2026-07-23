# main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from fitness_project.api.v1.login import router as login_router
from fitness_project.api.v1.plan import limiter, router as plan_router
from fitness_project.api.v1.training import router as training_router
from fitness_project.config.settings import settings
from fitness_project.core.logger import setup_logger
from fitness_project.infrastructure.db.mysql import mysql_client

# 初始化日志
setup_logger()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create missing tables without making the health endpoint DB-dependent."""
    try:
        mysql_client.init_tables()
    except Exception:
        logger.exception("数据库初始化失败")
    yield


# 初始化 FastAPI
app = FastAPI(title="SmartFit API", version="1.1.0", lifespan=lifespan)

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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": "请求参数校验失败", "data": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"服务器内部错误: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误", "data": None}
    )


# 健康检查接口
@app.get("/test", tags=["健康检查"])
async def test():
    return {"code": 200, "msg": "samrtfit服务器正常运行", "data": None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "fitness_project.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
