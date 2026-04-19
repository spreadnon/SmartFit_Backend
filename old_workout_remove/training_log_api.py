from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from jwt_util import parse_token
from training_service import save_training_data, get_training_summary
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
    try:
        success_count = save_training_data(user_id, items, record_focus_area, record_duration)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    
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
    return get_training_summary(user_id, date)
