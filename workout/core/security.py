"""JWT认证工具"""
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Header, Depends
from workout.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def create_token(user_id: int) -> str:
    """生成JWT Token"""
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def parse_token(authorization: str = Header(None)) -> int:
    """解析JWT Token，返回user_id"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效登录")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录无效")


async def get_current_user(user_id: int = Depends(parse_token)) -> int:
    """FastAPI依赖：获取当前用户ID"""
    return user_id
