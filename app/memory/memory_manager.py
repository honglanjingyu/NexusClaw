# app/memory/memory_manager.py (修改版)
"""记忆管理器 - 集成 Redis 会话记忆"""

from typing import List, Optional, Dict, Any
from loguru import logger

from .models import MemoryStats, ShortTermConfig, WorkingMemoryConfig, LongTermConfig
from .short_term_memory import ShortTermMemory
from .working_memory import WorkingMemory
from .long_term_memory import LongTermMemory
from .redis_session_memory import RedisSessionMemory, get_redis_memory_manager


class MemoryManager:
    """
    记忆管理器 - 使用 Redis 进行会话持久化
    """

    def __init__(
            self,
            short_term_config: Optional[ShortTermConfig] = None,
            working_config: Optional[WorkingMemoryConfig] = None,
            long_term_config: Optional[LongTermConfig] = None,
            vector_store=None
    ):
        self._short_term = ShortTermMemory(short_term_config or ShortTermConfig())
        self._working = WorkingMemory(working_config or WorkingMemoryConfig())
        self.long_term = LongTermMemory(vector_store, long_term_config)

        # Redis 会话记忆管理器
        self._redis_memory = get_redis_memory_manager()

        self._current_session_id: Optional[str] = None

        logger.info("MemoryManager 初始化完成（Redis 模式）")

    def set_session(self, session_id: str):
        """设置当前会话ID"""
        self._current_session_id = session_id
        # 从 Redis 加载历史消息到短期记忆
        self._load_session_to_short_term(session_id)
        logger.debug(f"切换到会话: {session_id}")

    def _load_session_to_short_term(self, session_id: str):
        """从 Redis 加载会话历史到短期记忆"""
        history = self._redis_memory.get_conversation_history(session_id, max_turns=self._short_term.config.max_size)
        if history:
            # 清空当前短期记忆
            self._short_term.clear()
            for msg in history:
                role = msg["role"]
                content = msg["content"]
                if role == "user":
                    self._short_term.add_user_message(content)
                elif role == "assistant":
                    self._short_term.add_assistant_message(content)
                elif role == "system":
                    self._short_term.add_system_message(content)
            logger.info(f"从 Redis 加载会话 {session_id}: {len(history)} 条消息")

    @property
    def short_term(self) -> ShortTermMemory:
        if not self._current_session_id:
            raise ValueError("未设置会话，请调用 set_session()")
        return self._short_term

    @property
    def working(self) -> WorkingMemory:
        if not self._current_session_id:
            raise ValueError("未设置会话，请调用 set_session()")
        return self._working

    # ========== 短期记忆方法 ==========
    def add_user_message(self, content: str, metadata: Optional[Dict] = None):
        item = self._short_term.add_user_message(content, metadata)
        if self._current_session_id:
            self._redis_memory.add_message(self._current_session_id, "user", content)
        return item

    def add_assistant_message(self, content: str, metadata: Optional[Dict] = None):
        item = self._short_term.add_assistant_message(content, metadata)
        if self._current_session_id:
            self._redis_memory.add_message(self._current_session_id, "assistant", content)
        return item

    def add_system_message(self, content: str, metadata: Optional[Dict] = None):
        item = self._short_term.add_system_message(content, metadata)
        if self._current_session_id:
            self._redis_memory.add_message(self._current_session_id, "system", content)
        return item

    def add_conversation(self, user_input: str, assistant_output: str):
        user_item = self.add_user_message(user_input)
        assistant_item = self.add_assistant_message(assistant_output)
        return user_item, assistant_item

    def get_short_term_context(self, max_messages: Optional[int] = None) -> str:
        return self._short_term.get_formatted_context(max_messages)

    def get_recent_messages(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._short_term.get_recent(n)

    # ========== 工作记忆方法 ==========
    def set_working(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        return self._working.set(key, value, ttl_seconds)

    def get_working(self, key: str, default: Any = None):
        return self._working.get(key, default)

    def delete_working(self, key: str) -> bool:
        return self._working.delete(key)

    def get_all_working(self) -> Dict[str, Any]:
        return self._working.get_all()

    def get_working_summary(self) -> str:
        return self._working.get_summary()

    # ========== 长期记忆方法 ==========
    async def retrieve_long_term(
            self,
            query: str,
            top_k: Optional[int] = None,
            score_threshold: Optional[float] = None,
            filter_metadata: Optional[Dict[str, Any]] = None,
            use_hybrid: bool = True,
            enable_rerank: bool = True
    ) -> List:
        """检索长期记忆"""
        if use_hybrid and self.long_term.config.enable_hybrid_search:
            return await self.long_term.retrieve_hybrid(
                query=query,
                session_id=self._current_session_id,  # 添加 session_id
                top_k=top_k,
                score_threshold=score_threshold,
                filter_metadata=filter_metadata,
                enable_rerank=enable_rerank
            )
        else:
            return await self.long_term.retrieve(
                query=query,
                session_id=self._current_session_id,
                top_k=top_k,
                score_threshold=score_threshold,
                filter_metadata=filter_metadata,
                enable_rerank=enable_rerank
            )

    async def add_to_long_term(self, content: str, metadata: Optional[Dict] = None, doc_id: Optional[str] = None):
        return await self.long_term.add_knowledge(content, self._current_session_id, metadata, doc_id)

    # ========== 会话管理方法 ==========
    # app/memory/memory_manager.py - 修复 get_session_history
    def get_session_history(self, session_id: str = None, limit: int = 100) -> List[Dict]:
        """获取会话历史（用于前端恢复）"""
        sid = session_id or self._current_session_id
        if not sid:
            return []

        # 确保 Redis 管理器可用
        if not hasattr(self, '_redis_memory') or self._redis_memory is None:
            logger.warning("Redis 记忆管理器不可用")
            return []

        try:
            return self._redis_memory.get_session_history(sid, limit=limit)
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}")
            return []

    def get_session_info(self, session_id: str = None) -> Optional[Dict]:
        """获取会话信息"""
        sid = session_id or self._current_session_id
        if not sid:
            return None

        if not hasattr(self, '_redis_memory') or self._redis_memory is None:
            logger.warning("Redis 记忆管理器不可用")
            return None

        try:
            info = self._redis_memory.get_session_info(sid)
            return info
        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            return None

    def clear_session(self, session_id: Optional[str] = None):
        target = session_id or self._current_session_id
        if target:
            self._short_term.clear()
            self._working.clear()
            self._redis_memory.clear_session(target)
            logger.info(f"清空会话记忆: {target}")

    def get_stats(self) -> MemoryStats:
        short_count = self._short_term.get_size()
        working_count = len(self._working.get_all())
        long_stats = self.long_term.get_stats(self._current_session_id)
        long_count = long_stats.get("num_entities", 0) if long_stats.get("available") else 0
        return MemoryStats(
            short_term_count=short_count,
            long_term_count=long_count,
            working_count=working_count,
            total_count=short_count + long_count + working_count
        )

    def get_all_sessions(self, user_id: str = "default") -> List[str]:
        """获取所有会话ID"""
        # 简化实现：从 Redis 获取
        return []


# 全局单例
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager(vector_store=None) -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(vector_store=vector_store)
    return _memory_manager