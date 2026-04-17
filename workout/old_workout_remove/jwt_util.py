# jwt_util.py
import jwt
import os
from datetime import datetime, timedelta
from fastapi import HTTPException, Header
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 两个服务必须用一样的密钥！
SECRET_KEY = os.getenv("JWT_SECRET", "smartfit_secure_default_jwt_secret_key_long_enough")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# ------------------- 登录服务使用：生成Token -------------------
def create_token(user_id: int):
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"user_id": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ------------------- 订单服务使用：解析Token -------------------
def parse_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效登录")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录无效")