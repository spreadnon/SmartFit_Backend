import time
import json
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis
from jwt_util import parse_token

# 导入业务逻辑层
from service import (
    prompt_cache,
    GLOBAL_EXERCISE_META,
    load_exercise_db,
    compute_global_meta,
    build_prompt,
    call_qwen,
    recursive_normalize_images,
    translate_chinese_keys_to_english
)
from jwt_util import parse_token
from db_save import save_to_mysql, get_from_mysql
from workout.training_log_api import router as training_router
from login import router as login_router

# 初始化 FastAPI 应用
app = FastAPI()

# 挂载子路由
app.include_router(training_router)
app.include_router(login_router)

# 连接 Redis
try:
    r = redis.Redis(
        host="localhost",
        port=6379,
        db=0,
        decode_responses=True,
        socket_connect_timeout=2
    )
    r.ping()
    print("✅ Redis 连接成功")
    redis_available = True
except Exception as e:
    print(f"⚠️ Redis 未启动或连接失败: {e}")
    redis_available = False

# 初始化限流器
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 全局异常捕获
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail, "data": None}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": f"服务器内部错误: {str(exc)}", "data": None}
    )

# 测试接口
@app.get("/test")
def test():
    return {"code": 200, "msg": "服务器正常运行"}

# 训练计划生成接口
@app.post("/generate-plan")
@limiter.limit("100/minute")
async def generate_plan(request: Request, user_id: int = Depends(parse_token)):
    start_total = time.perf_counter()
    
    # 1. 解析请求体
    try:
        t0 = time.perf_counter()
        request_body = await request.json()
        print(f"⏱️  解析请求体耗时: {time.perf_counter() - t0:.4f}s")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败：{str(e)}")
    
    # 2. 提取并校验参数
    user_input = request_body.get("user_input", "")
    user_profile = request_body.get("user_profile", {})
    if not user_input:
        raise HTTPException(status_code=400, detail="user_input 不能为空")

    # 3. 缓存查询（MySQL → 内存 → Redis）
    t_cache = time.perf_counter()
    cache_id = prompt_cache._get_prompt_hash(user_input, user_profile)
    redis_key = f"plan_cache:{cache_id}"
    
    # MySQL 缓存
    db_result = get_from_mysql(user_id, user_input)
    if db_result:
        print(f"📌 命中 MySQL 缓存 (用户 {user_id}), 耗时: {time.perf_counter() - t_cache:.4f}s")
        prompt_cache.set_cached_answer(user_input, user_profile, db_result)
        return {"code": 200, "msg": "命中数据库缓存，训练计划生成成功", "data": db_result}
    
    # 内存缓存
    cached_answer = prompt_cache.get_cached_answer(user_input, user_profile)
    if cached_answer:
        print(f"📌 命中内存缓存")
        save_to_mysql(user_id, [{"search_str": user_input, "search_respond": cached_answer}])
        return {"code": 200, "msg": "命中缓存，训练计划生成成功", "data": cached_answer}
    
    # Redis 缓存
    if redis_available:
        try:
            redis_val = r.get(redis_key)
            if redis_val:
                print(f"📌 命中 Redis 缓存")
                cached_answer = json.loads(redis_val)
                prompt_cache.set_cached_answer(user_input, user_profile, cached_answer)
                save_to_mysql(user_id, [{"search_str": user_input, "search_respond": cached_answer}])
                return {"code": 200, "msg": "命中缓存，训练计划生成成功", "data": cached_answer}
        except Exception as e:
            print(f"⚠️ Redis 读取失败: {e}")

    # 4. 生成训练计划（核心业务逻辑）
    try:
        # 构建提示词
        t_prompt = time.perf_counter()
        prompt = build_prompt(user_input, user_profile, GLOBAL_EXERCISE_META)
        print(f"⏱️  构建提示词耗时: {time.perf_counter() - t_prompt:.4f}s")
        
        # 调用大模型
        t_qwen = time.perf_counter()
        plan_logic = call_qwen(prompt)
        print(f"⏱️  调用大模型耗时: {time.perf_counter() - t_qwen:.4f}s")
        
        # 补充动作详情 + 转换中英文key + 归一化图片路径
        t_post = time.perf_counter()
        daily_plans = plan_logic.get("daily_plans") or plan_logic.get("每日计划") or []
        for day_plan in daily_plans:
            exercise_list = day_plan.get("exercise_list") or day_plan.get("动作列表") or []
            for action in exercise_list:
                # 复用 service 层的 GLOBAL_EXERCISE_MAP
                from service import GLOBAL_EXERCISE_MAP
                raw_name = action.get("exercise_name") or action.get("动作名称") or ""
                normalized_name = raw_name.replace(" ", "").lower()
                action_detail = GLOBAL_EXERCISE_MAP.get(normalized_name)
                
                # 关键词兜底搜索
                if not action_detail and len(normalized_name) >= 2:
                    for k, v in GLOBAL_EXERCISE_MAP.items():
                        if normalized_name in k or k in normalized_name:
                            action_detail = v
                            break
                
                # 补全动作详情
                action.setdefault("images", [])
                action.setdefault("primary_muscles", [])
                action.setdefault("instructionsCN", [])
                action.setdefault("secondary_muscles", [])
                action.setdefault("exercise_type", "")
                if action_detail:
                    action["id"] = action_detail.get("id", "")
                    action["images"] = action_detail.get("images", [])
                    action["instructionsCN"] = action_detail.get("instructionsCN", [])
                    action["secondary_muscles"] = action_detail.get("secondaryMuscles", [])
                    action["exercise_type"] = action_detail.get("category", "")
                    action["primary_muscles"] = action_detail.get("primaryMuscles", [])
        print(f"⏱️  后期补充详情耗时: {time.perf_counter() - t_post:.4f}s")
        
        # 转换中文key → 英文
        translated_plan_logic = translate_chinese_keys_to_english(plan_logic)
        
        # 归一化图片路径
        normalized_data = recursive_normalize_images(translated_plan_logic)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成训练计划失败：{str(e)}")

    # 5. 写入缓存
    prompt_cache.set_cached_answer(user_input, user_profile, translated_plan_logic)
    if redis_available:
        try:
            r.set(redis_key, json.dumps(translated_plan_logic, ensure_ascii=False), ex=60*60*24*7)
            print(f"📌 写入 Redis 缓存成功")
        except Exception as e:
            print(f"⚠️ Redis 写入失败: {e}")
    
    # 6. 写入 MySQL
    try:
        save_to_mysql(user_id, [{"search_str": user_input, "search_respond": translated_plan_logic}])
    except Exception as e:
        print(f"⚠️ MySQL 写入失败: {e}")

    # 7. 返回结果
    final_response = {
        "code": 200,
        "msg": "训练计划生成成功",
        "data": normalized_data
    }
    print(f"✅ 总处理耗时: {time.perf_counter() - start_total:.4f}s")
    return final_response