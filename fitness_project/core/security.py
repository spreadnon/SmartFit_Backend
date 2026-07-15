"""JWT creation and FastAPI authentication dependencies."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException

from fitness_project.config.settings import settings


ALGORITHM = "HS256"


def create_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"user_id": user_id, "exp": expires_at},
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )


def parse_token(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="登录已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="登录无效") from exc

    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise HTTPException(status_code=401, detail="无效登录")
    return user_id
