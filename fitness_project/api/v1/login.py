"""Sign in with Apple endpoint."""
import json
from typing import Optional

import jwt
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fitness_project.config.settings import settings
from fitness_project.core.security import create_token
from fitness_project.infrastructure.db.mysql import mysql_client


router = APIRouter(prefix="/api/auth", tags=["认证"])


class AppleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)
    code: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=100)


def _verify_apple_token(id_token: str) -> dict:
    if not settings.APPLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="APPLE_CLIENT_ID 未配置")
    try:
        token_header = jwt.get_unverified_header(id_token)
        response = requests.get(
            "https://appleid.apple.com/auth/keys",
            timeout=10,
        )
        response.raise_for_status()
        jwk = next(
            item
            for item in response.json()["keys"]
            if item["kid"] == token_header["kid"]
        )
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        return jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            issuer="https://appleid.apple.com",
            audience=settings.APPLE_CLIENT_ID,
            options={"require": ["exp", "iss", "aud", "sub"]},
            leeway=60,
        )
    except HTTPException:
        raise
    except (requests.RequestException, StopIteration, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Apple 登录服务暂不可用") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Apple Identity Token 无效") from exc


@router.post("/apple/login")
def apple_login(request: AppleLoginRequest):
    payload = _verify_apple_token(request.id_token)
    user = mysql_client.upsert_user(
        apple_sub=payload["sub"],
        email=payload.get("email"),
        name=request.name,
    )
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "user_id": user["id"],
            "apple_sub": user["apple_sub"],
            "email": user.get("email"),
            "name": user.get("name"),
            "token": create_token(user["id"]),
        },
    }
