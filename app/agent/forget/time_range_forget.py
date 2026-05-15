# app/agent/forget/time_range_forget.py
"""时间范围遗忘模块 - 支持按时间范围清除记忆"""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from loguru import logger
import json

from .memory_eraser import MemoryEraser
from .memory_eraser import get_memory_eraser


class TimeRangeForgetManager:
    """
    时间范围遗忘管理器

    支持格式:
    - "忘掉:8小时内,白兔"      - 清除过去8小时内关于白兔的记忆
    - "忘掉:24小时前,白兔"     - 清除24小时前的记忆
    - "忘掉:昨天,白兔"         - 清除昨天的记忆
    - "忘掉:今天,白兔"         - 清除今天的记忆
    - "忘掉:本周,白兔"         - 清除本周的记忆
    - "忘掉:本月,白兔"         - 清除本月的记忆
    """

    def __init__(self):
        self._eraser = get_memory_eraser()
        logger.info("TimeRangeForgetManager 初始化完成")

    def is_time_range_forget_request(self, user_input: str) -> bool:
        """判断是否是时间范围遗忘请求"""
        patterns = [
            r'忘掉[：:]\s*\d+\s*小时内\s*[,，]',
            r'忘掉[：:]\s*\d+\s*小时前\s*[,，]',
            r'忘掉[：:]\s*\d+\s*小时\s*[,，]',
            r'忘掉[：:]\s*昨天\s*[,，]',
            r'忘掉[：:]\s*今天\s*[,，]',
            r'忘掉[：:]\s*本周\s*[,，]',
            r'忘掉[：:]\s*本月\s*[,，]',
        ]
        for pattern in patterns:
            if re.search(pattern, user_input):
                return True
        return False

    def parse_time_range(self, user_input: str) -> Optional[tuple]:
        """
        解析时间范围

        Returns:
            (start_time, end_time, keyword) 或 None
        """
        now = datetime.now()

        # 格式: 忘掉:X小时内,关键词
        match = re.search(r'忘掉[：:]\s*(\d+)\s*小时内\s*[,，]\s*(.+)', user_input)
        if match:
            hours = int(match.group(1))
            keyword = match.group(2).strip()
            start_time = now - timedelta(hours=hours)
            return (start_time, now, keyword)

        # 格式: 忘掉:X小时前,关键词
        match = re.search(r'忘掉[：:]\s*(\d+)\s*小时前\s*[,，]\s*(.+)', user_input)
        if match:
            hours = int(match.group(1))
            keyword = match.group(2).strip()
            end_time = now - timedelta(hours=hours)
            return (None, end_time, keyword)

        # 格式: 忘掉:X小时,关键词
        match = re.search(r'忘掉[：:]\s*(\d+)\s*小时\s*[,，]\s*(.+)', user_input)
        if match:
            hours = int(match.group(1))
            keyword = match.group(2).strip()
            start_time = now - timedelta(hours=hours)
            return (start_time, now, keyword)

        # 格式: 忘掉:昨天,关键词
        match = re.search(r'忘掉[：:]\s*昨天\s*[,，]\s*(.+)', user_input)
        if match:
            keyword = match.group(1).strip()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            end_time = start_time + timedelta(days=1)
            return (start_time, end_time, keyword)

        # 格式: 忘掉:今天,关键词
        match = re.search(r'忘掉[：:]\s*今天\s*[,，]\s*(.+)', user_input)
        if match:
            keyword = match.group(1).strip()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
            return (start_time, end_time, keyword)

        # 格式: 忘掉:本周,关键词
        match = re.search(r'忘掉[：:]\s*本周\s*[,，]\s*(.+)', user_input)
        if match:
            keyword = match.group(1).strip()
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            return (start_time, now, keyword)

        # 格式: 忘掉:本月,关键词
        match = re.search(r'忘掉[：:]\s*本月\s*[,，]\s*(.+)', user_input)
        if match:
            keyword = match.group(1).strip()
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return (start_time, now, keyword)

        return None

    async def forget_by_time_range(
            self,
            session_id: str,
            keyword: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            include_working: bool = True,
            include_short_term: bool = True,
            include_redis: bool = True,
            include_long_term: bool = True,
            include_entity: bool = True
    ) -> dict:
        """
        按时间范围清除记忆

        Args:
            session_id: 会话ID
            keyword: 要遗忘的关键词
            start_time: 开始时间（包含）
            end_time: 结束时间（包含）
            include_working: 是否清除工作记忆
            include_short_term: 是否清除短期记忆
            include_redis: 是否清除 Redis 记忆
            include_long_term: 是否清除长期记忆
            include_entity: 是否清除实体记忆
        """
        results = {
            "keyword": keyword,
            "time_range": f"{start_time} ~ {end_time}" if start_time and end_time else "所有时间",
            "short_term_cleared": 0,
            "working_cleared": 0,
            "redis_cleared": 0,
            "long_term_cleared": 0,
            "entity_cleared": 0,
            "total_cleared": 0,
            "success": True,
            "message": ""
        }

        logger.info(f"[会话 {session_id}] 开始时间范围遗忘: keyword='{keyword}', start={start_time}, end={end_time}")

        try:
            # 清除短期记忆（不受时间限制）
            if include_short_term:
                results["short_term_cleared"] = await self._eraser.clear_short_term_memory(keyword, session_id)

            # 清除工作记忆（不受时间限制）
            if include_working:
                results["working_cleared"] = await self._eraser.clear_working_memory(keyword, session_id)

            # 清除实体记忆（不受时间限制）
            if include_entity:
                results["entity_cleared"] = await self._eraser.clear_entity_memory(keyword, session_id)

            # 获取 Redis 管理器进行时间范围过滤
            if include_redis:
                redis = self._eraser._get_redis_memory()
                if redis:
                    history = redis.get_session_history(session_id, limit=500)

                    if history:
                        keep_messages = []
                        for msg in history:
                            content = msg.get("content", "")
                            timestamp = msg.get("created_at")
                            msg_time = None

                            # 解析时间戳
                            if timestamp:
                                try:
                                    if isinstance(timestamp, (int, float)):
                                        msg_time = datetime.fromtimestamp(timestamp)
                                    elif isinstance(timestamp, str):
                                        msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                except:
                                    pass

                            # 判断是否应该保留
                            should_keep = True

                            if keyword.lower() in content.lower():
                                # 时间范围过滤
                                if start_time and msg_time and msg_time < start_time:
                                    should_keep = True
                                elif end_time and msg_time and msg_time > end_time:
                                    should_keep = True
                                else:
                                    should_keep = False
                                    results["redis_cleared"] += 1
                                    logger.info(f"[会话 {session_id}] 删除消息: {content[:50]}...")

                            if should_keep:
                                keep_messages.append(msg)

                        if results["redis_cleared"] > 0:
                            # 重建 Redis 消息列表
                            key = redis._get_session_key(session_id)
                            redis.redis_client.delete(key)

                            for msg in keep_messages:
                                redis.redis_client.rpush(key, json.dumps(msg, ensure_ascii=False))

                            meta_key = redis._get_meta_key(session_id)
                            redis.redis_client.hset(meta_key, "message_count", len(keep_messages))

                            logger.info(f"[会话 {session_id}] 删除 {results['redis_cleared']} 条消息")

            # 清除长期记忆（不受时间限制）
            if include_long_term:
                results["long_term_cleared"] = await self._eraser.clear_long_term_memory(keyword, session_id)

            results["total_cleared"] = (
                results["short_term_cleared"] +
                results["working_cleared"] +
                results["redis_cleared"] +
                results["long_term_cleared"] +
                results["entity_cleared"]
            )

            if results["total_cleared"] > 0:
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

                results["message"] = f"已清除 {', '.join(parts)}"
            else:
                results["message"] = f"📭 没有找到关于「{keyword}」的记忆"

            logger.info(f"[会话 {session_id}] 时间范围遗忘完成: {results['message']}")

        except Exception as e:
            results["success"] = False
            results["message"] = f"遗忘失败: {str(e)}"
            logger.error(f"[会话 {session_id}] 时间范围遗忘失败: {e}")

        return results

    async def process_time_range_forget(
            self,
            user_input: str,
            session_id: str
    ) -> Optional[str]:
        """处理时间范围遗忘请求"""
        if not self.is_time_range_forget_request(user_input):
            return None

        parsed = self.parse_time_range(user_input)
        if not parsed:
            return "❓ 格式错误，请使用如：忘掉:8小时内,白兔"

        start_time, end_time, keyword = parsed

        if not keyword:
            return "❓ 请指定要遗忘的内容"

        result = await self.forget_by_time_range(session_id, keyword, start_time, end_time)

        if result["success"]:
            time_desc = ""
            if start_time and end_time:
                time_desc = f"（{start_time.strftime('%Y-%m-%d %H:%M')} 至 {end_time.strftime('%H:%M')}）"
            elif end_time:
                time_desc = f"（{end_time.strftime('%Y-%m-%d %H:%M')} 之前）"

            return f"🧹 {result['message']}{time_desc}"
        else:
            return f"❌ {result['message']}"


# 全局单例
_time_range_manager = None


def get_time_range_forget_manager() -> TimeRangeForgetManager:
    global _time_range_manager
    if _time_range_manager is None:
        _time_range_manager = TimeRangeForgetManager()
    return _time_range_manager