# app/brain/replanner.py
"""重规划器 - 根据执行结果反思并调整计划"""

import asyncio
from typing import List, Dict, Any, AsyncGenerator
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from loguru import logger

from .llm_client import get_llm_client
from .models import ExecutionStep, BrainState


class ReplannerOutput(BaseModel):
    """重规划器输出格式"""
    action: str = Field(description="下一步行动: 'continue', 'replan', 'respond'")
    new_steps: List[str] = Field(default_factory=list, description="新步骤（仅当 action='replan' 时）")
    response: str = Field(default="", description="最终响应（仅当 action='respond' 时）")
    reasoning: str = Field(description="决策理由")


# 重规划器系统提示词
REPLANNER_SYSTEM_PROMPT = """你是一个重新规划专家。你需要根据已执行的步骤，决定下一步行动。

## 决策选项（按优先级排序）

### 1. 'respond' - 生成最终响应【最高优先级】
使用场景：
- 已收集到足够信息回答用户问题
- 已执行步骤数量 >= 3 且获取了关键信息
- 用户问题已经得到解答

### 2. 'continue' - 继续执行当前计划【次优先级】
使用场景：
- 剩余计划合理且能提供关键信息
- 当前步骤成功，有明确的下一个步骤

### 3. 'replan' - 调整计划【最低优先级，谨慎使用】
使用场景：
- 原计划明显错误
- 遇到意外情况需要调整方向
- ⚠️ 新步骤数量不能超过剩余步骤数

## 决策原则
- "信息足够就响应，不要追求完美"
- 优先结束 > 保持不变 > 调整计划
- 如果已执行步骤 >= 5，优先考虑 respond
"""


class Replanner:
    """重规划器"""

    def __init__(self):
        self.llm = get_llm_client()
        logger.info("Replanner 初始化完成")

    # app/brain/replanner.py (关键部分修改)

    async def reflect_and_decide(
            self,
            state: BrainState,
            session_id: str = ""
    ) -> Dict[str, Any]:
        """
        根据执行结果反思并决定下一步
        """
        logger.info(f"[会话 {session_id}] 开始反思规划")
        logger.info(f"  剩余计划: {len(state.plan)} 个步骤")
        logger.info(f"  已执行: {len(state.past_steps)} 个步骤")

        # 强制限制：超过最大迭代次数直接生成响应
        if len(state.past_steps) >= state.max_iterations:
            logger.warning(f"已执行 {len(state.past_steps)} 步，达到最大限制，强制生成响应")
            return await self._generate_response(state, session_id)

        # 如果计划为空，直接生成响应
        if not state.plan and len(state.past_steps) > 0:
            logger.info("计划已执行完毕，生成最终响应")
            return await self._generate_response(state, session_id)

        # 如果已执行步骤 >= 3 且计划为空或很少，考虑直接响应
        if len(state.past_steps) >= 3 and len(state.plan) <= 1:
            logger.info("已执行较多步骤，考虑生成响应")
            return await self._generate_response(state, session_id)

        # 构建上下文
        steps_summary = self._format_history(state.past_steps)
        remaining_plan = ", ".join(state.plan) if state.plan else "无"

        # 简化提示词，加快响应
        user_prompt = f"""
    ## 任务
    {state.input}

    ## 已执行步骤
    {steps_summary if steps_summary else "无"}

    ## 剩余步骤
    {remaining_plan}

    ## 决策
    请选择：'respond'（回答用户）、'continue'（继续执行）
    仅当计划明显错误时才选择 'replan'
    """

        messages = [
            SystemMessage(content="你是任务协调员。优先选择 respond 尽快回答用户。"),
            HumanMessage(content=user_prompt)
        ]

        try:
            # 添加超时控制
            output = await asyncio.wait_for(
                self.llm.invoke_structured(messages, ReplannerOutput),
                timeout=15  # 15秒超时
            )

            logger.info(f"[会话 {session_id}] Replanner 决策: {output.action}")

            if output.action == "respond":
                return await self._generate_response(state, session_id)
            elif output.action == "replan" and len(state.past_steps) < 5:
                if output.new_steps and len(output.new_steps) <= len(state.plan):
                    logger.info(f"计划已调整: {len(output.new_steps)} 个新步骤")
                    return {"plan": output.new_steps}
            else:
                # 默认继续执行
                if state.plan:
                    return {}
                else:
                    return await self._generate_response(state, session_id)

        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"[会话 {session_id}] 重规划失败: {e}")
            # 超时或失败时，直接生成响应
            return await self._generate_response(state, session_id)

    async def _generate_response(
            self,
            state: BrainState,
            session_id: str
    ) -> Dict[str, Any]:
        """生成最终响应"""
        logger.info(f"[会话 {session_id}] 生成最终响应")

        # 格式化执行历史
        history_summary = self._format_history_with_results(state.past_steps)

        if not history_summary:
            # 没有执行历史，直接返回原始输入的回答
            response_prompt = f"请回答用户的问题：{state.input}"
        else:
            response_prompt = f"""
## 原始任务
{state.input}

## 执行过程和结果
{history_summary}

## 任务
请根据以上执行结果，生成一个全面、清晰的最终响应。
"""

        messages = [
            SystemMessage(content="你是一个专业的AI助手，请根据提供的信息生成清晰、准确的回答。"),
            HumanMessage(content=response_prompt)
        ]

        try:
            response = await self.llm.invoke(messages)
            logger.info(f"[会话 {session_id}] 响应生成完成，长度: {len(response)}")
            return {"response": response}
        except Exception as e:
            logger.error(f"[会话 {session_id}] 生成响应失败: {e}")
            return {"response": f"处理您的请求时出现问题: {str(e)}"}

    def _format_history(self, steps: List[ExecutionStep]) -> str:
        """格式化执行历史（简洁版）"""
        if not steps:
            return ""

        lines = []
        for i, step in enumerate(steps, 1):
            status = "✓" if step.success else "✗"
            lines.append(f"{i}. {step.step} [{status}]")

        return "\n".join(lines)

    def _format_history_with_results(self, steps: List[ExecutionStep]) -> str:
        """格式化执行历史（带结果）"""
        if not steps:
            return ""

        lines = []
        for i, step in enumerate(steps, 1):
            lines.append(f"### 步骤{i}: {step.step}")
            if step.result:
                result_preview = step.result[:500] if len(step.result) > 500 else step.result
                lines.append(f"结果: {result_preview}")
            if step.error:
                lines.append(f"错误: {step.error}")
            lines.append("")

        return "\n".join(lines)

    # app/brain/replanner.py - 添加新方法

    async def _generate_response_stream(
            self,
            state: BrainState,
            session_id: str
    ) -> AsyncGenerator[str, None]:
        """生成最终响应（真正的流式）"""
        logger.info(f"[会话 {session_id}] 生成流式响应")

        # 格式化执行历史
        history_summary = self._format_history_with_results(state.past_steps)

        if not history_summary:
            response_prompt = f"请回答用户的问题：{state.input}"
        else:
            response_prompt = f"""
    ## 原始任务
    {state.input}

    ## 执行过程和结果
    {history_summary}

    ## 任务
    请根据以上执行结果，生成一个全面、清晰的最终响应。
    """

        messages = [
            SystemMessage(content="你是一个专业的AI助手，请根据提供的信息生成清晰、准确的回答。"),
            HumanMessage(content=response_prompt)
        ]

        try:
            # 使用真正的流式调用
            async for chunk in self.llm.stream(messages):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"[会话 {session_id}] 生成流式响应失败: {e}")
            yield f"处理您的请求时出现问题: {str(e)}"