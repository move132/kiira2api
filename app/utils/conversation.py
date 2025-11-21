"""
会话辅助工具

提供从消息内容中解析会话 ID 等功能，支持多种客户端场景。
"""
import re
from typing import List, Tuple, Optional, Any, Dict

from app.models.schemas import ChatMessage
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 会话 ID 标记格式：[CONVERSATION_ID:<会话ID>]
# 示例：[CONVERSATION_ID:6db0b0a2-88d5-4f71-b8cf-9a2b1ef45d89]
# 支持大小写不敏感，可以出现在文本任意位置
CID_TAG_PATTERN = re.compile(
    r"(?P<before>.*?)\[CONVERSATION_ID:(?P<cid>[^\]]+)\](?P<after>.*)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_from_text(text: str) -> Tuple[Optional[str], str]:
    """
    从单条文本中提取会话 ID，并返回清洗后的文本。

    标记可以出现在文本的任意位置（开头、中间、结尾）。
    解析成功后，标记会从文本中移除，避免污染模型上下文。

    Args:
        text: 待解析的文本内容

    Returns:
        Tuple[Optional[str], str]: (会话ID, 清洗后的文本)
            - 会话ID: 解析成功时返回 ID 字符串，否则返回 None
            - 清洗后的文本: 移除标记后的文本内容

    Examples:
        >>> _extract_from_text("[CONVERSATION_ID:abc-123] Hello")
        ('abc-123', ' Hello')
        >>> _extract_from_text("Hello [CONVERSATION_ID:abc-123]")
        ('abc-123', 'Hello ')
        >>> _extract_from_text("Normal message")
        (None, 'Normal message')
    """
    if not text or not isinstance(text, str):
        return None, text

    match = CID_TAG_PATTERN.search(text)
    if not match:
        return None, text

    # 提取会话 ID（去除首尾空格）
    cid = (match.group("cid") or "").strip()

    # 如果解析到的 ID 为空，视为无效
    if not cid:
        logger.warning("检测到会话 ID 标记但内容为空，忽略该标记")
        return None, text

    # 拼接标记前后的内容，移除标记本身
    before = match.group("before") or ""
    after = match.group("after") or ""
    cleaned = before + after

    logger.debug(f"从消息中解析到会话 ID: {cid}")
    return cid, cleaned


def extract_conversation_id_from_messages(
    messages: List[ChatMessage],
) -> Tuple[Optional[str], List[ChatMessage]]:
    """
    从消息列表中解析会话 ID，并返回清洗后的消息列表。

    解析规则：
    1. 只解析第一个出现的 [CONVERSATION_ID:...] 标记
    2. 支持纯文本消息和多模态消息（OpenAI 格式）
    3. 解析成功后，标记会从消息内容中移除
    4. 后续消息不再尝试解析，避免歧义

    Args:
        messages: 原始消息列表

    Returns:
        Tuple[Optional[str], List[ChatMessage]]: (会话ID, 清洗后的消息列表)
            - 会话ID: 解析成功时返回 ID，否则返回 None
            - 清洗后的消息列表: 移除标记后的消息列表

    Examples:
        纯文本消息：
        >>> messages = [ChatMessage(role="user", content="[CONVERSATION_ID:abc] Hi")]
        >>> cid, cleaned = extract_conversation_id_from_messages(messages)
        >>> cid
        'abc'
        >>> cleaned[0].content
        'Hi'

        多模态消息：
        >>> messages = [ChatMessage(
        ...     role="user",
        ...     content=[
        ...         {"type": "text", "text": "[CONVERSATION_ID:abc] Analyze this:"},
        ...         {"type": "image_url", "image_url": {"url": "https://..."}}
        ...     ]
        ... )]
        >>> cid, cleaned = extract_conversation_id_from_messages(messages)
        >>> cid
        'abc'
    """
    conversation_id: Optional[str] = None
    cleaned_messages: List[ChatMessage] = []

    for msg in messages:
        content = msg.content
        new_msg = msg

        # 处理纯文本消息
        if isinstance(content, str):
            cid, cleaned_text = _extract_from_text(content)
            if cid and conversation_id is None:
                # 只接受第一个会话 ID
                conversation_id = cid
                logger.debug(
                    f"从 {msg.role} 消息中解析到会话 ID: {conversation_id}"
                )
            # 无论是否找到 ID，都清洗标签（避免标签文本进入模型上下文）
            if cid:
                new_msg = msg.copy(update={"content": cleaned_text})

        # 处理多模态消息（OpenAI 格式：[{"type": "text", "text": "..."}, ...]）
        elif isinstance(content, list):
            new_parts: List[Dict[str, Any]] = []
            cid_found: Optional[str] = None

            for part in content:
                # 只处理包含 text 字段的部分
                if (
                    isinstance(part, dict)
                    and isinstance(part.get("text"), str)
                ):
                    cid, cleaned_text = _extract_from_text(part["text"])
                    if cid:
                        if conversation_id is None:
                            # 只接受第一个会话 ID
                            cid_found = cid
                            logger.debug(
                                f"从 {msg.role} 多模态消息中解析到会话 ID: {cid_found}"
                            )
                        # 无论是否接受 ID，都清洗标签
                        part = {**part, "text": cleaned_text}

                new_parts.append(part)

            if cid_found and conversation_id is None:
                conversation_id = cid_found
            # 如果有任何 part 被清洗，更新消息
            if new_parts != content:
                new_msg = msg.copy(update={"content": new_parts})

        cleaned_messages.append(new_msg)

    if conversation_id:
        logger.info(f"成功从消息中提取会话 ID: {conversation_id}")
    else:
        logger.debug("消息中未找到会话 ID 标记")

    return conversation_id, cleaned_messages


def inject_conversation_id_into_response(
    response_data: Dict[str, Any],
    conversation_id: Optional[str]
) -> None:
    """
    在响应内容中自动注入会话 ID 标记。

    用于实现自动上下文传递：在 API 响应中添加标记，
    下次请求时客户端会自动带回，无需用户手动添加。

    Args:
        response_data: 响应数据字典（非流式响应）
        conversation_id: 要注入的会话 ID

    Note:
        - 标记会添加到响应内容的末尾
        - 支持纯文本和多模态内容
        - 下次请求时会被自动解析并清洗
    """
    if not conversation_id:
        return

    tag = f"\n\n[CONVERSATION_ID:{conversation_id}]"
    choices = response_data.get("choices") or []

    for choice in choices:
        message = choice.get("message")
        if not isinstance(message, dict):
            continue

        content = message.get("content")

        # 处理纯文本内容
        if isinstance(content, str):
            message["content"] = (content or "") + tag

        # 处理多模态内容（OpenAI 格式）
        elif isinstance(content, list):
            content.append({"type": "text", "text": tag})

    logger.debug(f"已在响应中注入会话 ID: {conversation_id}")
