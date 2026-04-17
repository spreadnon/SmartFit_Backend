"""训练日志路由"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from datetime import date as dt_date
from workout.core.security import get_current_user

router = APIRouter(prefix="/training", tags=["训练日志"])

# TODO: 需要实现 training_service
# from services.training_service import save_training_data, get_training_summary


class ExerciseSet(BaseModel):
    """训练组数据"""
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[str] = None
    weight: float
    reps: int
    is_completed: bool = Field(False, alias="isCompleted")


class TrainingData(BaseModel):
    """单次训练数据"""
    model_config = ConfigDict(populate_by_name=True)
    external_id: Optional[str] = Field(None, alias="id")
    exercise_name: str = Field(..., alias="exerciseName")
    sets: int
    reps: Union[str, int]
    weight: Optional[float] = 0.0
    exercise_sets: Optional[List[ExerciseSet]] = Field(None, alias="exerciseSets")
    order: Optional[int] = None
    equipment: Optional[str] = None
    difficulty: Optional[str] = None
    instructions: Optional[str] = None
    focus_area: Optional[str] = Field(None, alias="focusArea")
    primary_muscles: Optional[List[str]] = Field(None, alias="primaryMuscles")
    rest_time: Optional[int] = Field(None, alias="restTime")
    backend_id: Optional[int] = Field(None, alias="backendId")


class TrainingRecord(BaseModel):
    """训练记录"""
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(..., alias="id")
    exercises: List[TrainingData]
    date: Optional[str] = None
    focus_area: Optional[str] = Field(None, alias="focusArea")
    duration: Optional[float] = 0.0
    is_completed: bool = Field(False, alias="isCompleted")


@router.post("/save")
async def save_training(
    data: Union[TrainingRecord, TrainingData, List[TrainingData]],
    user_id: int = Depends(get_current_user)
):
    """保存训练数据"""
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")

    # 统一转换为列表
    if isinstance(data, TrainingRecord):
        items = data.exercises
    elif isinstance(data, TrainingData):
        items = [data]
    else:
        items = data

    # TODO: 调用 training_service 保存数据
    # success_count = save_training_data(user_id, items, ...)
    
    return {
        "code": 200,
        "msg": f"训练数据保存成功 (共 {len(items)} 条)",
        "data": None
    }


@router.get("/gettraining")#summary
async def get_training_summary(
    date: str = Query(None, description="查询日期 (YYYY-MM-DD)"),
    user_id: int = Depends(get_current_user)
):
    """获取训练汇总"""
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")

    if not date:
        date = dt_date.today().strftime("%Y-%m-%d")

    # TODO: 调用 training_service 查询数据
    # return get_training_summary(user_id, date)
    
    return {
        "code": 200,
        "msg": "训练汇总",
        "data": {"date": date, "exercises": []}
    }
