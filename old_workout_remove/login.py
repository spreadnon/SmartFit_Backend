import uvicorn
import jwt
import json
import requests
import pymysql
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from jwt_util import create_token
from fastapi import FastAPI, HTTPException, Request, APIRouter

load_dotenv()
app = FastAPI(title="Apple 登录")
router = APIRouter(prefix="/api/apple", tags=["Login"])

# ==================== CORS 配置 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境建议改为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义异常处理器，确保错误也返回相同的 JSON 结构
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "msg": exc.detail,
            "data": None
        }
    )

# 你的业务 JWT
SECRET_KEY = os.getenv("JWT_SECRET", "smartfit_secure_default_jwt_secret_key_long_enough")
ALGORITHM = "HS256"
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID") # 注意：正式环境必须配置此项

# ==================== 数据库连接配置 ====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "12345678",
    "database": "smartfit",
    "charset": "utf8mb4"
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# 初始化表结构
def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 创建用户表，记录 Apple sub 和相关信息
            create_users_table = """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                apple_sub VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255),
                name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(create_users_table)
        conn.commit()
    finally:
        conn.close()

# 启动时执行表初始化
init_db()

if __name__ == "__main__":
    uvicorn.run("login:app", host="0.0.0.0", port=8001, reload=True)

# ==================== Apple 公钥获取 ====================
def get_apple_public_keys():
    url = "https://appleid.apple.com/auth/keys"
    resp = requests.get(url, timeout=10)
    return resp.json()["keys"]

# ==================== 验证 Apple id_token ====================
def verify_apple_id_token(id_token: str):
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

        # 验证选项
        decode_options = {
            "verify_exp": True,
            "verify_aud": APPLE_CLIENT_ID is not None, # 如果没有配置 CLIENT_ID，跳过验证 (仅限开发调试)
        }

        # 验证签名、过期、iss、aud
        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=[alg],
            issuer="https://appleid.apple.com",
            audience=APPLE_CLIENT_ID,
            options=decode_options,
            leeway=60 # 允许 60 秒的时间偏差，解决 "iat" is in the future 错误
        )
        return payload  # sub, email, email_verified...

    except Exception as e:
        print(f"Apple Token verification failed: {e}")
        # 如果是 audience 验证失败且没有配置 APPLE_CLIENT_ID
        if not APPLE_CLIENT_ID and "audience" in str(e).lower():
            print("⚠️ 警告: 由于未在 .env 中配置 APPLE_CLIENT_ID，跳过 aud 验证")
            # 这种情况下可以尝试重新 decode 不验证 aud
            return jwt.decode(id_token, public_key, algorithms=[alg], options={"verify_signature": False})
            
        raise HTTPException(401, f"Apple Token 无效: {str(e)}")

# ==================== 前端传参结构 ====================
class AppleLoginRequest(BaseModel):
    id_token: str       # iOS 端返回的 identityToken
    code: str = None    # 可选，用于获取用户姓名
    name: str = None    # 首次授权才有

# ==================== Apple 登录核心接口 ====================
@router.post("/login")
def apple_login(req: AppleLoginRequest):
    # 1. 验证 Apple 令牌，拿到官方数据
    print(f"🚀 收到 Apple 登录请求, id_token 长度: {len(req.id_token) if req.id_token else 0}")
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

    # 2. 根据 apple_sub 查询/创建用户（自动注册）
    user = get_user_by_apple_sub(apple_sub)
    if not user:
        # 自动注册
        user_id = create_user(
            apple_sub=apple_sub,
            email=apple_email,
            name=req.name
        )
        if not user_id:
            print("❌ 数据库注册失败，无法继续")
            raise HTTPException(status_code=500, detail="用户注册失败")
        user = {"id": user_id, "apple_sub": apple_sub}

    # 3. 生成通用 Token
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

# ==================== 工具函数 ====================
def create_business_token(user_id: int):
    expire = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(
        {"user_id": user_id, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

def get_user_by_apple_sub(apple_sub):
    print(f"🔍 查询用户: apple_sub={apple_sub}")
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = "SELECT id, apple_sub, email, name FROM users WHERE apple_sub = %s"
            cursor.execute(sql, (apple_sub,))
            result = cursor.fetchone()
            if result:
                print(f"✅ 查找到用户: user_id={result['id']}")
            else:
                print(f"ℹ️ 未查找到用户，将进行自动注册")
            return result
    except Exception as e:
        print(f"❌ 查询用户失败: {e}")
        return None
    finally:
        conn.close()

def create_user(apple_sub, email=None, name=None):
    print(f"🆕 开始注册新用户: apple_sub={apple_sub}, email={email}, name={name}")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO users (apple_sub, email, name) VALUES (%s, %s, %s)"
            cursor.execute(sql, (apple_sub, email, name))
            user_id = cursor.lastrowid
        conn.commit()
        print(f"✅ 注册成功: user_id={user_id}")
        return user_id
    except Exception as e:
        print(f"❌ 注册用户失败: {e}")
        return None
    finally:
        conn.close()