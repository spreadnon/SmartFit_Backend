"""训练日志业务服务"""
from typing import List, Optional, Union
from pydantic import BaseModel

from infrastructure.db.mysql import mysql_client


def _extract_weight_from_sets(training_dict: dict) -> Optional[float]:
    """从 exercise_sets 中提取第一个有效重量（当顶层 weight 为 0 或空时）"""
    weight = training_dict.get("weight")
    extra_data = training_dict.get("exercise_sets")
    if (weight is None or float(weight) == 0) and isinstance(extra_data, list):
        for s in extra_data:
            s_weight = s.get("weight") if isinstance(s, dict) else getattr(s, "weight", None)
            if s_weight is not None:
                try:
                    s_weight = float(s_weight)
                except (TypeError, ValueError):
                    continue
                if s_weight > 0:
                    return s_weight
    return weight


def _normalize_training_dict(
    item: Union[dict, BaseModel],
    record_focus_area: Optional[str],
    record_duration: Optional[float],
) -> dict:
    """将 Pydantic 模型或字典统一转换为可写入 DB 的字典"""
    training_dict = item.model_dump() if isinstance(item, BaseModel) else dict(item)

    if not training_dict.get("focus_area"):
        training_dict["focus_area"] = record_focus_area

    if not training_dict.get("duration") or training_dict.get("duration") == 0:
        training_dict["duration"] = record_duration or 0

    training_dict["weight"] = _extract_weight_from_sets(training_dict)

    if any(training_dict.get(k) is None for k in ("exercise_name", "sets", "reps")):
        raise ValueError("训练记录必须包含 exercise_name、sets 和 reps")

    return training_dict


def save_training_data(
    user_id: int,
    items: List[Union[BaseModel, dict]],
    record_focus_area: Optional[str] = None,
    record_duration: Optional[float] = 0,
) -> int:
    """
    批量保存训练记录，返回成功保存的条数。
    每条记录使用 UPSERT 逻辑（先按 external_id，再按当天同名动作）。
    """
    success_count = 0
    for item in items:
        training_dict = _normalize_training_dict(item, record_focus_area, record_duration)
        if mysql_client.save_training_record(user_id, training_dict):
            success_count += 1
    return success_count


def get_training_summary(user_id: int, date: str) -> dict:
    """查询指定日期的训练汇总，返回统一响应格式"""
    raw_results = mysql_client.fetch_training_records_by_date(user_id, date)

    summary = {"total_volume": 0.0, "total_duration": 0, "focus_areas": set()}
    formatted_exercises = []

    for row in raw_results:
        exercise_name  = row["exercise_name"]
        sets_count     = row["sets"]
        weight_summary = float(row["weight"]) if row["weight"] else 0.0
        duration       = row["duration"] or 0
        focus_area     = row["focus_area"]
        extra_data     = row["extra_data"]

        exercise_volume = 0.0
        max_weight = 0.0
        if isinstance(extra_data, list):
            for s in extra_data:
                s_weight = float(s.get("weight") or 0)
                s_reps   = int(s.get("reps") or 0)
                is_comp  = s.get("is_completed") if s.get("is_completed") is not None else s.get("isCompleted", True)
                if is_comp:
                    exercise_volume += s_weight * s_reps
                    max_weight = max(max_weight, s_weight)
        else:
            exercise_volume = weight_summary * sets_count * 10
            max_weight = weight_summary

        summary["total_volume"]   += exercise_volume
        summary["total_duration"] += duration
        if focus_area:
            summary["focus_areas"].add(focus_area)

        formatted_exercises.append({
            "id":            row["external_id"],
            "backend_id":    row["id"],
            "exercise_name": exercise_name,
            "exerciseName":  exercise_name,
            "focus_area":    focus_area,
            "focusArea":     focus_area,
            "sets":          sets_count,
            "reps":          row["reps"],
            "weight":        weight_summary,
            "max_weight":    max_weight,
            "volume":        exercise_volume,
            "duration":      duration,
            "detailed_sets": extra_data,
            "exercise_sets": extra_data,
            "log_date":      row["log_date"],
            "log_time":      row["log_date"],
        })

    summary["focus_areas"] = list(summary["focus_areas"])
    return {
        "code": 200,
        "msg":  "success",
        "data": [{"date": date, "summary": summary, "exercises": formatted_exercises}],
    }
