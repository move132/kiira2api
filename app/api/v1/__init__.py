"""
API v1 路由模块
"""
from fastapi import APIRouter
from . import chat, models
router = APIRouter(prefix="/v1")

router.include_router(chat.router)
router.include_router(models.router)
