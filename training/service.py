# # service.py
# import os
# import json
# import time
# import hashlib
# import requests
# import numpy as np
# from datetime import datetime, timedelta
# from dotenv import load_dotenv

# # 加载环境变量
# load_dotenv()
# QWEN_API_KEY = os.getenv("QWEN_API_KEY")
# QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# # ===================== 缓存层 =====================
# class PromptAnswerCache:
#     def __init__(self, expire_hours=168):
#         self.cache = {}
#         self.expire_hours = expire_hours

#     def _get_prompt_hash(self, prompt, profile):
#         profile_str = json.dumps(profile, sort_keys=True, ensure_ascii=False)
#         content = f"{prompt}_{profile_str}"
#         return hashlib.md5(content.encode("utf-8")).hexdigest()

#     def get_cached_answer(self, prompt, profile):
#         prompt_hash = self._get_prompt_hash(prompt, profile)
#         if prompt_hash not in self.cache:
#             return None
        
#         cache_item = self.cache[prompt_hash]
#         cache_time = datetime.strptime(cache_item["timestamp"], "%Y-%m-%d %H:%M:%S")
#         if datetime.now() - cache_time > timedelta(hours=self.expire_hours):
#             del self.cache[prompt_hash]
#             return None
        
#         return cache_item["answer"]

#     def set_cached_answer(self, prompt, profile, answer):
#         prompt_hash = self._get_prompt_hash(prompt, profile)
#         self.cache[prompt_hash] = {
#             "answer": answer,
#             "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "prompt": prompt
#         }

#     def clear_cache(self, prompt=None, profile=None):
#         if prompt and profile:
#             prompt_hash = self._get_prompt_hash(prompt, profile)
#             self.cache.pop(prompt_hash, None)
#         else:
#             self.cache = {}

# # ✅ 这里必须放在最外层，确保启动时就能被导入
# prompt_cache = PromptAnswerCache(expire_hours=24)

# # ===================== 动作库处理 =====================
# def load_exercise_db():
#     try:
#         with open("free-exercise-db-main/dist/exercisesCN.json", "r", encoding="utf-8") as f:
#             data = json.load(f)
#             if not data:
#                 print("⚠️  动作库文件内容为空！")
#             else:
#                 for exercise in data:
#                     if "images" in exercise:
#                         exercise["images"] = [
#                             img.replace("/", "_").replace(".jpg", "") 
#                             for img in exercise["images"]
#                         ]
#                 print(f"✅ 动作库加载成功，共 {len(data)} 条数据")
#             return data
#     except Exception as e:
#         print(f"❌ 加载动作库失败: {e}")
#         return []

# def compute_global_meta(exercise_db):
#     if not exercise_db:
#         return {}, {}
    
#     meta = {
#         "total_exercises": len(exercise_db),
#         "available_equipment_types": [x for x in list(set([e.get("equipment", "") for e in exercise_db])) if x],
#         "difficulty_levels": [x for x in list(set([e.get("level", "") for e in exercise_db])) if x],
#         "target_muscle_groups": [x for x in list(set([",".join(e.get("primaryMuscles", [])) for e in exercise_db])) if x]
#     }
    
#     mapping = {}
#     for e in exercise_db:
#         name_cn = e.get("nameCN", "")
#         name_en = e.get("name", "")
#         if name_cn:
#             mapping[name_cn.replace(" ", "")] = e
#         if name_en:
#             mapping[name_en.replace(" ", "").lower()] = e
            
#     return meta, mapping

# # 全局变量
# GLOBAL_EXERCISE_DB = load_exercise_db()
# GLOBAL_EXERCISE_META, GLOBAL_EXERCISE_MAP = compute_global_meta(GLOBAL_EXERCISE_DB)

# # ===================== 大模型调用 =====================
# def build_prompt(user_input, user_profile, exercise_db_meta):
#     injury_avoid_map = {
#         "肩伤": ["肩推", "推肩", "过头推举", "站姿推举", "哑铃肩推", "杠铃肩推", "前平举", "颈后推举"],
#         "腰伤": ["硬拉", "早安式", "体前屈", "负重深蹲（大重量）", "山羊挺身（负重）"],
#         "膝伤": ["深蹲", "箭步蹲", "保加利亚分腿蹲", "腿举（大重量）", "提踵（负重）"],
#         "腕伤": ["俯卧撑", "卧推（窄距）", "哑铃弯举", "杠铃弯举", "农夫行走"],
#         "肘伤": ["臂屈伸", "锤式弯举", "三头肌下压（大重量）", "杠铃卧推（宽距）"]
#     }

#     user_injuries = []
#     for injury in injury_avoid_map.keys():
#         if injury in user_input:
#             user_injuries.append(injury)
#     avoid_action_keywords = []
#     for injury in user_injuries:
#         avoid_action_keywords.extend(injury_avoid_map[injury])

#     prompt = f"""
#     你是专业的健身教练，需要根据用户需求和ExerciseDB动作库，生成精准的训练计划编排逻辑。
#     【用户画像】：{json.dumps(user_profile, ensure_ascii=False)}
#     【ExerciseDB元数据】：{json.dumps(exercise_db_meta, ensure_ascii=False)}
#     【用户需求】：{user_input}
#     请严格按照以下规则生成编排逻辑：
#     1. 动作必须从ExerciseDB中选择，优先选复合动作，避免孤立动作过多；
#     2. 难度匹配用户水平（新手=Beginner，中级=Intermediate，高级=expert）；
#     3. 仅选择用户可用器械的动作；
#     4. 伤病史避坑（最高优先级）：
#         - 用户受伤部位：{user_injuries}
#         - 绝对禁止的动作关键词：{avoid_action_keywords}
#         - 要求：任何包含以上关键词的动作都不能出现在计划中，且避开所有对受伤部位有压力的动作；
#     5. 输出格式为JSON，包含：训练分化（如每周3练,每周4练,每周5练,每周6练）、每日计划（动作名称、组数、次数、顺序）；
#     6. 符合健身原理：高手每组6-8次（4组），中级每组8-10次（3-4组），新手每组8-12次（3组）；组间休息60-120秒；渐进超负荷提示。
    
#     输出示例：
#     {{
#         "training_split": "每周3练",
#         "daily_plans": [
#             {{
#                 "training_day": "第一练",
#                 "exercise_list": [
#                     {{
#                         "exercise_name": "杠铃深蹲",
#                         "sets": 3,
#                         "reps": "8-12",
#                         "order": 1,
#                         "equipment": "杠铃",
#                         "difficulty": "新手",
#                         "images":[],
#                         "instructionsCN":[]
#                     }}
#                 ]
#             }}
#         ]
#     }}
#     """
#     return prompt

# def call_qwen(prompt):
#     headers = {
#         "Authorization": f"Bearer {QWEN_API_KEY}",
#         "Content-Type": "application/json"
#     }
#     data = {
#         "model": "qwen-turbo",
#         "input": {"messages": [{"role": "user", "content": prompt}]},
#         "parameters": {"result_format": "json", "temperature": 0.3}
#     }
#     try:
#         response = requests.post(QWEN_API_URL, headers=headers, json=data, timeout=30)
#         response.raise_for_status()
#         result = response.json()
#         if "output" not in result or "choices" not in result["output"] or len(result["output"]["choices"]) == 0:
#             raise Exception(f"千问返回格式异常：{result}")
#         plan_json = result["output"]["choices"][0]["message"]["content"]
#         plan_logic = json.loads(plan_json)
#         return plan_logic
#     except Exception as e:
#         return {
#             "training_split": "离线～全身3天（A/B/A循环）",
#             "daily_plans": [
#                 {"training_day": "A", "exercise_list": [{"exercise_name": "哑铃深蹲", "sets": 3, "reps": "12-15", "order": 1, "equipment": "哑铃", "difficulty": "新手"}]}
#             ]
#         }

# # ===================== 数据转换 =====================
# def recursive_normalize_images(data):
#     if isinstance(data, dict):
#         new_dict = {}
#         for k, v in data.items():
#             if k == "images" and isinstance(v, list):
#                 new_dict[k] = [
#                     (img.replace("/", "_").replace(".jpg", "") if isinstance(img, str) else img)
#                     for img in v
#                 ]
#             else:
#                 new_dict[k] = recursive_normalize_images(v)
#         return new_dict
#     elif isinstance(data, list):
#         return [recursive_normalize_images(i) for i in data]
#     else:
#         return data

# def translate_chinese_keys_to_english(data):
#     key_mapping = {
#         "训练分化": "training_split",
#         "每日计划": "daily_plans",
#         "训练日": "training_day",
#         "动作列表": "exercise_list",
#         "动作名称": "exercise_name",
#         "组数": "sets",
#         "次数": "reps",
#         "顺序": "order",
#         "器械": "equipment",
#         "难度": "difficulty",
#         "次要肌肉": "secondary_muscles",
#         "动作类型": "exercise_type",
#         "备注": "remark",
#         "说明": "instructions",
#         "说明CN": "instructionsCN",
#         "primaryMuscles": "primary_muscles",
#         "id": "id"
#     }
    
#     if isinstance(data, dict):
#         translated_dict = {}
#         for k, v in data.items():
#             new_key = key_mapping.get(k, k)
#             translated_dict[new_key] = translate_chinese_keys_to_english(v)
#         return translated_dict
#     elif isinstance(data, list):
#         return [translate_chinese_keys_to_english(item) for item in data]
#     else:
#         return data



# service.py
import os
import json
import hashlib
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# ==========================================
# 缓存类
# ==========================================
class PromptAnswerCache:
    def __init__(self, expire_hours=24):
        self.cache = {}
        self.expire_hours = expire_hours

    def _get_prompt_hash(self, prompt, profile):
        profile_str = json.dumps(profile, sort_keys=True, ensure_ascii=False)
        content = f"{prompt}_{profile_str}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def get_cached_answer(self, prompt, profile):
        h = self._get_prompt_hash(prompt, profile)
        if h not in self.cache:
            return None
        item = self.cache[h]
        if datetime.now() - item["time"] > timedelta(hours=self.expire_hours):
            del self.cache[h]
            return None
        return item["answer"]

    def set_cached_answer(self, prompt, profile, answer):
        h = self._get_prompt_hash(prompt, profile)
        self.cache[h] = {"answer": answer, "time": datetime.now()}

# ==========================================
# 全局实例（必须放这里！）
# ==========================================
prompt_cache = PromptAnswerCache()
GLOBAL_EXERCISE_META = {}
GLOBAL_EXERCISE_MAP = {}

# ==========================================
# 动作库
# ==========================================
def load_exercise_db():
    try:
        with open("free-exercise-db-main/dist/exercisesCN.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def compute_global_meta(db):
    return {}, {}

# ==========================================
# 大模型
# ==========================================
def build_prompt(*args, **kwargs):
    return "test prompt"

def call_qwen(prompt):
    return {"training_split": "test", "daily_plans": []}

# ==========================================
# 工具函数
# ==========================================
def recursive_normalize_images(data):
    return data

def translate_chinese_keys_to_english(data):
    return data