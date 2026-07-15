"""Training session validation, persistence, and daily aggregation."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from pydantic import BaseModel

from fitness_project.infrastructure.db.mysql import mysql_client


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return dict(value)


def save_training_record(user_id: int, record: BaseModel) -> Dict[str, Any]:
    data = _as_dict(record)
    started_at = data["date"]
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    if started_at.tzinfo is not None:
        started_at = started_at.astimezone(timezone.utc).replace(tzinfo=None)

    session = {
        **data,
        "started_at": started_at,
        "local_date": started_at.date(),
        "duration": max(0, int(round(data.get("duration") or 0))),
        "exercises": [],
    }
    for exercise_value in data["exercises"]:
        exercise = _as_dict(exercise_value)
        exercise["exercise_sets"] = [
            _as_dict(item) for item in (exercise.get("exercise_sets") or [])
        ]
        session["exercises"].append(exercise)

    version = mysql_client.save_training_session(user_id, session)
    return {
        "id": session["id"],
        "version": version,
        "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def get_training_summary(user_id: int, local_date: str) -> Dict[str, Any]:
    sessions = mysql_client.fetch_training_sessions_by_date(user_id, local_date)
    if not sessions:
        return {"code": 200, "msg": "ok", "data": []}

    total_duration = sum(int(item["duration_seconds"] or 0) for item in sessions)
    focus_areas: List[str] = []
    grouped: Dict[str, Dict[str, Any]] = {}
    total_volume = Decimal("0")

    for session in sessions:
        focus_area = session.get("focus_area")
        if focus_area and focus_area not in focus_areas:
            focus_areas.append(focus_area)

        for exercise in session["exercises"]:
            name = exercise["exercise_name"]
            result = grouped.setdefault(
                name,
                {
                    "exercise_name": name,
                    "max_weight": 0.0,
                    "sets": 0,
                    "detailed_sets": [],
                },
            )
            for item in exercise["exercise_sets"]:
                weight = Decimal(str(item["weight_kg"] or 0))
                reps = int(item["reps"] or 0)
                completed = bool(item["is_completed"])
                result["detailed_sets"].append(
                    {
                        "id": item["external_id"],
                        "weight": float(weight),
                        "reps": reps,
                        "is_completed": completed,
                    }
                )
                result["sets"] += 1
                result["max_weight"] = max(result["max_weight"], float(weight))
                if completed:
                    total_volume += weight * reps

    return {
        "code": 200,
        "msg": "ok",
        "data": [
            {
                "date": local_date,
                "summary": {
                    "total_volume": float(total_volume),
                    "total_duration": total_duration,
                    "focus_areas": focus_areas,
                },
                "exercises": list(grouped.values()),
            }
        ],
    }
