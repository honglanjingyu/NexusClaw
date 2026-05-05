# app/brain/workflow.py
"""Plan-Execute-Replan 工作流"""

import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from loguru import logger

from .models import BrainState, BrainPhase, ExecutionStep, ActionType
from .planner import Planner
from .executor import Executor
from .replanner import Replanner


class BrainWorkflow:
    """
    Plan-Execute-Replan 工作流

    流程:
    1. Planning: 制定执行计划
    2. Execution: 执行计划中的步骤
    3. Reflection: 反思结果，决定是继续、调整还是结束
    """

    def __init__(
            self,
            planner: Planner,
            executor: Executor,
            replanner: Replanner,
            session_id: str = ""
    ):
        self.planner = planner
        self.executor = executor
        self.replanner = replanner
        self.session_id = session_id

    async def run(
            self,
            user_input: str,
            perception_context: Dict[str, Any],
            available_tools: List[Dict[str, Any]]
    ) -> BrainState:
        """
        运行工作流（非流式）

        Returns:
            BrainState: 最终状态
        """
        # 初始化状态
        state = BrainState(
            input=user_input,
            session_id=self.session_id,
            perception_context=perception_context,
            available_tools=available_tools,
            phase=BrainPhase.INIT
        )

        # 1. 制定计划
        state.phase = BrainPhase.PLANNING
        plan = await self.planner.plan(
            user_input=user_input,
            perception_context=perception_context,
            available_tools=available_tools,
            session_id=self.session_id
        )
        state.plan = plan.steps

        # 2. 执行和反思循环
        while state.should_continue():
            state.current_iteration += 1
            logger.info(f"[{self.session_id}] 迭代 {state.current_iteration}/{state.max_iterations}")

            # 2.1 执行下一个步骤
            if state.plan:
                state.phase = BrainPhase.EXECUTING
                await self._execute_next_step(state)

            # 2.2 反思并决定下一步
            state.phase = BrainPhase.REFLECTING
            update = await self.replanner.reflect_and_decide(state, self.session_id)

            # 更新状态
            if "response" in update:
                state.response = update["response"]
                state.phase = BrainPhase.RESPONDING
                break
            elif "plan" in update:
                state.plan = update["plan"]

        # 确保有响应
        if not state.response:
            state.phase = BrainPhase.RESPONDING
            update = await self.replanner._generate_response(state, self.session_id)
            state.response = update.get("response", "抱歉，我无法生成有效的回答。")

        state.phase = BrainPhase.COMPLETED
        return state

    async def run_stream(
            self,
            user_input: str,
            perception_context: Dict[str, Any],
            available_tools: List[Dict[str, Any]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行工作流（流式）
        """
        # 初始化状态
        state = BrainState(
            input=user_input,
            session_id=self.session_id,
            perception_context=perception_context,
            available_tools=available_tools,
            phase=BrainPhase.INIT
        )

        # 1. 制定计划
        state.phase = BrainPhase.PLANNING
        yield {"type": "status", "stage": "planning", "message": "正在制定执行计划..."}

        plan = await self.planner.plan(
            user_input=user_input,
            perception_context=perception_context,
            available_tools=available_tools,
            session_id=self.session_id
        )
        state.plan = plan.steps

        yield {
            "type": "plan",
            "stage": "plan_created",
            "message": f"计划已制定，共 {len(plan.steps)} 个步骤",
            "steps": plan.steps,
            "reasoning": plan.reasoning
        }

        # 2. 执行和反思循环
        while state.should_continue():
            state.current_iteration += 1

            # 2.1 执行下一个步骤
            if state.plan:
                state.phase = BrainPhase.EXECUTING
                async for event in self._execute_next_step_stream(state):
                    if event:
                        yield event

            # 2.2 反思并决定下一步
            state.phase = BrainPhase.REFLECTING
            yield {"type": "status", "stage": "reflecting", "message": "正在评估执行结果..."}

            update = await self.replanner.reflect_and_decide(state, self.session_id)

            if "response" in update:
                state.response = update["response"]
                state.phase = BrainPhase.RESPONDING

                # 流式输出响应 - 发送开始标记
                yield {"type": "response_start"}

                # 使用真正的流式生成
                async for chunk in self.replanner._generate_response_stream(state, self.session_id):
                    if chunk:
                        yield {"type": "response_chunk", "data": chunk}

                yield {"type": "response_end"}
                break
            elif "plan" in update:
                state.plan = update["plan"]
                yield {
                    "type": "plan_update",
                    "stage": "plan_updated",
                    "message": f"计划已调整，新步骤数: {len(state.plan)}",
                    "new_steps": state.plan
                }

        # 确保有响应
        if not state.response:
            state.phase = BrainPhase.RESPONDING
            yield {"type": "response_start"}

            # 使用真正的流式生成
            async for chunk in self.replanner._generate_response_stream(state, self.session_id):
                if chunk:
                    yield {"type": "response_chunk", "data": chunk}

            yield {"type": "response_end"}

        # 完成事件
        yield {
            "type": "complete",
            "stage": "completed",
            "message": "大脑处理完成",
            "summary": {
                "steps_executed": len(state.past_steps),
                "plan_remaining": len(state.plan),
                "has_response": state.response is not None
            }
        }

    async def _execute_next_step(self, state: BrainState):
        """执行下一个步骤（非流式）"""
        if not state.plan:
            return

        step = state.plan[0]

        # 决策
        action = await self.executor.decide_action(
            step=step,
            user_input=state.input,
            available_tools=state.available_tools,
            execution_history=state.past_steps,
            session_id=self.session_id
        )

        # 执行
        execution_step = ExecutionStep(step=step, action=action)

        if action.type == ActionType.TOOL_CALL and action.tool_name:
            # 使用执行器的工具执行方法（已改为使用行动模块）
            result = await self.executor.execute_tool(
                tool_name=action.tool_name,
                tool_input=action.tool_input or {},
                session_id=self.session_id
            )
            execution_step.result = result
            # 检查是否成功（不以错误开头）
            execution_step.success = not (result.startswith("错误") or result.startswith("工具"))
        else:
            execution_step.result = action.answer or "步骤已处理"
            execution_step.success = True

        # 更新状态
        state.past_steps.append(execution_step)
        state.plan = state.plan[1:]

        logger.info(f"[{self.session_id}] 步骤完成: {step[:50]}...")

    async def _execute_next_step_stream(
            self,
            state: BrainState
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行下一个步骤（流式）

        Yields:
            步骤执行过程中的事件
        """
        if not state.plan:
            return

        step = state.plan[0]

        # 发出步骤开始事件
        yield {
            "type": "step_start",
            "stage": "step_executing",
            "step": step,
            "remaining_steps": len(state.plan) - 1,
            "total_steps": len(state.plan) + len(state.past_steps)
        }

        # 决策
        action = await self.executor.decide_action(
            step=step,
            user_input=state.input,
            available_tools=state.available_tools,
            execution_history=state.past_steps,
            session_id=self.session_id
        )

        # 执行
        execution_step = ExecutionStep(step=step, action=action)

        if action.type == ActionType.TOOL_CALL and action.tool_name:
            # 发出工具调用事件
            yield {
                "type": "tool_call",
                "stage": "tool_executing",
                "tool": action.tool_name,
                "input": action.tool_input
            }

            # 使用执行器的工具执行方法（已改为使用行动模块）
            result = await self.executor.execute_tool(
                tool_name=action.tool_name,
                tool_input=action.tool_input or {},
                session_id=self.session_id
            )
            execution_step.result = result
            execution_step.success = not (result.startswith("错误") or result.startswith("工具"))
        else:
            execution_step.result = action.answer or "步骤已处理"
            execution_step.success = True

        # 更新状态
        state.past_steps.append(execution_step)
        state.plan = state.plan[1:]

        # 返回步骤完成事件
        yield {
            "type": "step_complete",
            "stage": "step_completed",
            "step": step,
            "result_preview": execution_step.result[:200] if execution_step.result else "",
            "success": execution_step.success,
            "remaining_steps": len(state.plan),
            "executed_steps": len(state.past_steps)
        }