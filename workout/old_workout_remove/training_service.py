from typing import List, Union, Optional
from pydantic import BaseModel
from training_dao import save_training_record, fetch_training_records_by_date


def _extract_weight_from_sets(training_data: dict):
    weight = training_data.get("weight")
    extra_data = training_data.get("exercise_sets")
    if (weight is None or float(weight) == 0) and isinstance(extra_data, list):
        for s in extra_data:
            if isinstance(s, dict):
                s_weight = s.get("weight")
            else:
                s_weight = getattr(s, "weight", None)
            if s_weight is not None:
                try:
                    s_weight = float(s_weight)
                except (TypeError, ValueError):
                    continue
                if s_weight > 0:
                    return s_weight
    return weight


def _normalize_training_dict(item: Union[dict, BaseModel], record_focus_area: Optional[str], record_duration: Optional[float]):
    if isinstance(item, BaseModel):
        training_dict = item.model_dump()
    else:
        training_dict = dict(item)

    if not training_dict.get("focus_area"):
        training_dict["focus_area"] = record_focus_area

    if not training_dict.get("duration") or training_dict.get("duration") == 0:
        training_dict["duration"] = record_duration or 0

    weight = _extract_weight_from_sets(training_dict)
    training_dict["weight"] = weight if weight is not None else training_dict.get("weight")

    if training_dict.get("sets") is None or training_dict.get("exercise_name") is None or training_dict.get("reps") is None:
        raise ValueError("训练记录必须包含 exercise_name、sets 和 reps")

    return training_dict


def _normalize_input_payload(data: Union[BaseModel, List[BaseModel]]):
    if isinstance(data, list):
        return data
    return [data]


def save_training_data(user_id: int, data: Union[BaseModel, List[BaseModel]], record_focus_area: Optional[str] = None, record_duration: Optional[float] = 0):
    items = _normalize_input_payload(data)
    success_count = 0
    for item in items:
        training_dict = _normalize_training_dict(item, record_focus_area, record_duration)
        if save_training_record(user_id, training_dict):
            success_count += 1
    return success_count


def get_training_summary(user_id: int, date: str):
    raw_results = fetch_training_records_by_date(user_id, date)
    summary = {
        "total_volume": 0.0,
        "total_duration": 0,
        "focus_areas": set()
    }
    formatted_exercises = []

    for row in raw_results:
        exercise_name = row["exercise_name"]
        sets_count = row["sets"]
        weight_summary = float(row["weight"]) if row["weight"] else 0.0
        duration = row["duration"] or 0
        focus_area = row["focus_area"]
        extra_data = row["extra_data"]

        exercise_volume = 0.0
        max_weight = 0.0
        if isinstance(extra_data, list):
            for s in extra_data:
                s_weight = float(s.get("weight") or 0)
                s_reps = int(s.get("reps") or 0)
                is_comp = s.get("is_completed")
                if is_comp is None:
                    is_comp = s.get("isCompleted", True)
                if is_comp:
                    exercise_volume += s_weight * s_reps
                    if s_weight > max_weight:
                        max_weight = s_weight
        else:
            exercise_volume = weight_summary * sets_count * 10
            max_weight = weight_summary

        summary["total_volume"] += exercise_volume
        summary["total_duration"] += duration
        if focus_area:
            summary["focus_areas"].add(focus_area)

        formatted_exercises.append({
            "id": row["external_id"],
            "backend_id": row["id"],
            "exercise_name": exercise_name,
            "exerciseName": exercise_name,
            "focus_area": focus_area,
            "focusArea": focus_area,
            "sets": sets_count,
            "reps": row["reps"],
            "weight": weight_summary,
            "max_weight": max_weight,
            "volume": exercise_volume,
            "duration": duration,
            "detailed_sets": extra_data,
            "exercise_sets": extra_data,
            "log_date": row["log_date"],
            "log_time": row["log_date"]
        })

    summary["focus_areas"] = list(summary["focus_areas"])
    return {
        "code": 200,
        "msg": "success",
        "data": [
            {
                "date": date,
                "summary": summary,
                "exercises": formatted_exercises
            }
        ]
    }
