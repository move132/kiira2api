"""
模型相关 API 路由
"""
from fastapi import APIRouter, Depends
from typing import Optional
from app.models.schemas import ModelInfo
from app.config import AGENT_LIST
from app.api.dependencies import verify_api_key

router = APIRouter(tags=["models"])

@router.get("/models")
async def get_models(api_key: Optional[str] = Depends(verify_api_key)):
    """
    Get available models endpoint compatible with OpenAI API format.
    """
    models = []
    for agent in AGENT_LIST:
        models.append(
            ModelInfo(
                id=agent,
                object="model",
                created=1677610602,
                owned_by="move132"
            )
        )
    return {
        "object": "list",
        "data": models
    }
