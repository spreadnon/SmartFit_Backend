import os
import json
from http import client
import requests
from fastapi import FastAPI, HTTPException, Request
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

# 加载环境变量（千问API Key）
load_dotenv()  # 加载.env文件
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# 初始化 FastAPI 应用
app = FastAPI()

# 连接本地 Redis（默认无密码）
r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True  # 自动把 bytes 转成字符串
)

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
    with open("free-exercise-db-main/dist/exercisesCN.json", "r", encoding="utf-8") as f:
        # return json.load(f)
        data = json.load(f)
        # # 验证读取成功的核心代码
        # print("✅ 文件读取成功！")
        # print(f"数据类型：{type(data)}")  # 应该是 list/dict（JSON 文件的顶层结构）
        # print(f"数据条数：{len(data)}")   # 如果是列表，显示元素个数；字典则显示键的数量
        # print(f"第一条数据示例：{data[0] if isinstance(data, list) else list(data.values())[0]}")  # 打印第一条数据（按需）
        if not data:
            print("⚠️  文件读取成功，但内容为空！")
        else:
            print("✅ 文件读取成功且包含数据！")
        return data


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

# 定义训练计划生成接口（POST 请求）
@app.post("/generate-plan")
@limiter.limit("100/minute")  # 单IP每分钟最多100次请求
# @limiter.global_limit("100/minute") #全局限流每分钟最多100次请求
# 核心逻辑：生成智能训练计划
async def generate_plan(request: Request):
    # 1. 读取并解析请求体
    try:
        request_body = await request.json()  # 异步读取 JSON 请求体
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败：{str(e)}")
    
    # 2. 提取参数（兼容缺失的情况）
    user_input = request_body.get("user_input", "")
    user_profile = request_body.get("user_profile", {})

    # 校验必要参数
    if not user_input : #or not user_profile
        raise HTTPException(status_code=400, detail="user_input 和 user_profile 不能为空")

    # 2.5 统一缓存查找（内存 + Redis）
    cache_id = prompt_cache._get_prompt_hash(user_input, user_profile)
    redis_key = f"plan_cache:{cache_id}"
    
    # ✅ 新增：先查数据库，如果已存在则直接返回（避免重复生成）
    db_result = get_from_mysql(user_input)
    if db_result:
        print(f"📌 命中 MySQL 缓存")
        # 同步向内存和 Redis 写入（如果需要，这里只写内存加速下次查找）
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
        # 2. 调用另一个文件，保存到数据库
        save_to_mysql(data)


        return {
            "code": 200,
            "msg": "命中缓存，训练计划生成成功",
            "data": cached_answer
        }
    
    # 其次检查 Redis 缓存
    try:
        redis_val = r.get(redis_key)
        if redis_val:
            print(f"📌 命中 Redis 缓存")
            cached_answer = json.loads(redis_val)
            # 同步回内存缓存
            prompt_cache.set_cached_answer(user_input, user_profile, cached_answer)
            
            # ✅ 新增：Redis 命中也保存到数据库
            data = [
                {"search_str": user_input, "search_respond": cached_answer}
            ]
            save_to_mysql(data)

            return {
                "code": 200,
                "msg": "命中缓存，训练计划生成成功",
                "data": cached_answer
            }
    except Exception as e:
        print(f"⚠️ Redis 读取失败: {e}")

    # 3. 加载ExerciseDB数据，提取元数据（供大模型参考）
    try:
        exercise_db = load_exercise_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载动作库失败：{str(e)}")
    
    # ✅ 核心修复：替换为 JSON 真实的英文键名 + 增加容错处理
    exercise_db_meta = {
        #动作总数
        "total_exercises": len(exercise_db),
        # 器械类型 → equipment，用 get 容错，过滤空值
        "available_equipment_types": [x for x in list(set([e.get("equipment", "") for e in exercise_db])) if x],
        # 难度等级 → level，用 get 容错，过滤空值
        "difficulty_levels": [x for x in list(set([e.get("level", "") for e in exercise_db])) if x],
        # 目标肌肉 → primaryMuscles（数组），拼接成字符串后去重
        "target_muscle_groups": [x for x in list(set([",".join(e.get("primaryMuscles", [])) for e in exercise_db])) if x],
        "exercises_images": [x for x in list(set([",".join(e.get("images", [])) for e in exercise_db])) if x],
        
    }
    
    # 4. 构建提示词
    try:
        prompt = build_prompt(user_input, user_profile, exercise_db_meta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建提示词失败：{str(e)}")
    
    # 5. 调用千问大模型获取编排逻辑
    try:
        plan_logic = call_qwen(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用大模型失败：{str(e)}")
    
    # 6. 结合ExerciseDB补充动作详情（如次要肌肉、动作类型）
    # ✅ 修复：构建动作映射时用 nameCN（中文名称）匹配，补充真实字段
    exercise_map = {e.get("nameCN", ""): e for e in exercise_db}
    try:
        for day_plan in plan_logic.get("每日计划", []):# 每日计划 → daily_plans
            for action in day_plan.get("动作列表", []): # 动作列表 → exercise_list
                action_name = action.get("动作名称", "") #动作名称 → exercise_name
                action_detail = exercise_map.get(action_name)
                if action_detail:
                    # 次要肌肉 → secondaryMuscles，动作类型 → category
                    action["次要肌肉"] = action_detail.get("secondaryMuscles", [])# 次要肌肉 → secondary_muscles
                    action["动作类型"] = action_detail.get("category", "")# 动作类型 → exercise_type
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"补充动作详情失败：{str(e)}")
    
     # ✅ 关键步骤：调用转换函数，将所有中文 key 转为英文（必须执行！）
    translated_plan_logic = translate_chinese_keys_to_english(plan_logic)
    
    # 7. 写入缓存（内存 + Redis）
    prompt_cache.set_cached_answer(user_input, user_profile, translated_plan_logic)
    try:
        r.set(redis_key, json.dumps(translated_plan_logic, ensure_ascii=False), ex=60*60*24*7)
        print(f"📌 非缓存命中，生成答案并写入内存和 Redis 缓存")
        
        # ✅ 新增：新生成的计划也保存到数据库
        data = [
            {"search_str": user_input, "search_respond": translated_plan_logic}
        ]
        save_to_mysql(data)
    except Exception as e:
        print(f"⚠️ Redis 或 MySQL 写入失败: {e}")

    # 7. 返回标准化结果
    return {
        "code": 200,
        "msg": "训练计划生成成功",
        "data": translated_plan_logic
    }


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
        "说明CN": "instructionsCN"
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