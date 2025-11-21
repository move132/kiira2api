"""
会话存储模块

提供会话状态的持久化管理，支持内存和 Redis 两种实现方式。
遵循 SOLID 原则，接口与实现分离，便于扩展。
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Optional
from pydantic import BaseModel
import asyncio


class ConversationSession(BaseModel):
    """会话模型"""
    conversation_id: str
    group_id: str
    token: str
    agent_name: str
    created_at: datetime
    last_active_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConversationStore(ABC):
    """会话存储抽象接口"""

    @abstractmethod
    async def get(self, conversation_id: str) -> Optional[ConversationSession]:
        """获取会话"""
        pass

    @abstractmethod
    async def create(
        self,
        agent_name: str,
        group_id: str,
        token: str,
    ) -> ConversationSession:
        """创建新会话"""
        pass

    @abstractmethod
    async def touch(self, conversation_id: str) -> None:
        """更新会话活跃时间"""
        pass

    @abstractmethod
    async def delete(self, conversation_id: str) -> None:
        """删除会话"""
        pass


class InMemoryConversationStore(ConversationStore):
    """
    内存会话存储实现

    适用于单机开发和测试环境。
    特点：
    - 简单快速，无外部依赖
    - 进程重启后数据丢失
    - 不支持多实例共享
    """

    def __init__(self, ttl_hours: int = 24):
        """
        初始化内存存储

        Args:
            ttl_hours: 会话过期时间（小时），默认 24 小时
        """
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = asyncio.Lock()
        self._ttl = timedelta(hours=ttl_hours)

    def _now(self) -> datetime:
        """
        获取当前时间

        统一时间获取逻辑，便于测试和未来改为时区感知时间。
        """
        return datetime.now()

    async def get(self, conversation_id: str) -> Optional[ConversationSession]:
        """
        获取会话

        自动清理过期会话，遵循 KISS 原则。
        会话只有在业务层显式调用 touch() 时才续期，get() 只用于读取和过期判断。
        """
        async with self._lock:
            session = self._sessions.get(conversation_id)

            if session is None:
                return None

            # 检查是否过期
            if self._now() - session.last_active_at > self._ttl:
                del self._sessions[conversation_id]
                return None

            return session

    async def create(
        self,
        agent_name: str,
        group_id: str,
        token: str,
    ) -> ConversationSession:
        """
        创建新会话

        生成唯一的 conversation_id，避免冲突。
        """
        async with self._lock:
            conversation_id = str(uuid.uuid4())
            now = self._now()

            session = ConversationSession(
                conversation_id=conversation_id,
                group_id=group_id,
                token=token,
                agent_name=agent_name,
                created_at=now,
                last_active_at=now,
            )

            self._sessions[conversation_id] = session
            return session

    async def touch(self, conversation_id: str) -> None:
        """
        更新会话活跃时间

        延长会话生命周期，防止过期。
        """
        async with self._lock:
            session = self._sessions.get(conversation_id)
            if session:
                session.last_active_at = self._now()

    async def delete(self, conversation_id: str) -> None:
        """删除会话"""
        async with self._lock:
            self._sessions.pop(conversation_id, None)

    async def cleanup_expired(self) -> int:
        """
        清理过期会话

        Returns:
            清理的会话数量
        """
        async with self._lock:
            now = self._now()
            expired_ids = [
                conv_id
                for conv_id, session in self._sessions.items()
                if now - session.last_active_at > self._ttl
            ]

            for conv_id in expired_ids:
                del self._sessions[conv_id]

            return len(expired_ids)

    def get_stats(self) -> Dict[str, int]:
        """
        获取存储统计信息

        用于监控和调试。
        注意：此方法返回近似统计，未加锁以避免性能开销。
        """
        now = self._now()
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": sum(
                1 for s in self._sessions.values()
                if now - s.last_active_at <= self._ttl
            ),
        }


# 全局单例实例
_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    """
    获取全局会话存储实例

    使用单例模式，确保全局唯一。
    后续可通过配置切换为 Redis 实现。
    """
    global _store
    if _store is None:
        _store = InMemoryConversationStore()
    return _store


def set_conversation_store(store: ConversationStore) -> None:
    """
    设置全局会话存储实例

    用于测试或切换实现（如 Redis）。
    """
    global _store
    _store = store
