"""领域模型定义"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class UserProfile(BaseModel):
    """用户画像"""
    level: str = ""  # 新手/中级/高级
    equipment: List[str] = []  # 可用器械
    target_muscles: List[str] = []  # 目标部位
    injuries: List[str] = []  # 伤病史
    frequency: str = ""  # 训练频率


class ExerciseDetail(BaseModel):
    """动作详情"""
    id: str = ""
    exercise_name: str
    sets: int
    reps: str
    order: int
    equipment: str = ""
    difficulty: str = ""
    images: List[str] = []
    primary_muscles: List[str] = []
    secondary_muscles: List[str] = []
    instructionsCN: List[str] = []
    exercise_type: str = ""


class DailyPlan(BaseModel):
    """每日训练计划"""
    training_day: str
    exercise_list: List[ExerciseDetail]


class TrainingPlan(BaseModel):
    """完整训练计划"""
    training_split: str
    daily_plans: List[DailyPlan]


class UserRequest(BaseModel):
    """用户请求"""
    user_input: str
    user_profile: Dict[str, Any] = {}


class PlanResponse(BaseModel):
    """统一响应格式"""
    code: int
    msg: str
    data: Optional[Any] = None
