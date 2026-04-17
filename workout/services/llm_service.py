"""LLM服务 - 千问API封装"""
import json
import requests
from typing import Dict, Any
from core.config import settings
from core.constants import QWEN_API_URL, QWEN_MODEL
from core.exceptions import LLMError


class LLMService:
    """大模型服务"""
    
    def __init__(self):
        self.api_key = settings.QWEN_API_KEY
        self.api_url = QWEN_API_URL
        self.model = QWEN_MODEL
    
    def generate_plan(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
        exercise_meta: Dict[str, Any],
        injuries: list,
        avoid_keywords: list
    ) -> Dict[str, Any]:
        """调用千问生成训练计划"""
        prompt = self._build_prompt(
            user_input, user_profile, exercise_meta, injuries, avoid_keywords
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": prompt}]},
            "parameters": {"result_format": "json", "temperature": 0.3}
        }
        
        try:
            print(f"【千问API请求】headers={headers}, data={data}")
            response = requests.post(
                self.api_url, headers=headers, json=data, timeout=30
            )
            print(f"【千问API响应】status_code={response.status_code}, content={response.text}")
            response.raise_for_status()
            
            result = response.json()
            if "output" not in result or "choices" not in result["output"]:
                raise LLMError(f"千问返回格式异常: {result}")
            
            plan_json = result["output"]["choices"][0]["message"]["content"]
            return json.loads(plan_json)
            
        except json.JSONDecodeError as e:
            raise LLMError(f"千问返回内容不是合法JSON: {e}")
        except requests.exceptions.RequestException as e:
            raise LLMError(f"千问API请求失败: {e}")
    
    def _build_prompt(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
        exercise_meta: Dict[str, Any],
        injuries: list,
        avoid_keywords: list
    ) -> str:
        """构建提示词"""
        return f"""
    你是专业的健身教练，需要根据用户需求和ExerciseDB动作库，生成精准的训练计划编排逻辑。
    【用户画像】：{json.dumps(user_profile, ensure_ascii=False)}
    【ExerciseDB元数据】：{json.dumps(exercise_meta, ensure_ascii=False)}
    【用户需求】：{user_input}
    请严格按照以下规则生成编排逻辑：
    1. 动作必须从ExerciseDB中选择，优先选复合动作，避免孤立动作过多；
    2. 难度匹配用户水平（新手=Beginner，中级=Intermediate，高级=expert）；
    3. 仅选择用户可用器械的动作；
    4. 伤病史避坑（最高优先级）：
        - 用户受伤部位：{injuries}
        - 绝对禁止的动作关键词：{avoid_keywords}
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
    
    def fallback_plan(self) -> Dict[str, Any]:
        """离线降级方案"""
        return {
            "training_split": "离线~全身3天（A/B/A循环）",
            "daily_plans": [
                {
                    "training_day": "A",
                    "exercise_list": [
                        {
                            "exercise_name": "哑铃深蹲",
                            "sets": 3,
                            "reps": "12-15",
                            "order": 1,
                            "equipment": "哑铃",
                            "difficulty": "新手"
                        }
                    ]
                }
            ]
        }


# 全局LLM服务实例
llm_service = LLMService()
