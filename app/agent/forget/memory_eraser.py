# app/agent/forget/memory_eraser.py
"""记忆清除器 - 彻底清除指定关键词相关的所有记忆"""

import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger


class MemoryEraser:
    """
    记忆清除器 - 彻底清除记忆

    功能：
    1. 从短期记忆中清除包含关键词的消息
    2. 从工作记忆中清除包含关键词的条目
    3. 从 Redis 会话中删除相关消息
    4. 从长期记忆（Milvus）中删除相关记录
    5. 从实体记忆（文件系统）中删除相关记忆文件
    """

    def __init__(self):
        self._memory_manager = None
        self._dream_manager = None
        self._redis_memory = None
        self._long_term_memory = None
        logger.info("MemoryEraser 初始化完成")

    def _get_memory_manager(self):
        """获取记忆管理器"""
        if self._memory_manager is None:
            try:
                from app.agent.memory import get_memory_manager
                self._memory_manager = get_memory_manager()
            except Exception as e:
                logger.error(f"获取记忆管理器失败: {e}")
        return self._memory_manager

    def _get_dream_manager(self):
        """获取做梦管理器（用于实体记忆）"""
        if self._dream_manager is None:
            try:
                from app.agent.dream import get_dream_manager
                self._dream_manager = get_dream_manager()
            except Exception as e:
                logger.error(f"获取做梦管理器失败: {e}")
        return self._dream_manager

    def _get_redis_memory(self):
        """获取 Redis 记忆管理器"""
        if self._redis_memory is None:
            try:
                from app.agent.memory import get_redis_memory_manager
                self._redis_memory = get_redis_memory_manager()
            except Exception as e:
                logger.error(f"获取 Redis 记忆管理器失败: {e}")
        return self._redis_memory

    def _get_long_term_memory(self):
        """获取长期记忆（Milvus）"""
        if self._long_term_memory is None:
            try:
                from app.agent.memory import get_memory_manager
                mm = get_memory_manager()
                if mm and mm.long_term:
                    self._long_term_memory = mm.long_term
                    if hasattr(mm.long_term, 'vector_store') and mm.long_term.vector_store:
                        vs = mm.long_term.vector_store
                        if hasattr(vs, 'collection') and vs.collection:
                            try:
                                if vs.collection.num_entities > 0:
                                    vs.collection.load()
                                    logger.info("长期记忆集合已预加载")
                            except Exception as e:
                                logger.warning(f"预加载长期记忆集合失败: {e}")
            except Exception as e:
                logger.error(f"获取长期记忆失败: {e}")
        return self._long_term_memory

    def extract_keyword(self, user_input: str) -> Optional[str]:
        """
        从用户输入中提取要遗忘的关键词

        支持格式：
        - "忘掉:xxx"
        - "忘掉：xxx"
        - "忘记:xxx"
        - "遗忘:xxx"
        - "清除记忆:xxx"
        - "删除记忆:xxx"
        """
        patterns = [
            r'忘掉[：:]\s*(.+)',
            r'忘记[：:]\s*(.+)',
            r'遗忘[：:]\s*(.+)',
            r'清除记忆[：:]\s*(.+)',
            r'删除记忆[：:]\s*(.+)',
            r'忘掉\s+(.+)',
            r'忘记\s+(.+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                keyword = match.group(1).strip()
                # 移除可能的时间范围部分
                keyword = re.sub(r'[,，]\s*(昨天|今天|本周|本月|\d+小时|\d+小时内|\d+小时前)', '', keyword)
                keyword = keyword.strip()
                if keyword and len(keyword) > 0:
                    logger.info(f"提取到遗忘关键词: '{keyword}'")
                    return keyword
        return None

    async def clear_short_term_memory(self, keyword: str, session_id: str) -> int:
        """清除短期记忆中包含关键词的消息"""
        count = 0
        memory_manager = self._get_memory_manager()

        if not memory_manager:
            logger.warning("记忆管理器不可用，无法清除短期记忆")
            return 0

        try:
            all_messages = list(memory_manager._short_term._messages)
            filtered_messages = []

            for msg in all_messages:
                content = msg.get("content", "")
                if keyword.lower() in content.lower():
                    count += 1
                    logger.info(f"[会话 {session_id}] 短期记忆删除: {content[:50]}...")
                else:
                    filtered_messages.append(msg)

            if count > 0:
                memory_manager._short_term._messages.clear()
                memory_manager._short_term._message_ids.clear()

                for msg in filtered_messages:
                    memory_manager._short_term._messages.append(msg)
                    memory_manager._short_term._message_ids.append(msg.get("id", ""))

                logger.info(f"[会话 {session_id}] 短期记忆中删除了 {count} 条包含 '{keyword}' 的消息")

        except Exception as e:
            logger.error(f"清除短期记忆失败: {e}")

        return count

    async def clear_working_memory(self, keyword: str, session_id: str) -> int:
        """清除工作记忆中包含关键词的条目"""
        count = 0
        memory_manager = self._get_memory_manager()

        if not memory_manager:
            logger.warning("记忆管理器不可用，无法清除工作记忆")
            return 0

        try:
            working_memory = memory_manager._working
            if not working_memory:
                return 0

            all_items = dict(working_memory._data)
            keys_to_delete = []

            for key, item in all_items.items():
                value = item.get("value", "")
                value_str = str(value)

                if (keyword.lower() in key.lower() or
                        keyword.lower() in value_str.lower()):
                    keys_to_delete.append(key)
                    count += 1
                    logger.info(f"[会话 {session_id}] 工作记忆删除: key={key}")

            for key in keys_to_delete:
                if key in working_memory._data:
                    del working_memory._data[key]

            if count > 0:
                logger.info(f"[会话 {session_id}] 工作记忆中删除了 {count} 条包含 '{keyword}' 的条目")

        except Exception as e:
            logger.error(f"清除工作记忆失败: {e}")

        return count

    async def clear_redis_session_memory(self, keyword: str, session_id: str) -> int:
        """清除 Redis 会话记忆中包含关键词的消息"""
        count = 0
        redis = self._get_redis_memory()

        if not redis:
            logger.warning("Redis 不可用，无法清除会话记忆")
            return 0

        try:
            history = redis.get_session_history(session_id, limit=500)

            if not history:
                return 0

            keep_messages = []
            for msg in history:
                content = msg.get("content", "")
                if keyword.lower() not in content.lower():
                    keep_messages.append(msg)
                else:
                    count += 1
                    logger.info(f"[会话 {session_id}] Redis 删除消息: {content[:50]}...")

            if count > 0:
                key = redis._get_session_key(session_id)
                redis.redis_client.delete(key)

                for msg in keep_messages:
                    redis.redis_client.rpush(key, json.dumps(msg, ensure_ascii=False))

                meta_key = redis._get_meta_key(session_id)
                redis.redis_client.hset(meta_key, "message_count", len(keep_messages))

                logger.info(f"[会话 {session_id}] Redis 记忆中删除了 {count} 条包含 '{keyword}' 的消息")

        except Exception as e:
            logger.error(f"清除 Redis 会话记忆失败: {e}")

        return count

    async def clear_long_term_memory(self, keyword: str, session_id: str) -> int:
        """清除长期记忆（Milvus）中包含关键词的记录"""
        count = 0
        long_term = self._get_long_term_memory()

        if not long_term:
            logger.warning("长期记忆不可用，无法清除")
            return 0

        try:
            vector_store = long_term.vector_store
            if not vector_store or not hasattr(vector_store, 'collection'):
                logger.warning("向量存储不可用")
                return 0

            collection = vector_store.collection
            if not collection:
                return 0

            try:
                if hasattr(collection, 'is_loaded'):
                    if not collection.is_loaded:
                        logger.info(f"集合未加载，正在加载: {vector_store.collection_name}")
                        collection.load()
                else:
                    if collection.num_entities > 0:
                        collection.load()
                logger.info(f"集合状态检查完成，实体数: {collection.num_entities}")
            except Exception as e:
                logger.warning(f"加载集合失败: {e}")
                return 0

            if collection.num_entities == 0:
                logger.info("长期记忆集合为空，无需清除")
                return 0

            try:
                results = vector_store.similarity_search(keyword, k=50)
                if results:
                    ids_to_delete = []
                    for doc in results:
                        if keyword.lower() in doc.page_content.lower():
                            doc_id = doc.metadata.get('id')
                            if doc_id:
                                ids_to_delete.append(int(doc_id) if str(doc_id).isdigit() else doc_id)
                            elif hasattr(doc, 'id'):
                                ids_to_delete.append(doc.id)

                    if ids_to_delete:
                        ids_str = ','.join(str(i) for i in ids_to_delete)
                        expr = f"id in [{ids_str}]"

                        logger.info(f"准备删除 {len(ids_to_delete)} 条长期记忆，IDs: {ids_to_delete[:5]}...")

                        result = collection.delete(expr)
                        collection.flush()
                        count = len(ids_to_delete)
                        logger.info(f"[会话 {session_id}] 长期记忆中删除了 {count} 条包含 '{keyword}' 的记录")

            except Exception as e:
                logger.warning(f"通过搜索删除长期记忆失败: {e}")

                try:
                    if hasattr(vector_store, 'delete_by_metadata'):
                        count = vector_store.delete_by_metadata("text", keyword)
                        logger.info(f"[会话 {session_id}] 通过 metadata 删除了 {count} 条记录")
                except Exception as e2:
                    logger.warning(f"备用删除方法也失败: {e2}")

        except Exception as e:
            logger.error(f"清除长期记忆失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return count

    async def clear_entity_memory(self, keyword: str, session_id: str) -> int:
        """清除实体记忆（文件系统）中包含关键词的记忆"""
        count = 0
        dream_manager = self._get_dream_manager()

        if not dream_manager:
            logger.warning("做梦管理器不可用，无法清除实体记忆")
            return 0

        try:
            all_memories = dream_manager.get_all_memories()

            to_delete = []
            for memory in all_memories:
                if (keyword.lower() in memory.title.lower() or
                        keyword.lower() in memory.content.lower()):
                    to_delete.append(memory.id)
                    count += 1
                    logger.info(f"[会话 {session_id}] 实体记忆删除: {memory.title[:50]}...")

            for memory_id in to_delete:
                dream_manager.delete_memory(memory_id)

            if count > 0:
                logger.info(f"[会话 {session_id}] 实体记忆中删除了 {count} 条包含 '{keyword}' 的记忆")

        except Exception as e:
            logger.error(f"清除实体记忆失败: {e}")

        return count

    # ========== 按模式删除实体记忆的方法 ==========

    async def clear_entity_memory_by_pattern(self, pattern: str, session_id: str) -> int:
        """
        根据文件名模式清除实体记忆

        Args:
            pattern: 文件名匹配模式，如 "20251215_" 删除某天的记忆
            session_id: 会话ID
        """
        try:
            from app.agent.dream import get_dream_manager

            dream_manager = get_dream_manager()
            store = dream_manager._store

            count = store.delete_by_pattern(pattern)
            logger.info(f"[会话 {session_id}] 按模式删除实体记忆: pattern='{pattern}', count={count}")
            return count

        except Exception as e:
            logger.error(f"按模式清除实体记忆失败: {e}")
            return 0

    async def clear_entity_memory_by_date_range(
            self,
            start_date: str,
            end_date: str,
            session_id: str
    ) -> int:
        """
        按日期范围清除实体记忆

        Args:
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            session_id: 会话ID
        """
        try:
            from app.agent.dream import get_dream_manager

            dream_manager = get_dream_manager()
            store = dream_manager._store

            count = store.delete_by_date_range(start_date, end_date)
            logger.info(f"[会话 {session_id}] 按日期范围删除实体记忆: {start_date}~{end_date}, count={count}")
            return count

        except Exception as e:
            logger.error(f"按日期范围清除实体记忆失败: {e}")
            return 0

    async def clear_entity_memory_by_type(self, entity_type: str, session_id: str) -> int:
        """
        按实体类型清除实体记忆

        Args:
            entity_type: 实体类型 (user_preference, user_fact, knowledge_insight, pattern, correction)
            session_id: 会话ID
        """
        try:
            from app.agent.dream import get_dream_manager

            dream_manager = get_dream_manager()
            store = dream_manager._store

            count = store.delete_by_type(entity_type)
            logger.info(f"[会话 {session_id}] 按类型删除实体记忆: type='{entity_type}', count={count}")
            return count

        except Exception as e:
            logger.error(f"按类型清除实体记忆失败: {e}")
            return 0

    async def clear_entity_memory_by_importance(self, min_importance: float, session_id: str) -> int:
        """
        删除重要性低于阈值的实体记忆

        Args:
            min_importance: 最低重要性阈值 (0-1)
            session_id: 会话ID
        """
        try:
            from app.agent.dream import get_dream_manager

            dream_manager = get_dream_manager()
            store = dream_manager._store

            count = store.delete_by_importance_below(min_importance)
            logger.info(f"[会话 {session_id}] 按重要性删除实体记忆: threshold={min_importance}, count={count}")
            return count

        except Exception as e:
            logger.error(f"按重要性清除实体记忆失败: {e}")
            return 0

    # ========== 主遗忘方法 ==========

    async def forget(
            self,
            keyword: str,
            session_id: str,
            include_short_term: bool = True,
            include_working: bool = True,
            include_redis: bool = True,
            include_long_term: bool = True,
            include_entity: bool = True
    ) -> dict:
        """
        执行彻底的遗忘操作

        Args:
            keyword: 要遗忘的关键词
            session_id: 当前会话ID
            include_short_term: 是否清除短期记忆
            include_working: 是否清除工作记忆
            include_redis: 是否清除 Redis 会话记忆
            include_long_term: 是否清除长期记忆（Milvus）
            include_entity: 是否清除实体记忆

        Returns:
            统计结果
        """
        results = {
            "keyword": keyword,
            "short_term_cleared": 0,
            "working_cleared": 0,
            "redis_cleared": 0,
            "long_term_cleared": 0,
            "entity_cleared": 0,
            "total_cleared": 0,
            "success": True,
            "message": ""
        }

        logger.info(f"[会话 {session_id}] 开始彻底遗忘关键词: '{keyword}'")

        try:
            if include_short_term:
                results["short_term_cleared"] = await self.clear_short_term_memory(keyword, session_id)

            if include_working:
                results["working_cleared"] = await self.clear_working_memory(keyword, session_id)

            if include_redis:
                results["redis_cleared"] = await self.clear_redis_session_memory(keyword, session_id)

            if include_long_term:
                results["long_term_cleared"] = await self.clear_long_term_memory(keyword, session_id)

            if include_entity:
                results["entity_cleared"] = await self.clear_entity_memory(keyword, session_id)

            results["total_cleared"] = (
                    results["short_term_cleared"] +
                    results["working_cleared"] +
                    results["redis_cleared"] +
                    results["long_term_cleared"] +
                    results["entity_cleared"]
            )

            parts = []
            if results["short_term_cleared"] > 0:
                parts.append(f"短期记忆 {results['short_term_cleared']} 条")
            if results["working_cleared"] > 0:
                parts.append(f"工作记忆 {results['working_cleared']} 条")
            if results["redis_cleared"] > 0:
                parts.append(f"会话记忆 {results['redis_cleared']} 条")
            if results["long_term_cleared"] > 0:
                parts.append(f"长期记忆 {results['long_term_cleared']} 条")
            if results["entity_cleared"] > 0:
                parts.append(f"实体记忆 {results['entity_cleared']} 条")

            if results["total_cleared"] > 0:
                results["message"] = f"已彻底清除关于「{keyword}」的记忆：{', '.join(parts)}"
            else:
                results["message"] = f"📭 没有找到关于「{keyword}」的任何记忆"

            logger.info(f"[会话 {session_id}] 遗忘完成: {results['message']}")

        except Exception as e:
            results["success"] = False
            results["message"] = f"遗忘失败: {str(e)}"
            logger.error(f"[会话 {session_id}] 遗忘失败: {e}")

        return results


# 全局单例
_eraser: Optional[MemoryEraser] = None


def get_memory_eraser() -> MemoryEraser:
    """获取记忆清除器单例"""
    global _eraser
    if _eraser is None:
        _eraser = MemoryEraser()
    return _eraser