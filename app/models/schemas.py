"""
Pydantic 数据模型定义
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str
    content: Union[str, List[Dict[str, Any]]]  # 支持文本或多模态内容（文本+图片）
    group_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """聊天完成请求模型"""
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    conversation_id: Optional[str] = None  # 会话ID，用于保持上下文连续性


class ChatCompletionResponse(BaseModel):
    """聊天完成响应模型"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None
    conversation_id: Optional[str] = None  # 会话ID，用于后续请求保持上下文


class ModelInfo(BaseModel):
    """模型信息模型"""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    """模型列表响应模型"""
    object: str = "list"
    data: List[ModelInfo]
