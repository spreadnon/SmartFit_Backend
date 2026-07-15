"""Training upload and daily history endpoints."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from fitness_project.core.security import parse_token
from fitness_project.services.training_service import (
    get_training_summary,
    save_training_record,
)


router = APIRouter(prefix="/api/training", tags=["训练记录"])


class ExerciseSetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36)
    weight: float = Field(ge=0)
    reps: int = Field(ge=0)
    is_completed: bool = False


class ExercisePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36)
    backend_id: Optional[str] = Field(default=None, max_length=255)
    order: int = Field(ge=0)
    exercise_name: str = Field(min_length=1, max_length=200)
    sets: int = Field(ge=0)
    reps: str = Field(max_length=32)
    equipment: str = Field(default="", max_length=100)
    difficulty: str = Field(default="", max_length=32)
    images: List[str] = Field(default_factory=list)
    instructions: str = ""
    focus_area: str = Field(default="", max_length=100)
    primary_muscles: List[str] = Field(default_factory=list)
    rest_time: int = Field(default=90, ge=0, le=3600)
    exercise_sets: List[ExerciseSetPayload] = Field(default_factory=list)


class TrainingRecordPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36)
    date: datetime
    focus_area: str = Field(default="", max_length=200)
    exercises: List[ExercisePayload]
    duration: float = Field(default=0, ge=0)
    is_completed: bool = False


@router.post("/save")
async def save_training(
    record: TrainingRecordPayload,
    user_id: int = Depends(parse_token),
):
    saved = save_training_record(user_id, record)
    return {"code": 200, "msg": "saved", "data": saved}


@router.get("/gettraining")
async def fetch_training(
    date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user_id: int = Depends(parse_token),
):
    selected_date = date or datetime.now().date().isoformat()
    return get_training_summary(user_id, selected_date)
