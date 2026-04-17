"""自定义异常"""
from fastapi import HTTPException


class PlanGenerationError(HTTPException):
    """训练计划生成失败"""
    def __init__(self, detail: str = "训练计划生成失败"):
        super().__init__(status_code=500, detail=detail)


class CacheError(Exception):
    """缓存操作异常"""
    pass


class LLMError(Exception):
    """LLM调用异常"""
    pass


class ExerciseDBError(Exception):
    """ExerciseDB加载异常"""
    pass
