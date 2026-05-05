"""行动执行器 - 执行具体动作"""

from typing import List, Optional, Dict, Any, AsyncGenerator
from loguru import logger
import time

from .models import (
    Action, ActionType, ActionResult, ExecutionContext,
    OutputResult, OutputType
)
from .tool_registry import get_tool_registry, ToolRegistry


class ActionExecutor:
    """
    动作执行器

    负责：
    1. 执行工具调用
    2. 生成直接输出
    3. 管理执行上下文
    """

    def __init__(self):
        self.tool_registry: ToolRegistry = get_tool_registry()
        # 延迟初始化 OutputGenerator
        self._output_generator = None
        logger.info("ActionExecutor 初始化完成")

    @property
    def output_generator(self):
        """延迟获取输出生成器"""
        if self._output_generator is None:
            from .output_generator import OutputGenerator
            self._output_generator = OutputGenerator()
        return self._output_generator

    async def execute_action(
            self,
            action: Action,
            context: ExecutionContext,
            session_id: str = ""
    ) -> ActionResult:
        """
        执行单个动作
        """
        start_time = time.time()

        logger.info(f"[会话 {session_id}] 执行动作: {action.type.value}")

        if action.type == ActionType.TOOL_CALL and action.tool_call:
            result = await self._execute_tool_call(
                action.tool_call,
                context,
                session_id
            )
        elif action.type == ActionType.DIRECT_OUTPUT:
            result = action.content or "处理完成"
        else:
            result = "动作已接收，等待处理"

        execution_time_ms = (time.time() - start_time) * 1000

        return ActionResult(
            action=action,
            success=True,
            result=result,
            execution_time_ms=execution_time_ms
        )

    async def execute_actions(
            self,
            actions: List[Action],
            context: ExecutionContext,
            session_id: str = ""
    ) -> List[ActionResult]:
        """
        批量执行动作
        """
        results = []
        for action in actions:
            result = await self.execute_action(action, context, session_id)
            results.append(result)
        return results

    async def _execute_tool_call(
            self,
            tool_call,
            context: ExecutionContext,
            session_id: str
    ) -> str:
        """执行工具调用"""
        # 传递 session_id
        return await self.tool_registry.execute(
            tool_name=tool_call.name,
            input_data=tool_call.input,
            session_id=session_id
        )

    async def generate_output(
            self,
            user_input: str,
            action_results: List[ActionResult],
            perception_context: Optional[Dict[str, Any]] = None,
            output_type: OutputType = OutputType.MARKDOWN,
            session_id: str = ""
    ) -> OutputResult:
        """
        生成最终输出
        """
        return await self.output_generator.generate(
            user_input=user_input,
            action_results=action_results,
            perception_context=perception_context,
            output_type=output_type,
            session_id=session_id
        )

    async def generate_output_stream(
            self,
            user_input: str,
            action_results: List[ActionResult],
            perception_context: Optional[Dict[str, Any]] = None,
            session_id: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        流式生成输出
        """
        async for chunk in self.output_generator.generate_stream(
                user_input=user_input,
                action_results=action_results,
                perception_context=perception_context,
                session_id=session_id
        ):
            yield chunk

    def get_available_tools_description(self) -> str:
        """获取可用工具描述"""
        return self.tool_registry.get_tools_description()

    def list_tools(self) -> List[str]:
        """列出所有可用工具"""
        return self.tool_registry.list_tools()


# 全局单例
_action_executor: Optional[ActionExecutor] = None


def get_action_executor() -> ActionExecutor:
    """获取全局动作执行器单例"""
    global _action_executor
    if _action_executor is None:
        _action_executor = ActionExecutor()
    return _action_executor