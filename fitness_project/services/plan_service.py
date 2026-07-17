"""AI training plan generation."""
import asyncio
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from fitness_project.config.settings import settings


def _normalize_image_paths(images: Any) -> list[str]:
    if not isinstance(images, list):
        return []
    normalized: list[str] = []
    for image in images:
        if not isinstance(image, str):
            continue
        normalized.append(image.replace("/", "_").replace(".jpg", ""))
    return normalized


@lru_cache(maxsize=1)
def _load_exercise_map() -> Dict[str, Dict[str, Any]]:
    db_path = Path(settings.EXERCISE_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    if not db_path.exists():
        return {}

    with db_path.open("r", encoding="utf-8") as handle:
        exercises = json.load(handle)

    mapping: Dict[str, Dict[str, Any]] = {}
    for exercise in exercises:
        name_cn = exercise.get("nameCN", "")
        name_en = exercise.get("name", "")
        if name_cn:
            mapping[name_cn.replace(" ", "")] = exercise
        if name_en:
            mapping[name_en.replace(" ", "").lower()] = exercise
    return mapping


def _lookup_exercise(exercise_name: str, exercise_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized_name = exercise_name.replace(" ", "").lower()
    if not normalized_name:
        return None

    direct = exercise_map.get(exercise_name.replace(" ", "")) or exercise_map.get(normalized_name)
    if direct:
        return direct

    for key, value in exercise_map.items():
        if normalized_name in key or key in normalized_name:
            return value
    return None


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        match = re.search(r"\d+", stripped)
        if match:
            return int(match.group())
        return default
    return default


def normalize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI output so iOS models can decode it reliably."""
    exercise_map = _load_exercise_map()
    daily_plans = plan.get("daily_plans") or []

    for day_plan in daily_plans:
        exercise_list = day_plan.get("exercise_list") or []
        for action in exercise_list:
            if not isinstance(action, dict):
                continue

            exercise_name = action.get("exercise_name") or action.get("动作名称") or ""
            action_detail = _lookup_exercise(exercise_name, exercise_map)

            action.setdefault("images", [])
            action.setdefault("primary_muscles", [])
            action.setdefault("instructionsCN", [])
            action.setdefault("secondary_muscles", [])
            action.setdefault("exercise_type", "")

            if action_detail:
                action["id"] = str(action_detail.get("id", ""))
                action["images"] = _normalize_image_paths(action_detail.get("images", []))
                action["instructionsCN"] = action_detail.get("instructionsCN", [])
                action["secondary_muscles"] = action_detail.get("secondaryMuscles", [])
                action["exercise_type"] = action_detail.get("category", "")
                action["primary_muscles"] = action_detail.get("primaryMuscles", [])
            elif "id" in action and action["id"] is not None:
                action["id"] = str(action["id"])
            else:
                action["id"] = ""

            if "reps" in action and action["reps"] is not None:
                action["reps"] = str(action["reps"])

            action["sets"] = _coerce_int(action.get("sets"), default=3)
            action["order"] = _coerce_int(action.get("order"), default=1)

            action["images"] = _normalize_image_paths(action.get("images", []))

    return plan


class PlanGenerationService:
    async def generate_plan(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not settings.QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY 未配置")
        plan = await asyncio.to_thread(
            self._request_plan,
            user_input,
            user_profile,
        )
        return normalize_plan(plan)

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
            "id 必须是字符串；reps 必须是字符串，例如 \"8-12\"；"
            "sets 和 order 必须是整数。"
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
