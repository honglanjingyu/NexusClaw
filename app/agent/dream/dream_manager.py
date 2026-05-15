# app/dream/dream_manager.py
"""做梦管理器 - 核心模块"""

import uuid
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from loguru import logger

from .models import EntityMemory, DreamSession, DreamResult, MemoryCompressionLevel
from .entity_memory import get_entity_memory_store, EntityMemoryStore
from .memory_compressor import get_memory_compressor, MemoryCompressor
from .config import dream_config


class DreamManager:
    """
    做梦管理器

    功能：
    1. 定期扫描未处理的会话
    2. 将对话压缩提炼为实体记忆
    3. 存储到文件系统
    4. 提供记忆查询接口
    """

    def __init__(self):
        self._store: EntityMemoryStore = get_entity_memory_store()
        self._compressor: MemoryCompressor = get_memory_compressor()
        self._processed_sessions: set = set()  # 已处理的会话
        self._is_dreaming = False
        self._last_dream_time: Optional[datetime] = None
        self._redis_memory = None

        # 加载已处理的会话记录
        self._load_processed_sessions()

        logger.info("DreamManager 初始化完成")

    def _get_redis_memory(self):
        """获取 Redis 记忆管理器"""
        if self._redis_memory is None:
            try:
                from app.agent.memory import get_redis_memory_manager
                self._redis_memory = get_redis_memory_manager()
            except Exception as e:
                logger.warning(f"无法获取 Redis 记忆管理器: {e}")
        return self._redis_memory

    def _load_processed_sessions(self):
        """加载已处理的会话记录"""
        # 从实体记忆中提取已处理的会话ID
        all_memories = self._store.get_all()
        for memory in all_memories:
            if memory.source_session_id:
                self._processed_sessions.add(memory.source_session_id)

        logger.info(f"已加载 {len(self._processed_sessions)} 个已处理会话")

    async def get_unprocessed_sessions(self) -> List[Dict[str, Any]]:
        """获取未处理的会话"""
        redis = self._get_redis_memory()
        if not redis:
            return []

        unprocessed = []

        try:
            # 获取所有会话（这里需要从 Redis 获取会话列表）
            # 简化实现：扫描 Redis keys
            import redis as redis_lib
            if hasattr(redis, 'redis_client') and redis.redis_client:
                # 获取所有会话元数据 key
                pattern = "agent:session:meta:*"
                keys = redis.redis_client.keys(pattern)

                for key in keys:
                    session_id = key.replace("agent:session:meta:", "")
                    if session_id not in self._processed_sessions:
                        # 获取会话信息
                        history = redis.get_session_history(session_id, limit=50)
                        if history and len(history) >= 2:  # 至少有一轮对话
                            unprocessed.append({
                                "session_id": session_id,
                                "message_count": len(history),
                                "history": history
                            })
        except Exception as e:
            logger.error(f"获取未处理会话失败: {e}")

        logger.info(f"找到 {len(unprocessed)} 个未处理会话")
        return unprocessed

    async def dream(
            self,
            session_ids: Optional[List[str]] = None,
            force: bool = False
    ) -> DreamResult:
        """
        执行做梦：处理会话，提炼记忆

        Args:
            session_ids: 指定要处理的会话ID，None 则自动检测未处理的
            force: 是否强制重新处理已处理的会话

        Returns:
            DreamResult: 做梦结果
        """
        if self._is_dreaming:
            logger.warning("正在做梦，请稍后再试")
            return DreamResult(
                success=False,
                dream_session_id="",
                memories_created=[],
                sessions_processed=0,
                duration_seconds=0,
                message="Already dreaming"
            )

        self._is_dreaming = True
        dream_session_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(f"🌙 开始做梦: {dream_session_id}")

        try:
            # 获取要处理的会话
            if session_ids is None:
                unprocessed = await self.get_unprocessed_sessions()
                session_ids = [s["session_id"] for s in unprocessed]

                # 限制数量
                if len(session_ids) > dream_config.MAX_MEMORIES_PER_DREAM:
                    session_ids = session_ids[:dream_config.MAX_MEMORIES_PER_DREAM]
            elif force:
                # 强制模式：清除已处理记录
                for sid in session_ids:
                    if sid in self._processed_sessions:
                        self._processed_sessions.remove(sid)

            if not session_ids:
                logger.info("没有需要处理的会话")
                return DreamResult(
                    success=True,
                    dream_session_id=dream_session_id,
                    memories_created=[],
                    sessions_processed=0,
                    duration_seconds=time.time() - start_time,
                    message="No sessions to process"
                )

            logger.info(f"处理 {len(session_ids)} 个会话")

            # 收集所有对话
            all_conversations = []
            processed_count = 0

            for session_id in session_ids:
                # 获取会话历史
                history = await self._get_session_history(session_id)
                if history and len(history) >= 2:
                    all_conversations.extend(history)
                    self._processed_sessions.add(session_id)
                    processed_count += 1

            if not all_conversations:
                return DreamResult(
                    success=True,
                    dream_session_id=dream_session_id,
                    memories_created=[],
                    sessions_processed=0,
                    duration_seconds=time.time() - start_time,
                    message="No conversations found"
                )

            # 压缩提炼记忆
            memories = await self._compressor.compress_conversations(
                conversations=all_conversations,
                session_id=",".join(session_ids),
                level=MemoryCompressionLevel.MEDIUM
            )

            # 保存记忆
            saved_ids = self._store.save_multi(memories)

            # 保存做梦会话记录
            dream_session = DreamSession(
                id=dream_session_id,
                started_at=datetime.fromtimestamp(start_time),
                completed_at=datetime.now(),
                sessions_processed=session_ids,
                memories_created=saved_ids,
                status="completed"
            )

            self._last_dream_time = datetime.now()

            duration = time.time() - start_time
            logger.info(f"✅ 做梦完成: 处理 {processed_count} 个会话, 提炼 {len(memories)} 条记忆, 耗时 {duration:.2f}s")

            return DreamResult(
                success=True,
                dream_session_id=dream_session_id,
                memories_created=memories,
                sessions_processed=processed_count,
                duration_seconds=duration,
                message=f"Created {len(memories)} memories from {processed_count} sessions"
            )

        except Exception as e:
            logger.error(f"做梦失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

            return DreamResult(
                success=False,
                dream_session_id=dream_session_id,
                memories_created=[],
                sessions_processed=0,
                duration_seconds=time.time() - start_time,
                message=str(e)
            )

        finally:
            self._is_dreaming = False

    async def _get_session_history(
            self,
            session_id: str,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取会话历史"""
        redis = self._get_redis_memory()
        if not redis:
            return []

        try:
            history = redis.get_session_history(session_id, limit=limit)
            return history
        except Exception as e:
            logger.error(f"获取会话历史失败 {session_id}: {e}")
            return []

    # 修改 query_memories 方法

    async def query_memories(
            self,
            query: str,
            entity_type: Optional[str] = None,
            min_importance: float = 0.2,  # 降低阈值，让更多记忆被召回
            limit: int = 10
    ) -> List[EntityMemory]:
        """
        查询实体记忆（使用混合检索）
        """
        # 使用混合检索
        results = await self._store.hybrid_search(query, limit=limit, min_similarity=0.25)

        # 按类型过滤
        if entity_type:
            results = [r for r in results if r.entity_type.value == entity_type]

        # 按重要性过滤
        results = [r for r in results if r.importance_score >= min_importance]

        logger.info(f"记忆查询: '{query}' -> {len(results)} 条结果")

        # 打印匹配详情
        for r in results:
            logger.debug(f"  - [{r.entity_type.value}] {r.title[:50]} (重要性: {r.importance_score})")

        return results

    def get_memories_by_type(self, entity_type: str) -> List[EntityMemory]:
        """按类型获取记忆"""
        from .models import EntityType
        try:
            etype = EntityType(entity_type)
            return self._store.search_by_type(etype)
        except ValueError:
            return []

    def get_all_memories(self) -> List[EntityMemory]:
        """获取所有记忆"""
        return self._store.get_all()

    def get_memory_by_id(self, memory_id: str) -> Optional[EntityMemory]:
        """根据ID获取记忆"""
        return self._store.get(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        return self._store.delete(memory_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._store.get_stats()
        stats["last_dream_time"] = self._last_dream_time.isoformat() if self._last_dream_time else None
        stats["is_dreaming"] = self._is_dreaming
        stats["processed_sessions"] = len(self._processed_sessions)
        return stats

    def is_dreaming(self) -> bool:
        """是否正在做梦"""
        return self._is_dreaming


# 全局单例
_dream_manager: Optional[DreamManager] = None


def get_dream_manager() -> DreamManager:
    global _dream_manager
    if _dream_manager is None:
        _dream_manager = DreamManager()
    return _dream_manager