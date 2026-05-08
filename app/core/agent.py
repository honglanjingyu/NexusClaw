# app/core/agent.py
"""Agent 核心类"""

import sys
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 屏蔽 Pydantic 警告
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from loguru import logger

def ensure_logging():
    """确保日志已配置"""
    from loguru import logger
    if not logger._core.handlers:
        LOG_DIR = Path("logs")
        LOG_DIR.mkdir(exist_ok=True)
        logger.add(
            LOG_DIR / "agent_{time:YYYY-MM-DD}.log",
            rotation="1 day",
            retention="30 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
            level="DEBUG",
            encoding="utf-8"
        )


ensure_logging()

class Agent:
    def __init__(self):
        self._initialized = False
        self._brain_manager = None
        self._action_manager = None
        self._memory_manager = None
        self._perception_manager = None
        self._session_manager = None
        self._current_session_id = None

    def set_session_manager(self, session_manager):
        """设置会话管理器"""
        self._session_manager = session_manager

    # app/core/agent.py - 修改 initialize 方法中的会话设置

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        logger.info("=" * 50)
        logger.info("正在初始化 Agent 系统...")
        logger.info("=" * 50)

        try:
            from app.action import get_action_manager
            self._action_manager = get_action_manager()
            self._action_manager.register_builtin_tools()
            logger.info(f"行动模块初始化完成，工具数: {len(self._action_manager.list_tools())}")

            from app.brain import get_brain_manager
            self._brain_manager = get_brain_manager()
            logger.info("大脑模块初始化完成")

            from app.memory import get_memory_manager
            self._memory_manager = get_memory_manager()
            logger.info("记忆模块初始化完成")

            from app.perception import PerceptionManager
            vector_store = None
            if self._memory_manager and self._memory_manager.long_term.vector_store:
                vector_store = self._memory_manager.long_term.vector_store
            self._perception_manager = PerceptionManager(vector_store_manager=vector_store)
            logger.info("感知模块初始化完成")

            # 修复：只有当 memory_manager 存在且有效时才设置会话
            if self._session_manager:
                self._current_session_id = self._session_manager.get_or_create()
            else:
                self._current_session_id = str(uuid.uuid4())[:8]

            # 设置会话到记忆管理器
            if self._memory_manager:
                try:
                    # 确保 Redis 会话存在
                    if hasattr(self._memory_manager, '_redis_memory') and self._memory_manager._redis_memory:
                        existing = self._memory_manager._redis_memory.get_session_info(self._current_session_id)
                        if not existing:
                            self._current_session_id = self._memory_manager._redis_memory.get_or_create_session(
                                user_id="default"
                            )
                    self._memory_manager.set_session(self._current_session_id)
                except Exception as e:
                    logger.warning(f"设置会话到记忆管理器失败: {e}")

            self._initialized = True

            logger.info("=" * 50)
            logger.info("✅ Agent 系统初始化完成！")
            logger.info(f"   会话ID: {self._current_session_id}")
            logger.info(f"   可用工具: {len(self._action_manager.list_tools())} 个")
            logger.info("=" * 50)

            return True

        except Exception as e:
            logger.error(f"Agent 初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def chat(self, user_input: str) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "response": "系统正在初始化，请稍后再试..."}

        if self._memory_manager:
            self._memory_manager.set_session(self._current_session_id)

        start_time = datetime.now()

        try:
            perception_result = await self._perception_manager.perceive(
                input_text=user_input,
                session_id=self._current_session_id,
                include_long_term=True,
                top_k=5
            )

            available_tools = []
            for tool_name in self._action_manager.list_tools():
                available_tools.append({
                    "name": tool_name,
                    "description": self._get_tool_description(tool_name)
                })

            brain_response = await self._brain_manager.think(
                user_input=user_input,
                session_id=self._current_session_id,
                perception_context=perception_result.to_dict(),
                available_tools=available_tools
            )

            if brain_response.answer:
                if self._memory_manager:
                    self._memory_manager.add_user_message(user_input)
                    self._memory_manager.add_assistant_message(brain_response.answer)
                    logger.info(f"对话已保存: user='{user_input[:50]}...', assistant='{brain_response.answer[:50]}...'")

                if self._perception_manager:
                    self._perception_manager.add_conversation_to_memory(user_input, brain_response.answer)

            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            return {
                "success": True,
                "response": brain_response.answer,
                "steps_executed": len(brain_response.execution_history),
                "elapsed_ms": elapsed_ms
            }

        except Exception as e:
            logger.error(f"处理失败: {e}")
            return {"success": False, "response": f"处理失败: {str(e)}"}

    def _get_tool_description(self, tool_name: str) -> str:
        descriptions = {
            "get_current_time": "获取当前真实时间",
            "search_knowledge": "从知识库搜索信息",
            "search_knowledge_with_filter": "按分类搜索知识",
            "get_knowledge_stats": "获取知识库统计信息",
            "add_to_knowledge": "添加知识到知识库",
            "web_search": "网络搜索，参数 query: 搜索词",
            "web_search_advanced": "高级网络搜索"
        }
        return descriptions.get(tool_name, f"工具: {tool_name}")

    async def add_knowledge(self, content: str, category: str = "general") -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="add_to_knowledge",
                tool_input={"content": content, "category": category, "source": "user"},
                session_id=self._current_session_id
            )
            success = "✅" in result or "成功" in result
            return {"success": success, "message": result}
        except Exception as e:
            return {"success": False, "message": f"添加失败: {str(e)}"}

    async def search_knowledge(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="search_knowledge",
                tool_input={"query": query, "top_k": top_k},
                session_id=self._current_session_id
            )
            return {"success": True, "message": result}
        except Exception as e:
            return {"success": False, "message": f"搜索失败: {str(e)}"}

    async def get_knowledge_stats(self) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="get_knowledge_stats",
                tool_input={},
                session_id=self._current_session_id
            )
            return {"success": True, "message": result}
        except Exception as e:
            return {"success": False, "message": f"获取失败: {str(e)}"}

    def list_tools(self) -> List[str]:
        if self._action_manager:
            return self._action_manager.list_tools()
        return []

    def clear_session(self):
        if self._perception_manager:
            self._perception_manager.clear_session(self._current_session_id)
        if self._memory_manager:
            self._memory_manager.clear_session()
        logger.info(f"会话已清空: {self._current_session_id}")

    def new_session(self):
        if self._session_manager:
            self._current_session_id = self._session_manager.get_or_create()
        else:
            self._current_session_id = str(uuid.uuid4())[:8]
        if self._memory_manager:
            self._memory_manager.set_session(self._current_session_id)
        logger.info(f"新会话已创建: {self._current_session_id}")

    def get_session_id(self) -> str:
        return self._current_session_id

    def get_status(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "tools": self.list_tools(),
            "session_id": self._current_session_id,
        }

    async def get_memory_stats(self) -> Dict[str, Any]:
        if self._memory_manager:
            stats = self._memory_manager.get_stats()
            return {
                "short_term": stats.short_term_count,
                "working": stats.working_count,
                "long_term": stats.long_term_count,
                "total": stats.total_count
            }
        return {}