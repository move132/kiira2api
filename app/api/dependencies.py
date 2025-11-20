"""
API 依赖项
"""
from typing import Optional
from fastapi import Header, HTTPException, status
from app.config import API_KEY
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def verify_api_key(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """
    验证 API Key
    
    支持两种方式：
    1. Authorization: Bearer <token> (OpenAI 兼容格式)
    2. X-API-Key: <token> (备用方式)
    
    Args:
        authorization: Authorization header
        x_api_key: X-API-Key header
        
    Returns:
        Optional[str]: 验证通过的 API Key，如果使用默认值则返回 None
        
    Raises:
        HTTPException: API Key 无效或缺失
    """
    # 如果未配置 API_KEY，跳过验证
    if not API_KEY:
        logger.warning("API_KEY 未配置或使用默认值，跳过鉴权验证")
        return None
    
    api_key = None
    # 方式 1: 从 Authorization header 获取 (Bearer token)
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() == "bearer":
                api_key = token
        except ValueError:
            pass
    
    # 方式 2: 从 X-API-Key header 获取
    if not api_key and x_api_key:
        api_key = x_api_key
    
    # 验证 API Key
    if not api_key:
        logger.warning("请求缺少 API Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Please provide API Key via Authorization header (Bearer token) or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if api_key != API_KEY:
        logger.warning(f"API Key 验证失败: {api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug("API Key 验证通过")
    return api_key

