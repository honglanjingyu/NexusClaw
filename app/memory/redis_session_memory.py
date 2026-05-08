# app/memory/redis_session_memory.py
"""
Redis会话记忆管理器 - 支持持久化、自动过期
"""

import os
import json
import time
import hashlib
import uuid
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("警告: redis模块未安装，请运行: pip install redis")

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """单条记忆条目"""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    turn_id: int = 0


class RedisSessionMemory:
    """
    Redis会话记忆存储
    支持多实例共享、自动过期、持久化
    """

    # 默认配置
    DEFAULT_MAX_TURNS = 20
    DEFAULT_MAX_TOKENS = 4000
    DEFAULT_SESSION_TTL = 604800  # 7天

    def __init__(
            self,
            redis_client: redis.Redis = None,
            max_turns: int = None,
            max_tokens: int = None,
            session_ttl: int = None
    ):
        self.max_turns = max_turns or int(os.getenv("MEMORY_MAX_TURNS", self.DEFAULT_MAX_TURNS))
        self.max_tokens = max_tokens or int(os.getenv("MEMORY_MAX_TOKENS", self.DEFAULT_MAX_TOKENS))
        self.session_ttl = session_ttl or int(os.getenv("REDIS_SESSION_TTL", self.DEFAULT_SESSION_TTL))

        # 初始化Redis连接
        if redis_client:
            self.redis_client = redis_client
        elif REDIS_AVAILABLE:
            self.redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD") or None,
                db=int(os.getenv("REDIS_DB", 0)),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            try:
                self.redis_client.ping()
                logger.info("Redis连接成功，会话记忆将使用Redis存储")
            except Exception as e:
                logger.error(f"Redis连接失败: {e}")
                self.redis_client = None
        else:
            self.redis_client = None
            logger.warning("redis模块未安装，会话记忆将使用内存存储")

        # 降级模式：内存存储
        self._fallback_storage: Dict[str, List] = {}
        self._fallback_meta: Dict[str, Dict] = {}

        # Redis key前缀
        self._key_prefix = "agent:session:"
        self._meta_prefix = "agent:session:meta:"
        self._list_prefix = "agent:session:list:"

        logger.info(f"RedisSessionMemory初始化: max_turns={self.max_turns}, session_ttl={self.session_ttl}s")

    def _is_redis_available(self) -> bool:
        return self.redis_client is not None

    def _get_session_key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    def _get_meta_key(self, session_id: str) -> str:
        return f"{self._meta_prefix}{session_id}"

    def _get_list_key(self, user_id: str) -> str:
        return f"{self._list_prefix}{user_id}"

    # app/memory/redis_session_memory.py

    def get_or_create_session(self, session_id: str = None, user_id: str = "default") -> str:
        """获取或创建会话 - 添加详细日志"""
        logger.info(f"get_or_create_session called: session_id={session_id}, user_id={user_id}")

        # 如果提供了 session_id，先检查 Redis 中是否存在
        if session_id:
            logger.info(f"检查会话是否存在: {session_id}")
            exists = self._session_exists(session_id, user_id)
            logger.info(f"_session_exists 返回: {exists}")

            if exists:
                self._update_last_accessed(session_id, user_id)
                logger.info(f"使用已有会话: {session_id}")
                return session_id
            else:
                logger.warning(f"会话 {session_id} 不存在，将创建新会话")
                session_id = None

        # 创建新会话
        new_session_id = session_id or self._generate_session_id()
        logger.info(f"创建新会话: {new_session_id}")

        meta = {
            "session_id": new_session_id,
            "user_id": user_id,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "turn_count": 0,
            "message_count": 0
        }

        if self._is_redis_available():
            try:
                meta_key = self._get_meta_key(new_session_id)
                session_key = self._get_session_key(new_session_id)
                list_key = self._get_list_key(user_id)

                logger.info(f"Redis key 信息:")
                logger.info(f"  meta_key: {meta_key}")
                logger.info(f"  session_key: {session_key}")
                logger.info(f"  list_key: {list_key}")

                # 存储元数据
                self.redis_client.hset(meta_key, mapping=meta)
                self.redis_client.expire(meta_key, self.session_ttl)

                # 验证是否保存成功
                saved = self.redis_client.hgetall(meta_key)
                logger.info(f"保存后验证: {saved}")

                # 添加到用户会话列表
                self.redis_client.lpush(list_key, new_session_id)
                self.redis_client.ltrim(list_key, 0, 99)

                logger.info(f"Redis 会话创建成功: {new_session_id}")
            except Exception as e:
                logger.error(f"Redis 保存会话失败: {e}")
                import traceback
                traceback.print_exc()
                # 降级到内存存储
                if new_session_id not in self._fallback_storage:
                    self._fallback_storage[new_session_id] = []
                self._fallback_meta[new_session_id] = meta
        else:
            logger.warning("Redis 不可用，使用内存存储")
            if new_session_id not in self._fallback_storage:
                self._fallback_storage[new_session_id] = []
            self._fallback_meta[new_session_id] = meta

        return new_session_id

    # app/memory/redis_session_memory.py - 修复 _session_exists 方法

    def _session_exists(self, session_id: str, user_id: str = None) -> bool:
        """检查会话是否存在 - 修复版：只要会话存在就返回 True"""
        logger.info(f"_session_exists: session_id={session_id}, user_id={user_id}")

        if not self._is_redis_available():
            exists = session_id in self._fallback_meta
            logger.info(f"内存存储检查结果: {exists}")
            return exists

        try:
            meta_key = self._get_meta_key(session_id)
            logger.info(f"检查 Redis key: {meta_key}")

            # 检查 key 是否存在
            exists = self.redis_client.exists(meta_key)
            logger.info(f"Redis exists 返回: {exists}")

            if not exists:
                logger.debug(f"会话 {session_id} 元数据不存在: {meta_key}")
                return False

            # 关键修复：如果传入了 user_id，验证匹配；否则只检查会话存在性
            if user_id:
                stored_user = self.redis_client.hget(meta_key, "user_id")
                logger.info(f"存储的 user_id: {stored_user}, 期望的: {user_id}")
                if stored_user != user_id:
                    logger.debug(f"会话 {session_id} 用户不匹配: {stored_user} vs {user_id}")
                    return False

            logger.info(f"会话 {session_id} 存在")
            return True

        except Exception as e:
            logger.error(f"检查 Redis 会话存在性失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_or_create_session(self, session_id: str = None, user_id: str = "default") -> str:
        """获取或创建会话 - 强制使用传入的 ID"""
        logger.info(f"get_or_create_session: session_id={session_id}, user_id={user_id}")

        # 确定要使用的 session_id
        final_session_id = session_id if session_id else self._generate_session_id()

        # 检查会话是否已存在
        if self._session_exists(final_session_id, user_id):
            logger.info(f"会话存在，直接返回: {final_session_id}")
            self._update_last_accessed(final_session_id, user_id)
            return final_session_id

        # 创建新会话
        logger.info(f"创建新会话: {final_session_id}")

        meta = {
            "session_id": final_session_id,
            "user_id": user_id,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "turn_count": 0,
            "message_count": 0
        }

        if self._is_redis_available():
            try:
                meta_key = self._get_meta_key(final_session_id)
                session_key = self._get_session_key(final_session_id)

                # 存储元数据
                self.redis_client.hset(meta_key, mapping=meta)
                self.redis_client.expire(meta_key, self.session_ttl)

                # 验证保存
                saved = self.redis_client.hgetall(meta_key)
                if saved:
                    logger.info(f"✅ 会话元数据保存成功: {final_session_id}")
                else:
                    logger.error(f"❌ 会话元数据保存失败: {meta_key}")

                # 添加到用户会话列表（注意：这里不需要创建空的 session key）
                # 消息 key 会在添加第一条消息时自动创建

                logger.info(f"✅ Redis 会话创建成功: {final_session_id}")
                return final_session_id

            except Exception as e:
                logger.error(f"❌ Redis 保存会话失败: {e}")
                import traceback
                traceback.print_exc()
                # 降级到内存存储
                if final_session_id not in self._fallback_storage:
                    self._fallback_storage[final_session_id] = []
                self._fallback_meta[final_session_id] = meta
        else:
            logger.warning("Redis 不可用，使用内存存储")
            if final_session_id not in self._fallback_storage:
                self._fallback_storage[final_session_id] = []
            self._fallback_meta[final_session_id] = meta

        return final_session_id

    def _update_last_accessed(self, session_id: str, user_id: str = "default"):
        if self._is_redis_available():
            self.redis_client.hset(self._get_meta_key(session_id), "last_accessed", time.time())
            self.redis_client.expire(self._get_session_key(session_id), self.session_ttl)
            self.redis_client.expire(self._get_meta_key(session_id), self.session_ttl)

    def _generate_session_id(self) -> str:
        return hashlib.md5(f"{uuid.uuid4()}_{time.time()}".encode()).hexdigest()[:16]

    # app/memory/redis_session_memory.py - 完整修复

    def add_message(self, session_id: str, role: str, content: str,
                    user_id: str = None, timestamp: float = None) -> bool:
        """
        添加消息到会话记忆

        Args:
            session_id: 会话ID
            role: 角色 ('user', 'assistant', 'system')
            content: 消息内容
            user_id: 用户ID（如果不传，自动从会话元数据获取）
            timestamp: 时间戳
        """
        # 关键修复：如果没有传递 user_id，从 Redis 获取会话的 user_id
        if user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                user_id = stored_user
                logger.debug(f"从会话元数据获取 user_id: {user_id}")
            else:
                user_id = "default"
                logger.warning(f"无法获取会话 {session_id} 的 user_id，使用默认值")
        elif user_id is None:
            user_id = "default"

        if not self._session_exists(session_id, user_id):
            logger.warning(f"会话不存在: {session_id}, user_id={user_id}")
            return False

        timestamp = timestamp or time.time()
        message = {"role": role, "content": content, "timestamp": timestamp}

        if self._is_redis_available():
            key = self._get_session_key(session_id)
            self.redis_client.rpush(key, json.dumps(message, ensure_ascii=False))
            if role == 'user':
                self.redis_client.hincrby(self._get_meta_key(session_id), "turn_count", 1)
            self.redis_client.hincrby(self._get_meta_key(session_id), "message_count", 1)
            self.redis_client.hset(self._get_meta_key(session_id), "last_accessed", time.time())
            self.redis_client.expire(key, self.session_ttl)
            self.redis_client.expire(self._get_meta_key(session_id), self.session_ttl)
            self._trim_session_redis(session_id)
        else:
            if session_id not in self._fallback_storage:
                self._fallback_storage[session_id] = []
            self._fallback_storage[session_id].append(message)
            if session_id in self._fallback_meta:
                if role == 'user':
                    self._fallback_meta[session_id]["turn_count"] += 1
                self._fallback_meta[session_id]["message_count"] += 1
                self._fallback_meta[session_id]["last_accessed"] = time.time()
            self._trim_session_fallback(session_id)

        logger.debug(f"添加消息到会话 {session_id}: {role}")
        return True

    def get_conversation_history(self, session_id: str, user_id: str = None,
                                 max_turns: int = None, max_tokens: int = None) -> List[Dict[str, str]]:
        """获取对话历史"""
        # 如果没有传递 user_id，从 Redis 获取
        if user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                user_id = stored_user
            else:
                user_id = "default"
        elif user_id is None:
            user_id = "default"

        if not self._session_exists(session_id, user_id):
            return []

        self._update_last_accessed(session_id, user_id)

        if self._is_redis_available():
            messages = self._get_messages_redis(session_id)
        else:
            messages = self._fallback_storage.get(session_id, [])

        if not messages:
            return []

        max_turns = max_turns or self.max_turns
        if max_turns and len(messages) > max_turns * 2:
            messages = messages[-(max_turns * 2):]

        max_tokens = max_tokens or self.max_tokens
        if max_tokens:
            messages = self._trim_by_tokens(messages, max_tokens)

        result = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        return result

    def get_session_history(self, session_id: str, user_id: str = None,
                            limit: int = 100, offset: int = 0) -> List[Dict]:
        """获取会话的完整历史（用于前端恢复）"""
        # 如果没有传递 user_id，从 Redis 获取
        if user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                user_id = stored_user
            else:
                user_id = "default"
        elif user_id is None:
            user_id = "default"

        if not self._session_exists(session_id, user_id):
            return []

        if self._is_redis_available():
            messages = self._get_messages_redis(session_id)
        else:
            messages = self._fallback_storage.get(session_id, [])

        start = offset
        end = offset + limit if limit > 0 else len(messages)
        messages = messages[start:end]

        result = []
        for i, msg in enumerate(messages):
            result.append({
                "id": i,
                "role": msg["role"],
                "content": msg["content"],
                "created_at": datetime.fromtimestamp(msg["timestamp"]).isoformat() if "timestamp" in msg else None
            })
        return result

    def _get_messages_redis(self, session_id: str) -> List[Dict]:
        key = self._get_session_key(session_id)
        messages_json = self.redis_client.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages_json]

    # app/memory/redis_session_memory.py

    def get_history_text(self, session_id: str, user_id: str = None,
                         max_turns: int = 10, max_tokens: int = 2000) -> str:
        """获取格式化的历史文本"""
        # 如果没有传递 user_id，从 Redis 获取
        if user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                user_id = stored_user
            else:
                user_id = "default"
        elif user_id is None:
            user_id = "default"

        history = self.get_conversation_history(session_id, user_id, max_turns, max_tokens)
        if not history:
            return ""
        formatted_lines = []
        for msg in history:
            role = "用户" if msg["role"] == "user" else "助手"
            formatted_lines.append(f"{role}: {msg['content']}")
        return "\n".join(formatted_lines)

    def _trim_by_tokens(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        def estimate_tokens(text: str) -> int:
            if not text:
                return 0
            chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
            others = len(text) - chinese
            return int(chinese / 1.5 + others / 4)

        total_tokens = 0
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_tokens(messages[i]["content"])
            if total_tokens + msg_tokens > max_tokens:
                return messages[i + 1:]
            total_tokens += msg_tokens
        return messages

    def _trim_session_redis(self, session_id: str):
        key = self._get_session_key(session_id)
        msg_count = self.redis_client.llen(key)
        if msg_count > self.max_turns * 2:
            excess = msg_count - (self.max_turns * 2)
            self.redis_client.ltrim(key, excess, -1)

        messages = self._get_messages_redis(session_id)
        trimmed = self._trim_by_tokens(messages, self.max_tokens)
        if len(trimmed) != len(messages):
            self.redis_client.delete(key)
            for msg in trimmed:
                self.redis_client.rpush(key, json.dumps(msg, ensure_ascii=False))

    def _trim_session_fallback(self, session_id: str):
        messages = self._fallback_storage.get(session_id, [])
        if len(messages) > self.max_turns * 2:
            self._fallback_storage[session_id] = messages[-(self.max_turns * 2):]
        trimmed = self._trim_by_tokens(self._fallback_storage[session_id], self.max_tokens)
        self._fallback_storage[session_id] = trimmed

    def get_session_info(self, session_id: str, user_id: str = None) -> Optional[Dict]:
        """获取会话信息"""
        logger.info(f"get_session_info: session_id={session_id}, user_id={user_id}")

        # 如果没有传递 user_id，先从 Redis 获取
        actual_user_id = user_id
        if actual_user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                actual_user_id = stored_user
                logger.info(f"从 Redis 获取 user_id: {actual_user_id}")
            else:
                actual_user_id = "default"

        # 检查 Redis 是否可用
        if not self._is_redis_available():
            logger.warning("Redis 不可用，检查内存存储")
            if session_id in self._fallback_meta:
                meta = self._fallback_meta.get(session_id, {})
                if actual_user_id and actual_user_id != meta.get("user_id", "default"):
                    logger.warning(f"用户不匹配: {actual_user_id} vs {meta.get('user_id')}")
                    return None
                msg_count = len(self._fallback_storage.get(session_id, []))
                return {
                    "session_id": session_id,
                    "user_id": meta.get("user_id", actual_user_id),
                    "turn_count": meta.get("turn_count", 0),
                    "message_count": msg_count,
                    "created_at": meta.get("created_at", 0),
                    "last_accessed": meta.get("last_accessed", 0),
                    "is_active": True
                }
            return None

        try:
            meta_key = self._get_meta_key(session_id)
            logger.info(f"检查 Redis key: {meta_key}")

            # 检查 key 是否存在
            if not self.redis_client.exists(meta_key):
                logger.warning(f"Redis key 不存在: {meta_key}")
                return None

            # 获取元数据
            meta = self.redis_client.hgetall(meta_key)
            logger.info(f"从 Redis 获取的 meta: {meta}")

            if not meta:
                logger.warning(f"meta 为空: {meta_key}")
                return None

            # 验证 user_id
            stored_user = meta.get("user_id", "default")
            if actual_user_id and actual_user_id != stored_user:
                logger.warning(f"用户不匹配: actual_user_id={actual_user_id}, stored_user={stored_user}")
                return None

            session_key = self._get_session_key(session_id)
            msg_count = self.redis_client.llen(session_key)
            logger.info(f"会话消息数: {msg_count}")

            result = {
                "session_id": session_id,
                "user_id": stored_user,
                "turn_count": int(meta.get("turn_count", 0)),
                "message_count": msg_count,
                "created_at": float(meta.get("created_at", 0)),
                "last_accessed": float(meta.get("last_accessed", 0)),
                "is_active": True
            }
            logger.info(f"返回会话信息: {result}")
            return result

        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # app/memory/redis_session_memory.py

    def clear_session(self, session_id: str, user_id: str = None) -> bool:
        """清除会话记忆"""
        # 如果没有传递 user_id，从 Redis 获取
        if user_id is None and self._is_redis_available():
            meta_key = self._get_meta_key(session_id)
            stored_user = self.redis_client.hget(meta_key, "user_id")
            if stored_user:
                user_id = stored_user
            else:
                user_id = "default"
        elif user_id is None:
            user_id = "default"

        if self._is_redis_available():
            self.redis_client.delete(self._get_session_key(session_id))
            self.redis_client.delete(self._get_meta_key(session_id))
            self.redis_client.lrem(self._get_list_key(user_id), 1, session_id)
        else:
            self._fallback_storage.pop(session_id, None)
            self._fallback_meta.pop(session_id, None)
        logger.info(f"清除会话: {session_id}")
        return True


# 全局单例
_redis_memory_manager = None


def get_redis_memory_manager() -> RedisSessionMemory:
    global _redis_memory_manager
    if _redis_memory_manager is None:
        _redis_memory_manager = RedisSessionMemory()
    return _redis_memory_manager


__all__ = ['RedisSessionMemory', 'get_redis_memory_manager']