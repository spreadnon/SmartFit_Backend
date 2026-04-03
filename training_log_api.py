from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from jwt_util import parse_token
from db_save_training import save_training_data_to_db, get_training_data_from_db
from datetime import date as date_type

router = APIRouter(prefix="/api/training", tags=["Training Log"])

class TrainingData(BaseModel):
    exercise_name: str
    sets: int
    reps: str
    weight: float = None
    # 可以根据需要添加更多字段，例如：
    # duration_minutes: int = None
    # notes: str = None

@router.post("/savetraining")
async def save_training_data_endpoint(
    data: TrainingData,
    user_id: int = Depends(parse_token)
):
    """
    保存用户的训练数据。
    需要有效的 JWT Token 进行认证。
    """
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")

    success = save_training_data_to_db(user_id, data.dict())
    
    if success:
        return {
            "code": status.HTTP_200_OK,
            "msg": "训练数据保存成功",
            "data": None
        }
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="训练数据保存失败")

@router.get("/gettraining")
async def get_training_data_endpoint(
    date: str = Query(None, description="查询日期 (格式: YYYY-MM-DD), 默认为今天"),
    user_id: int = Depends(parse_token)
):
    """
    按日期查询用户的训练数据。
    默认为当天数据。
    """
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 如果没传日期，默认使用今天
    if not date:
        date = date_type.today().strftime("%Y-%m-%d")
    
    # 获取数据
    trainings = get_training_data_from_db(user_id, date)
    
    return {
        "code": status.HTTP_200_OK,
        "msg": f"查询成功 ({date})",
        "data": trainings
    }
