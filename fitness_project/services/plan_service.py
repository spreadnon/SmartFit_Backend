"""AI training plan generation."""
import asyncio
import json
import re
from typing import Any, Dict

import requests

from fitness_project.config.settings import settings


class PlanGenerationService:
    async def generate_plan(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not settings.QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY 未配置")
        return await asyncio.to_thread(
            self._request_plan,
            user_input,
            user_profile,
        )

    def _request_plan(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = (
            "你是健身教练。请根据用户条件生成训练计划，只返回 JSON。"
            "JSON 必须包含 training_split 和 daily_plans；daily_plans 每项包含 "
            "training_day 和 exercise_list；动作包含 id、exercise_name、sets、"
            "reps、order、equipment、difficulty、images、primary_muscles。"
            f"\n用户条件：{user_input}\n用户画像："
            f"{json.dumps(user_profile, ensure_ascii=False)}"
        )
        response = requests.post(
            settings.QWEN_API_URL,
            headers={
                "Authorization": f"Bearer {settings.QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.QWEN_MODEL,
                "input": {"messages": [{"role": "user", "content": prompt}]},
                "parameters": {
                    "result_format": "message",
                    "temperature": settings.QWEN_TEMPERATURE,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["output"]["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            plan = content
        else:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            plan = json.loads(cleaned)
        if not isinstance(plan.get("daily_plans"), list):
            raise ValueError("AI 返回缺少 daily_plans")
        plan.setdefault("training_split", "")
        return plan
