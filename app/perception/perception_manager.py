# app/perception/perception_manager.py
"""感知管理器 - 统一管理感知模块的所有组件"""

from typing import Optional, Dict, Any
from loguru import logger

from .models import PerceptionResult, InputData, MemoryItem, MemoryType
from .input_handler import InputHandler
from .environment_sensor import EnvironmentSensor
from .config import vector_store_config, validate_config
from datetime import datetime

# 导入统一记忆管理器
from app.memory import get_memory_manager


class PerceptionManager:
    """
    感知管理器 - 使用统一的记忆管理器
    """

    def __init__(self, vector_store_manager=None):
        """
        初始化感知管理器

        Args:
            vector_store_manager: 向量存储管理器（已废弃，使用统一记忆管理器）
        """
        # 验证配置
        validate_config()

        self.input_handler = InputHandler()
        self.environment_sensor = EnvironmentSensor()

        # 直接使用全局记忆管理器（单例）
        self._memory_manager = get_memory_manager(vector_store=vector_store_manager)

        # 会话状态缓存
        self._session_cache: Dict[str, Dict] = {}

        logger.info("PerceptionManager 初始化完成（使用统一记忆管理器）")

    @property
    def memory_retriever(self):
        """为了兼容性，提供 memory_retriever 属性"""
        return self

    async def perceive(
            self,
            input_text: str,
            session_id: str,
            include_long_term: bool = True,
            top_k: Optional[int] = None,
            metadata: Optional[Dict] = None
    ) -> PerceptionResult:
        """
        执行完整的感知流程
        """
        logger.info(f"开始感知流程: session={session_id}, input='{input_text[:100]}...'")

        # 设置会话
        self._memory_manager.set_session(session_id)

        # 1. 输入处理
        input_data = await self.input_handler.process_text(
            text=input_text,
            session_id=session_id,
            metadata=metadata
        )

        # 2. 环境感知
        environment_context = await self.environment_sensor.scan_environment(session_id)

        # 3. 记忆检索（使用统一记忆管理器）
        short_term_items = []
        short_term_messages = self._memory_manager.get_recent_messages(10)
        for msg in short_term_messages:
            item = MemoryItem(
                id=msg.get("id", ""),
                type=MemoryType.SHORT_TERM,
                content=f"{msg['role']}: {msg['content']}",
                metadata=msg.get("metadata", {}),
                score=1.0
            )
            short_term_items.append(item)

        long_term_items = []
        if include_long_term:
            long_term_items = await self._memory_manager.retrieve_long_term(
                query=input_text,
                top_k=top_k,
                filter_metadata=None,
                enable_rerank=True
            )

        working_memory = self._memory_manager.get_all_working()

        # 4. 生成摘要
        summary = self._generate_summary(
            input_data=input_data,
            environment=environment_context,
            short_term_count=len(short_term_items),
            long_term_count=len(long_term_items)
        )

        result = PerceptionResult(
            input_data=input_data,
            environment_context=environment_context,
            short_term_memory=short_term_items,
            long_term_memory=long_term_items,
            working_memory=working_memory,
            summary=summary
        )

        # 缓存结果
        self._session_cache[session_id] = {
            "last_input": input_text,
            "last_perception": result,
            "timestamp": input_data.timestamp
        }

        logger.info(f"感知流程完成: session={session_id}")
        return result

    async def perceive_with_file(
            self,
            file_path: str,
            session_id: str,
            include_long_term: bool = True,
            top_k: Optional[int] = None
    ) -> PerceptionResult:
        """
        带文件的感知流程

        Args:
            file_path: 文件路径
            session_id: 会话ID
            include_long_term: 是否包含长期记忆
            top_k: 长期记忆返回数量

        Returns:
            PerceptionResult: 感知结果
        """
        logger.info(f"开始文件感知流程: session={session_id}, file={file_path}")

        # 设置会话
        self._memory_manager.set_session(session_id)

        # 1. 处理文件输入
        input_data = await self.input_handler.process_file(file_path, session_id)

        # 2. 环境感知
        environment_context = await self.environment_sensor.scan_environment(session_id)

        # 3. 记忆检索（使用文件内容作为查询）
        short_term_items = []
        short_term_messages = self._memory_manager.get_recent_messages(10)
        for msg in short_term_messages:
            item = MemoryItem(
                id=msg.get("id", ""),
                type=MemoryType.SHORT_TERM,
                content=f"{msg['role']}: {msg['content']}",
                metadata=msg.get("metadata", {}),
                score=1.0
            )
            short_term_items.append(item)

        long_term_items = []
        if include_long_term:
            long_term_items = await self._memory_manager.retrieve_long_term(
                query=input_data.content[:500],
                top_k=top_k,
                filter_metadata=None,
                enable_rerank=True
            )

        working_memory = self._memory_manager.get_all_working()

        summary = f"文件感知: {input_data.metadata.get('file_name', 'unknown')}, 大小={input_data.metadata.get('file_size', 0)} 字符"

        return PerceptionResult(
            input_data=input_data,
            environment_context=environment_context,
            short_term_memory=short_term_items,
            long_term_memory=long_term_items,
            working_memory=working_memory,
            summary=summary
        )

    def _generate_summary(
            self,
            input_data: InputData,
            environment: Any,
            short_term_count: int,
            long_term_count: int
    ) -> str:
        """生成感知结果摘要"""
        return f"""
感知摘要:
- 输入类型: {input_data.type.value}
- 输入长度: {len(str(input_data.content))} 字符
- 当前时间: {environment.current_time}
- 环境状态: CPU {environment.system_status.get('cpu_percent', 'N/A')}%, 内存 {environment.system_status.get('memory_percent', 'N/A')}%
- 活动告警: {len(environment.active_alerts)} 个
- 短期记忆: {short_term_count} 条
- 长期记忆: {long_term_count} 条
        """.strip()

    def add_conversation_to_memory(
            self,
            user_input: str,
            assistant_output: str
    ):
        """将对话添加到短期记忆（不保存到 Redis）"""
        # 只添加到短期记忆，不保存到 Redis（避免重复）
        # 因为 routes.py 已经保存到 Redis 了
        self._memory_manager._short_term.add_user_message(user_input)
        self._memory_manager._short_term.add_assistant_message(assistant_output)
        logger.debug(f"添加对话到短期记忆: {user_input[:50]}...")

    def add_to_working_memory(self, key: str, value: Any):
        """添加到工作记忆"""
        self._memory_manager.set_working(key, value)

    def clear_session(self, session_id: str):
        """清空会话"""
        self._memory_manager.clear_session(session_id)
        if session_id in self._session_cache:
            del self._session_cache[session_id]
        logger.info(f"清空会话: {session_id}")

    # 代理记忆管理器的方法（保持兼容性）
    def get_recent_messages(self, n: int = 10):
        return self._memory_manager.get_recent_messages(n)

    def get_short_term_context(self, max_messages: Optional[int] = None):
        return self._memory_manager.get_short_term_context(max_messages)

    def get_all_working(self):
        return self._memory_manager.get_all_working()

    def get_memory_manager(self):
        """获取底层记忆管理器"""
        return self._memory_manager