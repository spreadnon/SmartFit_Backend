from fastapi import APIRouter
from .plan import router as plan_router
from .auth import router as auth_router
from .training import router as training_router

router = APIRouter(prefix="/api")#/v1
router.include_router(plan_router)
router.include_router(auth_router)
router.include_router(training_router)
