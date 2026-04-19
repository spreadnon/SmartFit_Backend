import os
import json
import time
from http import client
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import numpy as np
import hashlib
from datetime import datetime, timedelta
# 👇 新增这一行：导入 BaseModel
from pydantic import BaseModel
from langchain.memory import ConversationBufferMemory, VectorStoreRetrieverMemory
#限流降级（防止过载，保障核心功能）
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis
#保存到mysql
from db_save import save_to_mysql, get_from_mysql
from jwt_util import parse_token
from fastapi import FastAPI, HTTPException, Request, Depends
from training_log_api import router as training_router # 导入新的训练日志路由
from login import router as login_router # 导入登录路由

# 加载环境变量（千问API Key）
load_dotenv()  # 加载.env文件
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# 初始化 FastAPI 应用
app = FastAPI()

# 挂载训练日志路由
app.include_router(training_router)
app.include_router(login_router)

# 连接本地 Redis（默认无密码）
try:
    r = redis.Redis(
        host="localhost",
        port=6379,
        db=0,
        decode_responses=True,  # 自动把 bytes 转成字符串
        socket_connect_timeout=2 # 快速失败，不卡死服务
    )
    # 立即测试连接，如果失败后续逻辑将跳过 Redis
    r.ping()
    print("✅ Redis 连接成功")
    redis_available = True
except Exception as e:
    print(f"⚠️ Redis 未启动或连接失败 (将使用本地内存和数据库缓存): {e}")
    redis_available = False

# 👇 必须添加在 app = FastAPI() 之后！
@app.get("/test")  # GET 接口，无需请求体
def test():
    return {"code": 200, "msg": "服务器正常运行"}

# ====================== 新增：Prompt-Answer缓存层 ======================
class PromptAnswerCache:
    def __init__(self, expire_hours=168):
        # 缓存结构：{prompt_hash: {"answer": 答案, "timestamp": 时间戳, "prompt": 原始Prompt}}
        self.cache = {}
        self.expire_hours = expire_hours  # 缓存有效期（小时）

    def _get_prompt_hash(self, prompt, profile):
        """生成Prompt和Profile的哈希值（作为唯一标识）"""
        # 将用户请求和画像结合起来作为标识，避免不同画像的用户串流
        profile_str = json.dumps(profile, sort_keys=True, ensure_ascii=False)
        content = f"{prompt}_{profile_str}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def get_cached_answer(self, prompt, profile):
        """获取缓存的答案（若存在且未过期）"""
        prompt_hash = self._get_prompt_hash(prompt, profile)
        if prompt_hash not in self.cache:
            return None
        
        # 检查是否过期
        cache_item = self.cache[prompt_hash]
        cache_time = datetime.strptime(cache_item["timestamp"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - cache_time > timedelta(hours=self.expire_hours):
            del self.cache[prompt_hash]  # 删除过期缓存
            return None
        
        return cache_item["answer"]

    def set_cached_answer(self, prompt, profile, answer):
        """写入缓存"""
        prompt_hash = self._get_prompt_hash(prompt, profile)
        self.cache[prompt_hash] = {
            "answer": answer,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": prompt
        }

    def clear_cache(self, prompt=None, profile=None):
        """清空缓存（可选指定Prompt）"""
        if prompt and profile:
            prompt_hash = self._get_prompt_hash(prompt, profile)
            self.cache.pop(prompt_hash, None)
        else:
            self.cache = {}

# 初始化缓存
prompt_cache = PromptAnswerCache(expire_hours=24)

# 定义请求体模型（对应 iOS 传过来的参数）
class UserRequest(BaseModel):
    user_input: str  # 用户自然语言需求（如「新手，每周3天，家用哑铃」）
    user_profile: dict  # 用户画像（水平/器械/目标部位等）

# 读取本地ExerciseDB中文数据
def load_exercise_db():
    try:
        with open("free-exercise-db-main/dist/exercisesCN.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                print("⚠️  文件读取成功，但内容为空！")
            else:
                # ✅ 统一处理图片路径：把 "/" 换成 "_"，并去掉 ".jpg" 后缀，匹配 iOS 本地资源格式
                for exercise in data:
                    if "images" in exercise:
                        exercise["images"] = [
                            img.replace("/", "_").replace(".jpg", "") 
                            for img in exercise["images"]
                        ]
                print(f"✅ ExerciseDB 加载成功，并已完成图片路径预处理，共 {len(data)} 条数据")
            return data
    except Exception as e:
        print(f"❌ 加载动作库失败: {e}")
        return []

# 全局变量：服务启动时加载一次
GLOBAL_EXERCISE_DB = load_exercise_db()

# 预计算元数据和动作名称映射
def compute_global_meta(exercise_db):
    if not exercise_db:
        return {}, {}
    
    # 提取元数据（仅包含训练编排必要的辅助信息，移除图片等大字段）
    meta = {
        "total_exercises": len(exercise_db),
        "available_equipment_types": [x for x in list(set([e.get("equipment", "") for e in exercise_db])) if x],
        "difficulty_levels": [x for x in list(set([e.get("level", "") for e in exercise_db])) if x],
        "target_muscle_groups": [x for x in list(set([",".join(e.get("primaryMuscles", [])) for e in exercise_db])) if x]
    }
    
    # 动作映射：支持中英文名称，并进行归一化处理（去掉空格）以增强匹配成功率
    mapping = {}
    for e in exercise_db:
        name_cn = e.get("nameCN", "")
        name_en = e.get("name", "")
        if name_cn:
            mapping[name_cn.replace(" ", "")] = e
        if name_en:
            # 同时也支持归一化的英文名称匹配
            mapping[name_en.replace(" ", "").lower()] = e
            
    return meta, mapping

GLOBAL_EXERCISE_META, GLOBAL_EXERCISE_MAP = compute_global_meta(GLOBAL_EXERCISE_DB)


# # 短期记忆：内存列表（模拟ConversationBufferMemory）
# short_term_memory = []

# # 长期记忆：模拟向量库（向量+文本+元数据）
# long_term_memory = {
#     "vectors": [],  # 存储向量
#     "texts": [],    # 存储文本
#     "metadatas": [] # 存储元数据
# }

# # ===================== 模拟Embedding（简化版） =====================
# def simple_embedding(text):
#     """模拟文本转向量：用字符的ASCII码均值生成3维向量"""
#     if not text:
#         return np.zeros(3)
#     avg_ascii = sum(ord(c) for c in text) / len(text)
#     return np.array([avg_ascii/100, avg_ascii/200, avg_ascii/300])

# # ===================== 模拟余弦相似度计算 =====================
# def cosine_similarity(vec1, vec2):
#     """计算两个向量的余弦相似度"""
#     dot_product = np.dot(vec1, vec2)
#     norm1 = np.linalg.norm(vec1)
#     norm2 = np.linalg.norm(vec2)
#     if norm1 == 0 or norm2 == 0:
#         return 0
#     return dot_product / (norm1 * norm2)

# def retrieve_long_term_memory(query):
#     """检索和查询最相关的Top-2长期记忆"""
#     query_vec = simple_embedding(query)
#     # 计算相似度
#     similarities = [cosine_similarity(query_vec, vec) for vec in long_term_memory["vectors"]]
#     # 取Top-2的索引
#     top_indices = np.argsort(similarities)[-2:][::-1]
#     # 返回对应的文本
#     retrieved = [long_term_memory["texts"][i] for i in top_indices if similarities[i] > 0.1]
#     return "\n".join(retrieved) if retrieved else "无相关长期记忆"

# # ===================== 记忆更新 =====================
# def update_short_term_memory(user_input, ai_answer):
#     """更新短期记忆（内存追加）"""
#     short_term_memory.append({"human": user_input, "ai": ai_answer})

# def update_long_term_memory(content):
#     """更新长期记忆（向量库写入）"""
#     vec = simple_embedding(content)
#     long_term_memory["vectors"].append(vec)
#     long_term_memory["texts"].append(content)
#     long_term_memory["metadatas"].append({"timestamp": datetime.now()})


# 格式化千问请求提示词（关键：引导大模型输出结构化结果）
def build_prompt(user_input, user_profile, exercise_db_meta):
    # # 1. 检索长期记忆
    # ltm = retrieve_long_term_memory(user_input)
    # # 2. 加载短期记忆（拼接为文本）
    # stm = "\n".join([f"Human: {item['human']} AI: {item['ai']}" for item in short_term_memory])
    
    # # 3. 构建提供给大模型的记忆上下文（无需编造AI回答，只提供历史）
    # memory_context = f"长期记忆相关的参考：{ltm}\n最近几次连续对话（短期记忆）：{stm}"

     # ========== 核心：伤病史→禁忌动作映射表（可无限扩展） ==========
    injury_avoid_map = {
        "肩伤": ["肩推", "推肩", "过头推举", "站姿推举", "哑铃肩推", "杠铃肩推", "前平举", "颈后推举"],
        "腰伤": ["硬拉", "早安式", "体前屈", "负重深蹲（大重量）", "山羊挺身（负重）"],
        "膝伤": ["深蹲", "箭步蹲", "保加利亚分腿蹲", "腿举（大重量）", "提踵（负重）"],
        "腕伤": ["俯卧撑", "卧推（窄距）", "哑铃弯举", "杠铃弯举", "农夫行走"],
        "肘伤": ["臂屈伸", "锤式弯举", "三头肌下压（大重量）", "杠铃卧推（宽距）"]
    }

    # ========== 解析用户输入中的伤病史 ==========
    # 提取用户提到的所有伤病史（如 "肩伤、腰伤" → ["肩伤", "腰伤"]）
    user_injuries = []
    for injury in injury_avoid_map.keys():
        if injury in user_input:
            user_injuries.append(injury)
    
    # 汇总所有需要禁止的动作关键词
    avoid_action_keywords = []
    for injury in user_injuries:
        avoid_action_keywords.extend(injury_avoid_map[injury])

    prompt = f"""
    你是专业的健身教练，需要根据用户需求和ExerciseDB动作库，生成精准的训练计划编排逻辑。
    【用户画像】：{json.dumps(user_profile, ensure_ascii=False)}
    【ExerciseDB元数据】：{json.dumps(exercise_db_meta, ensure_ascii=False)}
    【用户需求】：{user_input}
    请严格按照以下规则生成编排逻辑：
    1. 动作必须从ExerciseDB中选择，优先选复合动作，避免孤立动作过多；
    2. 难度匹配用户水平（新手=Beginner，中级=Intermediate，高级=expert）；
    3. 仅选择用户可用器械的动作；
    4. 伤病史避坑（最高优先级）：
        - 用户受伤部位：{user_injuries}
        - 绝对禁止的动作关键词：{avoid_action_keywords}
        - 要求：任何包含以上关键词的动作都不能出现在计划中，且避开所有对受伤部位有压力的动作；
    5. 输出格式为JSON，包含：训练分化（如每周3练,每周4练,每周5练,每周6练）、每日计划（动作名称、组数、次数、顺序）；
    6. 符合健身原理：高手每组6-8次（4组），中级每组8-10次（3-4组），新手每组8-12次（3组）；组间休息60-120秒；渐进超负荷提示。
    
    输出示例：
    {{
        "training_split": "每周3练",
        "daily_plans": [
            {{
                "training_day": "第一练",
                "exercise_list": [
                    {{
                        "exercise_name": "杠铃深蹲",
                        "sets": 3,
                        "reps": "8-12",
                        "order": 1,
                        "equipment": "杠铃",
                        "difficulty": "新手",
                        "images":[],
                        "instructionsCN":[]
                    }}
                ]
            }}
        ]
    }}
    """
    return prompt

# 调用千问大模型
def call_qwen(prompt):
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen-turbo",
        "input": {"messages": [{"role": "user", "content": prompt}]},
        "parameters": {"result_format": "json", "temperature": 0.3}
    }
    try:
        print(f"【千问API请求】headers={headers}, data={data}")  # 打印请求信息
        response = requests.post(QWEN_API_URL, headers=headers, json=data, timeout=30)
        print(f"【千问API响应】status_code={response.status_code}, content={response.text}")  # 打印响应信息
        response.raise_for_status()  # 触发 HTTP 错误
        result = response.json()
        # 检查返回格式是否正确
        if "output" not in result or "choices" not in result["output"] or len(result["output"]["choices"]) == 0:
            raise Exception(f"千问返回格式异常：{result}")
        plan_json = result["output"]["choices"][0]["message"]["content"]
        # 验证 JSON 格式
        plan_logic = json.loads(plan_json)
        return plan_logic
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"千问返回的内容不是合法JSON：{plan_json}, 错误：{str(e)}")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=response.status_code, detail=f"千问API HTTP错误：{response.text}")
    except Exception as e:
        return {
            "训练分化": "离线～全身3天（A/B/A循环）",
            "每日计划": [
                {"训练日": "A", "动作列表": [{"动作名称": "哑铃深蹲", "组数": 3, "次数": "12-15", "顺序": 1, "器械": "哑铃", "难度": "新手"}]}
            ]
        }



# 初始化限流器：100次/分钟（适配百人并发）
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])#, storage_uri="redis://localhost:6379"
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ====================== 新增：全局异常捕获，统一返回格式 ======================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    统一处理所有的 HTTPException，返回 {code, msg, data} 格式
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "msg": exc.detail,
            "data": None
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    统一处理未捕获的 500 系统错误
    """
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "msg": f"服务器内部错误: {str(exc)}",
            "data": None
        }
    )

# 定义训练计划生成接口（POST 请求）
@app.post("/generate-plan")
@limiter.limit("100/minute")  # 单IP每分钟最多100次请求
# @limiter.global_limit("100/minute") #全局限流每分钟最多100次请求
# 核心逻辑：生成智能训练计划
async def generate_plan(request: Request, user_id: int = Depends(parse_token)):
    # 1. 读取并解析请求体
    start_total = time.perf_counter()
    try:
        t0 = time.perf_counter()
        request_body = await request.json()  # 异步读取 JSON 请求体
        print(f"⏱️  解析请求体耗时: {time.perf_counter() - t0:.4f}s")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败：{str(e)}")
    
    # 2. 提取参数（兼容缺失的情况）
    user_input = request_body.get("user_input", "")
    user_profile = request_body.get("user_profile", {})

    # 校验必要参数
    if not user_input : #or not user_profile
        raise HTTPException(status_code=400, detail="user_input 和 user_profile 不能为空")

    # 2.5 统一缓存查找（内存 + Redis）
    t_cache = time.perf_counter()
    cache_id = prompt_cache._get_prompt_hash(user_input, user_profile)
    redis_key = f"plan_cache:{cache_id}"
    
    # ✅ 修改：关联 user_id 查询数据库
    db_result = get_from_mysql(user_id, user_input)
    if db_result:
        print(f"📌 命中 MySQL 缓存 (用户 {user_id}), 耗时: {time.perf_counter() - t_cache:.4f}s")
        # 同步向内存和 Redis 写入
        prompt_cache.set_cached_answer(user_input, user_profile, db_result)
        return {
            "code": 200,
            "msg": "命中数据库缓存，训练计划生成成功",
            "data": db_result
        }
    
    # 首先检查内存缓存
    cached_answer = prompt_cache.get_cached_answer(user_input, user_profile)
    if cached_answer:
        print(f"📌 命中内存缓存")

        # 1. 获取数据
        data = [
            {"search_str": user_input,
            "search_respond": cached_answer
            }
        ]
        # 2. 调用另一个文件，保存到数据库，关联 user_id
        save_to_mysql(user_id, data)

        return {
            "code": 200,
            "msg": "命中缓存，训练计划生成成功",
            "data": cached_answer
        }
    
    # 其次检查 Redis 缓存
    if redis_available:
        try:
            redis_val = r.get(redis_key)
            if redis_val:
                print(f"📌 命中 Redis 缓存")
                cached_answer = json.loads(redis_val)
                # 同步回内存缓存
                prompt_cache.set_cached_answer(user_input, user_profile, cached_answer)
                
                # ✅ 修改：Redis 命中也关联 user_id 保存到数据库
                data = [
                    {"search_str": user_input, "search_respond": cached_answer}
                ]
                save_to_mysql(user_id, data)
    
                return {
                    "code": 200,
                    "msg": "命中缓存，训练计划生成成功",
                    "data": cached_answer
                }
        except Exception as e:
            print(f"⚠️ Redis 读取失败: {e}")

    # 3. 使用全局元数据构建提示词
    t_meta = time.perf_counter()
    print(f"⏱️  获取全局元数据耗时: {time.perf_counter() - t_meta:.4f}s (预加载已优化)")
    
    # 4. 构建提示词
    try:
        t_prompt = time.perf_counter()
        prompt = build_prompt(user_input, user_profile, GLOBAL_EXERCISE_META)
        print(f"⏱️  构建提示词耗时: {time.perf_counter() - t_prompt:.4f}s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建提示词失败：{str(e)}")
    
    # 5. 调用千问大模型获取编排逻辑
    try:
        t_qwen = time.perf_counter()
        plan_logic = call_qwen(prompt)
        print(f"⏱️  调用大模型耗时: {time.perf_counter() - t_qwen:.4f}s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用大模型失败：{str(e)}")
    
    # 6. 结合ExerciseDB补充动作详情（兼容中英文 Key）
    try:
        t_post = time.perf_counter()
        # 兼容性查找：尝试获取每日计划列表
        daily_plans = plan_logic.get("daily_plans") or plan_logic.get("每日计划") or []
        
        for day_plan in daily_plans:
            # 兼容性查找：尝试获取动作列表
            exercise_list = day_plan.get("exercise_list") or day_plan.get("动作列表") or []
            
            for action in exercise_list:
                # 1. 归一化精准匹配（去掉空格）
                raw_name = action.get("exercise_name") or action.get("动作名称") or ""
                normalized_name = raw_name.replace(" ", "").lower()
                action_detail = GLOBAL_EXERCISE_MAP.get(normalized_name)
                
                # 2. 如果精准匹配失败，尝试关键词保底搜索（例如“自重深蹲” -> 包含“深蹲”）
                if not action_detail and len(normalized_name) >= 2:
                    for k, v in GLOBAL_EXERCISE_MAP.items():
                        if normalized_name in k or k in normalized_name:
                            action_detail = v
                            break
                
                # 确保基础结构存在，防止 iOS 端解析失败
                action.setdefault("images", [])
                action.setdefault("primary_muscles", [])
                action.setdefault("instructionsCN", [])
                action.setdefault("secondary_muscles", [])
                action.setdefault("exercise_type", "")
                
                if action_detail:
                    # 强力补全 ID、图片、肌肉等本地核心数据
                    action["id"] = action_detail.get("id", "")
                    action["images"] = action_detail.get("images", [])
                    action["instructionsCN"] = action_detail.get("instructionsCN", [])
                    action["secondary_muscles"] = action_detail.get("secondaryMuscles", [])
                    action["exercise_type"] = action_detail.get("category", "")
                    action["primary_muscles"] = action_detail.get("primaryMuscles", [])
        print(f"⏱️  后期补充详情耗时: {time.perf_counter() - t_post:.4f}s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"补充动作详情失败：{str(e)}")
    
     # ✅ 关键步骤：调用转换函数，将所有中文 key 转为英文（必须执行！）
    translated_plan_logic = translate_chinese_keys_to_english(plan_logic)
    
    # 7. 写入缓存（内存 + Redis）
    prompt_cache.set_cached_answer(user_input, user_profile, translated_plan_logic)
    
    # 写入 Redis
    if redis_available:
        try:
            r.set(redis_key, json.dumps(translated_plan_logic, ensure_ascii=False), ex=60*60*24*7)
            print(f"📌 非缓存命中，生成答案并写入内存和 Redis 缓存")
        except Exception as e:
            print(f"⚠️ Redis 写入失败: {e}")
    
    # 写入 MySQL
    try:
        # ✅ 新增：新生成的计划也保存到数据库，关联 user_id
        data = [
            {"search_str": user_input, "search_respond": translated_plan_logic}
        ]
        save_to_mysql(user_id, data)
    except Exception as e:
        print(f"⚠️ MySQL 写入失败: {e}")

    # 7. 返回标准化结果前，强制进行图片路径归一化（确保即使是缓存旧数据也能被修复）
    normalized_data = recursive_normalize_images(translated_plan_logic)
    
    final_response = {
        "code": 200,
        "msg": "训练计划生成成功",
        "data": normalized_data
    }
    print(f"📤 接口返回数据: {json.dumps(final_response, ensure_ascii=False, indent=2)}")
    print(f"✅ 总处理耗时: {time.perf_counter() - start_total:.4f}s")
    return final_response


def recursive_normalize_images(data):
    """
    递归遍历字典/列表，将所有 'images' 字段中的 '/' 替换为 '_' 并去掉 '.jpg'
    """
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == "images" and isinstance(v, list):
                new_dict[k] = [
                    (img.replace("/", "_").replace(".jpg", "") if isinstance(img, str) else img)
                    for img in v
                ]
            else:
                new_dict[k] = recursive_normalize_images(v)
        return new_dict
    elif isinstance(data, list):
        return [recursive_normalize_images(i) for i in data]
    else:
        return data


def translate_chinese_keys_to_english(data):
    # 补充「说明」的映射：说明 → instructions
    key_mapping = {
        "训练分化": "training_split",
        "每日计划": "daily_plans",
        "训练日": "training_day",
        "动作列表": "exercise_list",
        "动作名称": "exercise_name",
        "组数": "sets",
        "次数": "reps",
        "顺序": "order",
        "器械": "equipment",
        "难度": "difficulty",
        "次要肌肉": "secondary_muscles",
        "动作类型": "exercise_type",
        "备注": "remark",
        "说明": "instructions",  # 新增：匹配返回结果里的「说明」
        "说明CN": "instructionsCN",
        "primaryMuscles": "primary_muscles", # 新增：转换主肌键名
        "id": "id"
    }
    
    # 以下递归逻辑不变
    if isinstance(data, dict):
        translated_dict = {}
        for k, v in data.items():
            new_key = key_mapping.get(k, k)
            translated_dict[new_key] = translate_chinese_keys_to_english(v)
        return translated_dict
    elif isinstance(data, list):
        translated_list = []
        for item in data:
            translated_list.append(translate_chinese_keys_to_english(item))
        return translated_list
    else:
        return data


# # 测试调用
# if __name__ == "__main__":
#     # 用户画像示例
#     user_profile = {
#         "水平": "新手",
#         "可用器械": ["哑铃", "徒手"],
#         "目标部位": ["胸肌", "背阔肌", "股四头肌"],
#         "伤病史": "",
#         "训练频率": "每周3天"
#     }
#     # 用户输入需求
#     user_input = "新手，每周练3天，家用哑铃，想练胸背腿，不要复杂动作"
    
#     # 生成计划
#     plan = generate_training_plan(user_input, user_profile)
#     print("智能生成的训练计划：")
#     print(json.dumps(plan, ensure_ascii=False, indent=2))

# 启动服务器（运行后接口可通过 http://localhost:8000 访问）
if __name__ == "__main__":
    import uvicorn
    # host=0.0.0.0 允许局域网访问（iOS 真机/模拟器能访问电脑的接口）
    uvicorn.run("fitness:app", host="0.0.0.0", port=8001, reload=False, proxy_headers=True, forwarded_allow_ips="*")