from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from jwt_util import parse_token
from db_save_training import save_training_data_to_db, get_training_data_from_db
from datetime import date as date_type

router = APIRouter(prefix="/api/training", tags=["Training Log"])

class ExerciseSet(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[str] = None  # iOS 端的 Set ID
    weight: float
    reps: int
    is_completed: bool = Field(False, alias="isCompleted")

class TrainingData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    external_id: Optional[str] = Field(None, alias="id")  # 映射 iOS 的 id
    exercise_name: str = Field(..., alias="exerciseName")
    sets: int
    reps: Union[str, int]
    weight: Optional[float] = 0.0
    exercise_sets: Optional[List[ExerciseSet]] = Field(None, alias="exerciseSets")
    
    # 额外元数据
    order: Optional[int] = None
    equipment: Optional[str] = None
    difficulty: Optional[str] = None
    instructions: Optional[str] = None
    focus_area: Optional[str] = Field(None, alias="focusArea")
    primary_muscles: Optional[List[str]] = Field(None, alias="primaryMuscles")
    rest_time: Optional[int] = Field(None, alias="restTime")
    backend_id: Optional[int] = Field(None, alias="backendId")

class TrainingRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(..., alias="id")
    exercises: List[TrainingData]
    date: Optional[str] = None
    focus_area: Optional[str] = Field(None, alias="focusArea")
    duration: Optional[float] = 0.0
    is_completed: bool = Field(False, alias="isCompleted")


@router.post("/savetraining")
async def save_training_data_endpoint(
    data: Union[TrainingRecord, TrainingData, List[TrainingData]],
    user_id: int = Depends(parse_token)
):
    """
    保存用户的训练数据。支持单个对象、对象列表或包含 exercises 列表的 TrainingRecord。
    具有智能 UPSERT 逻辑。
    """
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")

    # 统一转换为列表处理
    items = []
    record_focus_area = None
    record_duration = 0

    if isinstance(data, TrainingRecord):
        items = data.exercises
        record_focus_area = data.focus_area
        record_duration = data.duration
    elif isinstance(data, TrainingData):
        items = [data]
    else:
        items = data

    success_count = 0
    for item in items:
        # 转换为字典格式
        training_dict = item.model_dump()
        
        # 补充字段：如果 exercise 自身没填，则取 record 的
        if not training_dict.get("focus_area"):
            training_dict["focus_area"] = record_focus_area
        if not training_dict.get("duration") or training_dict.get("duration") == 0:
            # 这里简单均摊或者只给第一个（或者数据库存总时长）
            # 当前逻辑：将 record duration 尝试赋给 exercises
            training_dict["duration"] = record_duration
        
        # 权重提取逻辑：如果 top-level weight 为 0 或 None，尝试从 exercise_sets 中提取
        if (not training_dict.get("weight") or training_dict.get("weight") == 0) and item.exercise_sets:
            for s in item.exercise_sets:
                if s.weight and s.weight > 0:
                    training_dict["weight"] = s.weight
                    break
        
        if save_training_data_to_db(user_id, training_dict):
            success_count += 1
    
    if success_count > 0:
        print(f"🚀 [API] 用户 {user_id} 成功保存了 {success_count} 条训练日志")
        return {
            "code": status.HTTP_200_OK,
            "msg": f"训练数据保存成功 (共 {success_count} 条)",
            "data": None
        }
    else:
        print(f"⚠️ [API] 用户 {user_id} 尝试保存训练日志，但全部失败")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="训练数据保存失败")





@router.get("/gettraining")
async def get_training_data_endpoint(
    date: str = Query(None, description="查询日期 (格式: YYYY-MM-DD), 默认为今天"),
    user_id: int = Depends(parse_token)
):
    """
    根据日期查询用户的训练数据，并返回聚合后的每日概览。
    """
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    if not date:
        from datetime import date as dt_date
        date = dt_date.today().strftime("%Y-%m-%d")
        
    raw_results = get_training_data_from_db(user_id, date)
    
    # 1. 汇总逻辑
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
        extra_data = row["extra_data"] # 数据库层已解析为 list/dict
        
        # 计算单项动作指标
        exercise_volume = 0.0
        max_weight = 0.0
        
        if isinstance(extra_data, list):
            for s in extra_data:
                # 兼容不同来源的 key 名
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
            # 兜底逻辑
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

