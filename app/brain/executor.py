# app/brain/executor.py - 修复版

"""执行器 - 执行具体步骤，决定调用工具或直接回答"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from loguru import logger

from .llm_client import get_llm_client
from .models import Action, ActionType, ExecutionStep
from app.action import get_action_manager
from app.action.models import Action as ActionModel, ToolCall, ActionType as ActionModuleType, OutputType


class ExecutorOutput(BaseModel):
    """执行器输出格式"""
    action_type: str = Field(description="动作类型: 'tool_call' 或 'direct_answer'")
    tool_name: Optional[str] = Field(None, description="工具名称（如果是 tool_call）")
    tool_input: Optional[Dict[str, Any]] = Field(None, description="工具参数")
    answer: Optional[str] = Field(None, description="直接回答内容（如果是 direct_answer）")
    reasoning: str = Field(description="决策推理过程")


# 执行器系统提示词
EXECUTOR_SYSTEM_PROMPT = """你是一个任务执行专家。你需要根据当前步骤和目标，决定如何执行。

## 决策规则

### 1. 工具调用 (tool_call)
当满足以下条件时，选择调用工具：
- 需要获取实时数据（如当前时间、系统状态）
- 需要查询外部知识库
- 需要执行计算或操作
- 步骤描述中明确要求使用某个工具

### 2. 直接回答 (direct_answer)
当满足以下条件时，直接回答：
- 问题很简单，不需要外部信息
- 已掌握足够的信息可以回答
- 用户只是在打招呼或闲聊

## 可用工具
- get_current_time: 获取当前真实时间，无需参数，返回格式如 2026-05-04 18:30:00
- search_knowledge: 搜索知识库，参数 query: 搜索词, top_k: 返回数量
- get_knowledge_stats: 获取知识库统计信息

## 输出格式
- action_type: "tool_call" 或 "direct_answer"
- tool_name: 工具名称（仅在 tool_call 时需要）
- tool_input: 工具参数（仅在 tool_call 时需要）
- answer: 直接回答内容（仅在 direct_answer 时需要）
- reasoning: 你的决策理由
"""


class Executor:
    """执行器 - 使用行动模块执行工具"""

    def __init__(self):
        self.llm = get_llm_client()
        # 获取行动管理器
        self.action_manager = get_action_manager()
        logger.info("Executor 初始化完成，已集成行动模块")

    async def decide_action(
            self,
            step: str,
            user_input: str,
            available_tools: List[Dict[str, Any]],
            execution_history: List[ExecutionStep],
            session_id: str = ""
    ) -> Action:
        """
        决定下一步动作

        Args:
            step: 当前步骤描述
            user_input: 原始用户输入
            available_tools: 可用工具列表
            execution_history: 执行历史
            session_id: 会话ID

        Returns:
            Action: 决策动作
        """
        logger.info(f"[会话 {session_id}] 执行步骤: {step}")

        # 构建上下文
        tools_desc = self._format_tools(available_tools)
        history_desc = self._format_history(execution_history)

        user_prompt = f"""
## 原始任务
{user_input}

## 当前步骤
{step}

## 已执行的步骤
{history_desc if history_desc else "无"}

## 可用工具
{tools_desc}

## 任务
请决定如何执行当前步骤。优先考虑是否需要调用工具获取信息。
"""

        messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        try:
            output = await self.llm.invoke_structured(messages, ExecutorOutput)
            logger.info(f"[会话 {session_id}] ExecutorOutput: action_type={output.action_type}, tool_name={output.tool_name}, tool_input={output.tool_input}")

            if output.action_type == "tool_call" and output.tool_name:
                # 创建行动模块的 Action 对象
                action = Action(
                    type=ActionType.TOOL_CALL,
                    tool_name=output.tool_name,
                    tool_input=output.tool_input or {},
                    reasoning=output.reasoning
                )
                logger.info(f"[会话 {session_id}] 决策: 调用工具 {output.tool_name}")
            else:
                action = Action(
                    type=ActionType.DIRECT_ANSWER,
                    answer=output.answer or "处理完成",
                    reasoning=output.reasoning
                )
                logger.info(f"[会话 {session_id}] 决策: 直接回答")

            return action

        except Exception as e:
            logger.error(f"[会话 {session_id}] 执行决策失败: {e}")
            # 默认回退到直接回答
            return Action(
                type=ActionType.DIRECT_ANSWER,
                answer=f"执行步骤时出现问题: {str(e)}",
                reasoning=f"决策失败，使用回退策略"
            )

    async def execute_tool(
            self,
            tool_name: str,
            tool_input: Dict[str, Any],
            session_id: str = ""
    ) -> str:
        """
        执行工具调用 - 使用行动模块

        Args:
            tool_name: 工具名称
            tool_input: 工具参数
            session_id: 会话ID

        Returns:
            str: 工具执行结果
        """
        logger.info(f"[会话 {session_id}] 执行工具: {tool_name}, 参数: {tool_input}")

        # 使用行动模块执行工具调用
        try:
            result = await self.action_manager.execute_tool_call(
                tool_name=tool_name,
                tool_input=tool_input,
                session_id=session_id
            )
            logger.info(f"[会话 {session_id}] 工具执行成功，结果: {result[:100]}...")
            return result

        except Exception as e:
            error_msg = f"工具 '{tool_name}' 执行失败: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def _format_tools(self, tools: List[Dict[str, Any]]) -> str:
        """格式化工具列表"""
        if not tools:
            return "无可用工具"

        lines = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "无描述")[:100]
            lines.append(f"- {name}: {desc}")

        return "\n".join(lines)

    def _format_history(self, history: List[ExecutionStep]) -> str:
        """格式化执行历史"""
        if not history:
            return ""

        lines = []
        for i, step in enumerate(history[-5:], 1):
            status = "✓" if step.success else "✗"
            result_preview = step.result[:100] if step.result else "无结果"
            lines.append(f"{i}. {step.step} [{status}] - {result_preview}...")

        return "\n".join(lines)