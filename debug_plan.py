import json
import os
import hashlib
from datetime import datetime, timedelta
from pydantic import BaseModel
import redis
from fitness import PromptAnswerCache, build_prompt, load_exercise_db, translate_chinese_keys_to_english, call_qwen

# Mocking Request for testing
class MockRequest:
    async def json(self):
        return {
            "user_input": "测试：新手，每周3天",
            "user_profile": {"水平": "初级"}
        }

async def debug_generate():
    try:
        # 模拟上下文
        prompt_cache = PromptAnswerCache(expire_hours=24)
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        
        user_input = "测试：新手，每周3天"
        user_profile = {"水平": "初级"}
        
        print("1. 测试哈希及 Redis Key...")
        cache_id = prompt_cache._get_prompt_hash(user_input, user_profile)
        redis_key = f"plan_cache:{cache_id}"
        print(f"Key: {redis_key}")

        print("2. 加载 ExerciseDB...")
        exercise_db = load_exercise_db()
        print(f"数据量: {len(exercise_db)}")

        print("3. 构建元数据...")
        exercise_db_meta = {
            "total_exercises": len(exercise_db),
            "available_equipment_types": [x for x in list(set([e.get("equipment", "") for e in exercise_db])) if x],
            "difficulty_levels": [x for x in list(set([e.get("level", "") for e in exercise_db])) if x],
            "target_muscle_groups": [x for x in list(set([",".join(e.get("primaryMuscles", [])) for e in exercise_db])) if x],
            "exercises_images": [x for x in list(set([",".join(e.get("images", [])) for e in exercise_db])) if x][:10], # 限制长度防止 payload 过大
        }
        print("元数据构建成功")

        print("4. 构建 Prompt...")
        prompt = build_prompt(user_input, user_profile, exercise_db_meta)
        print("Prompt 构建成功")

        # 接下来调 API 可能会慢或报错，这里捕获异常
        # print("5. 调用千问...")
        # plan_logic = call_qwen(prompt)
        # print("API 返回成功")

    except Exception as e:
        print(f"❌ 捕获到异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_generate())
