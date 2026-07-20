"""AI training plan generation."""
import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from fitness_project.config.settings import settings

logger = logging.getLogger(__name__)


class PlanGenerationError(RuntimeError):
    """Raised when the upstream LLM call fails or returns an unusable payload.

    The message carried here is safe to show to end users (e.g. iOS); the
    technical detail (HTTP status, response body, raw content, ...) is always
    logged separately via `logger` so it stays out of client-facing text.
    """


# TrainingScene.rawValue（iOS 端）→ 该场景下可用的 equipment 取值。
# None 表示不过滤（例如 gym，健身房器械齐全）。
_SCENE_EQUIPMENT_ALLOWLIST: Dict[str, set] = {
    "home": {"body only", "dumbbell", "bands", "kettlebells", "exercise ball",
              "medicine ball", "foam roll", None},
    "outdoor": {"body only", "bands", "medicine ball", None},
}


def _infer_scene(user_input: str) -> Optional[str]:
    """从 user_input（如 "novice，four，gym，无"）里识别训练场景。

    识别不到时返回 None，保持不过滤（回退为完整动作库），避免误裁剪。
    """
    if not user_input:
        return None
    tokens = {token.strip().lower() for token in re.split(r"[，,]", user_input)}
    for scene in _SCENE_EQUIPMENT_ALLOWLIST:
        if scene in tokens:
            return scene
    return None


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
def _load_exercises() -> list[Dict[str, Any]]:
    db_path = Path(settings.EXERCISE_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    if not db_path.exists():
        return []

    with db_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _load_exercise_map() -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for exercise in _load_exercises():
        name_cn = exercise.get("nameCN", "")
        name_en = exercise.get("name", "")
        if name_cn:
            mapping[name_cn.replace(" ", "")] = exercise
        if name_en:
            mapping[name_en.replace(" ", "").lower()] = exercise
    return mapping


@lru_cache(maxsize=4)
def _build_exercise_catalog_text(scene: Optional[str] = None) -> str:
    """按动作部位分组列出动作库中的英文动作名称，供 LLM 限定选取范围。

    `scene` 为 "home"/"outdoor" 时，会按 `_SCENE_EQUIPMENT_ALLOWLIST` 过滤掉
    该场景下不具备的器械动作，缩小目录以减少 prompt token 消耗；
    `scene` 为 None（含未识别到的场景，如 "gym"）时使用完整动作库。
    """
    allowed_equipment = _SCENE_EQUIPMENT_ALLOWLIST.get(scene)
    grouped: Dict[str, list[str]] = {}
    for exercise in _load_exercises():
        if allowed_equipment is not None and exercise.get("equipment") not in allowed_equipment:
            continue

        name_en = exercise.get("name") or exercise.get("nameCN")
        if not name_en:
            continue
        for muscle in exercise.get("primaryMuscles") or ["other"]:
            names = grouped.setdefault(muscle, [])
            if name_en not in names:
                names.append(name_en)

    return "\n".join(
        f"{body_part}: {', '.join(names)}" for body_part, names in grouped.items()
    )


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


def _coerce_str(value: Any, default: str = "") -> str:
    """Coerce arbitrary LLM output (including None/int/float) into a string.

    iOS decodes several exercise fields as non-optional String; a missing key
    or a JSON null would otherwise crash JSONDecoder on the client.
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value or default
    return str(value)


def normalize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI output so iOS models can decode it reliably.

    The iOS `APIExercise`/`DailyPlan` models declare several fields as
    non-optional (exercise_name, sets, reps, order, equipment, difficulty,
    training_day, exercise_list). If the LLM omits a key or returns null for
    one of them, `JSONDecoder` fails client-side with a generic "格式不对"
    error even though our server responded with HTTP 200. Every field below
    is therefore force-defaulted rather than left missing/null.
    """
    exercise_map = _load_exercise_map()
    daily_plans = plan.get("daily_plans") or plan.get("每日计划") or []
    plan["daily_plans"] = daily_plans

    for day_plan in daily_plans:
        if not isinstance(day_plan, dict):
            continue

        training_day = day_plan.get("training_day") or day_plan.get("训练日") or ""
        day_plan["training_day"] = _coerce_str(training_day)

        exercise_list = day_plan.get("exercise_list") or day_plan.get("动作列表") or []
        day_plan["exercise_list"] = exercise_list

        for action in exercise_list:
            if not isinstance(action, dict):
                continue

            exercise_name = action.get("exercise_name") or action.get("动作名称") or ""
            action_detail = _lookup_exercise(exercise_name, exercise_map)

            action["exercise_name"] = _coerce_str(exercise_name)
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
                # equipment/difficulty 由本地动作库权威回填，不再依赖 LLM 生成，
                # 避免其编造与库内数据不一致的取值，同时省掉这两个输出字段的 token。
                action["equipment"] = _coerce_str(action_detail.get("equipment"))
                action["difficulty"] = _coerce_str(action_detail.get("level"))
            elif "id" in action and action["id"] is not None:
                action["id"] = str(action["id"])
            else:
                action["id"] = ""

            action.setdefault("equipment", "")
            action.setdefault("difficulty", "")
            action["equipment"] = _coerce_str(action.get("equipment"))
            action["difficulty"] = _coerce_str(action.get("difficulty"))

            action["reps"] = _coerce_str(action.get("reps"), default="8-12")
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
            logger.error("QWEN_API_KEY 未配置，无法生成训练计划")
            raise PlanGenerationError("AI 服务未配置，请联系管理员")
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
        scene = _infer_scene(user_input)
        exercise_catalog = _build_exercise_catalog_text(scene)
        prompt = (
            "你是健身教练。请根据用户条件生成训练计划，只返回 JSON。"
            "JSON 必须包含 training_split 和 daily_plans；daily_plans 每项包含 "
            "training_day 和 exercise_list；动作只需包含 exercise_name、sets、"
            "reps、order 四个字段，不要输出 id、equipment、difficulty、images、"
            "primary_muscles，这些信息会由服务端根据动作名称自动补全。"
            "reps 必须是字符串，例如 \"8-12\"；sets 和 order 必须是整数。"
            "exercise_name 必须从下方动作库中选取已有的英文动作名称，禁止自行编造或翻译成中文；"
            "动作库按动作部位分组，格式为 \"body part: exercise1, exercise2, ...\"：\n"
            f"{exercise_catalog}\n"
            f"\n用户条件：{user_input}\n用户画像："
            f"{json.dumps(user_profile, ensure_ascii=False)}"
        )

        try:
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
        except requests.exceptions.RequestException as exc:
            response_body = getattr(exc.response, "text", "")
            logger.error(
                "调用千问接口失败: %s | response=%s", exc, response_body,
            )
            raise PlanGenerationError("AI 服务暂时不可用，请稍后重试") from exc

        try:
            payload = response.json()
            content = payload["output"]["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error(
                "千问接口返回结构异常: %s | raw=%s", exc, response.text,
            )
            raise PlanGenerationError("AI 服务返回异常，请稍后重试") from exc

        try:
            if isinstance(content, dict):
                plan = content
            else:
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
                plan = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("千问返回内容无法解析为 JSON: %s | content=%s", exc, content)
            raise PlanGenerationError("AI 返回内容解析失败，请稍后重试") from exc

        if not isinstance(plan.get("daily_plans"), list):
            logger.error("千问返回缺少 daily_plans 字段: %s", plan)
            raise PlanGenerationError("AI 生成的计划格式不完整，请稍后重试")

        plan.setdefault("training_split", "")
        return plan
