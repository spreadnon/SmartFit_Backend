"""认证路由 - Apple登录"""
import jwt
import json
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from workout.core.config import settings
from workout.core.security import create_token
from workout.infrastructure.db.mysql import mysql_client

router = APIRouter(prefix="/auth", tags=["认证"])

APPLE_CLIENT_ID = getattr(settings, 'APPLE_CLIENT_ID', None)


class AppleLoginRequest(BaseModel):
    """Apple登录请求"""
    id_token: str
    code: Optional[str] = None
    name: Optional[str] = None


def get_apple_public_keys():
    """获取Apple公钥"""
    url = "https://appleid.apple.com/auth/keys"
    resp = requests.get(url, timeout=10)
    return resp.json()["keys"]


def verify_apple_id_token(id_token: str):
    """验证Apple ID Token"""
    try:
        headers = jwt.get_unverified_header(id_token)
        kid = headers["kid"]
        alg = headers["alg"]

        keys = get_apple_public_keys()
        public_key = None
        for key in keys:
            if key["kid"] == kid:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                break
        if not public_key:
            raise HTTPException(400, "Apple公钥不匹配")

        decode_options = {
            "verify_exp": True,
            "verify_aud": APPLE_CLIENT_ID is not None,
        }

        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=[alg],
            issuer="https://appleid.apple.com",
            audience=APPLE_CLIENT_ID,
            options=decode_options,
            leeway=60
        )
        return payload

    except Exception as e:
        print(f"Apple Token verification failed: {e}")
        if not APPLE_CLIENT_ID and "audience" in str(e).lower():
            print("⚠️ 警告: 由于未在 .env 中配置 APPLE_CLIENT_ID，跳过 aud 验证")
            return jwt.decode(id_token, public_key, algorithms=[alg], options={"verify_signature": False})
        raise HTTPException(401, f"Apple Token 无效: {str(e)}")


@router.post("/apple/login")
def apple_login(req: AppleLoginRequest):
    """Apple登录/注册"""
    print(f"🚀 收到 Apple 登录请求, id_token 长度: {len(req.id_token) if req.id_token else 0}")
    
    # 1. 验证Apple令牌
    try:
        apple_payload = verify_apple_id_token(req.id_token)
        apple_sub = apple_payload["sub"]
        apple_email = apple_payload.get("email")
        print(f"✅ Apple 验证通过: sub={apple_sub}, email={apple_email}")
    except HTTPException as e:
        print(f"❌ Apple 验证失败: {e.detail}")
        raise e
    except Exception as e:
        print(f"❌ Apple 验证出现异常: {e}")
        raise HTTPException(status_code=401, detail=f"验证失败: {str(e)}")

    # 2. 查询/创建用户
    user = mysql_client.get_user_by_apple_sub(apple_sub)
    if not user:
        user_id = mysql_client.create_user(
            apple_sub=apple_sub,
            email=apple_email,
            name=req.name
        )
        if not user_id:
            raise HTTPException(status_code=500, detail="用户注册失败")
        user = {"id": user_id, "apple_sub": apple_sub}

    # 3. 生成Token
    token = create_token(user["id"])
    print(f"🎉 登录成功，发放 Token, user_id={user['id']}")

    return {
        "code": 200,
        "msg": "Apple登录成功",
        "data": {
            "token": token,
            "user_id": user["id"],
            "apple_sub": apple_sub
        }
    }
