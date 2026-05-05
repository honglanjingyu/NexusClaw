# app/brain/brain_manager.py
"""大脑管理器 - 统一入口"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from loguru import logger

from .models import BrainState, BrainResponse, ExecutionStep, ActionType
from .planner import Planner
from .executor import Executor
from .replanner import Replanner
from .workflow import BrainWorkflow
from app.action import get_action_manager


class BrainManager:
    """大脑管理器 - 统一入口"""

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()  # 现在使用行动模块
        self.replanner = Replanner()
        self.workflow = None  # 延迟初始化

        # 获取行动管理器
        self.action_manager = get_action_manager()

        # 工具映射（用于兼容性）
        self._tools_map: Dict[str, Any] = {}

        logger.info("BrainManager 初始化完成，已集成行动模块")

    def register_tool(self, tool: Any) -> None:
        """
        注册单个工具

        Args:
            tool: 工具函数或 LangChain 工具对象
        """
        tool_name = tool.name if hasattr(tool, 'name') else tool.__name__
        self._tools_map[tool_name] = tool
        self.action_manager.register_tool(tool)
        logger.info(f"注册工具: {tool_name}")

    def register_tools(self, tools: List[Any]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register_tool(tool)

    def register_builtin_tools(self) -> None:
        """注册内置工具 - 使用行动模块的内置工具"""
        # 行动模块已经注册了内置工具
        self.action_manager.register_builtin_tools()

        # 同步工具到本地 map（用于兼容性）
        from app.action.tools import (
            get_current_time, search_knowledge, search_knowledge_with_filter,
            get_knowledge_stats, add_to_knowledge
        )
        for tool in [get_current_time, search_knowledge, search_knowledge_with_filter,
                     get_knowledge_stats, add_to_knowledge]:
            self._tools_map[tool.__name__] = tool

        logger.info(f"已注册内置工具: {list(self._tools_map.keys())}")

    def get_tool(self, name: str) -> Optional[Any]:
        """获取已注册的工具"""
        return self._tools_map.get(name)

    def list_tools(self) -> List[str]:
        """列出所有已注册的工具"""
        return list(self._tools_map.keys())

    async def think(
            self,
            user_input: str,
            session_id: str,
            perception_context: Optional[Dict[str, Any]] = None,
            available_tools: Optional[List[Dict[str, Any]]] = None
    ) -> BrainResponse:
        """
        大脑思考入口（非流式）

        Args:
            user_input: 用户输入
            session_id: 会话ID
            perception_context: 感知上下文
            available_tools: 可用工具描述列表

        Returns:
            BrainResponse: 大脑响应
        """
        logger.info(f"[会话 {session_id}] 大脑开始思考: {user_input[:100]}...")

        # 初始化工作流（不需要传递 tools_map）
        workflow = BrainWorkflow(
            planner=self.planner,
            executor=self.executor,
            replanner=self.replanner,
            session_id=session_id
        )

        # 执行工作流
        final_state = await workflow.run(
            user_input=user_input,
            perception_context=perception_context or {},
            available_tools=available_tools or []
        )

        # 构建响应
        response = BrainResponse(
            answer=final_state.response or "抱歉，我无法生成有效的回答。",
            plan=self._state_to_plan(final_state),
            execution_history=final_state.past_steps,
            confidence=0.8 if final_state.response else 0.0,
            needs_more_info=len(final_state.past_steps) >= final_state.max_iterations
        )

        logger.info(f"[会话 {session_id}] 大脑思考完成")
        return response

    # app/brain/brain_manager.py

    async def think_stream(
            self,
            user_input: str,
            session_id: str,
            perception_context: Optional[Dict[str, Any]] = None,
            available_tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        大脑思考入口（流式）
        """
        logger.info(f"[会话 {session_id}] 大脑开始思考（流式）: {user_input[:100]}...")

        workflow = BrainWorkflow(
            planner=self.planner,
            executor=self.executor,
            replanner=self.replanner,
            session_id=session_id
        )

        # 直接传递事件，不做额外处理
        async for event in workflow.run_stream(
                user_input=user_input,
                perception_context=perception_context or {},
                available_tools=available_tools or []
        ):
            yield event

        logger.info(f"[会话 {session_id}] 大脑思考完成（流式）")

    def _state_to_plan(self, state: BrainState):
        """将状态转换为 Plan 对象"""
        from .models import Plan
        return Plan(
            steps=state.plan,
            reasoning=""
        )

    def get_state_summary(self, state: BrainState) -> str:
        """获取状态摘要"""
        return f"""
## 大脑状态摘要
- 原始输入: {state.input[:100]}...
- 当前阶段: {state.phase.value}
- 计划步骤: {len(state.plan)} 个
- 已执行: {len(state.past_steps)} 步
- 是否有响应: {state.response is not None}
        """.strip()


# 全局单例
_brain_manager: Optional[BrainManager] = None


def get_brain_manager() -> BrainManager:
    """获取全局大脑管理器单例"""
    global _brain_manager
    if _brain_manager is None:
        _brain_manager = BrainManager()
    return _brain_manager