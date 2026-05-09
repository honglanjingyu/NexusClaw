# app/brain/brain_manager.py
"""大脑管理器 - 统一入口"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from .models import BrainState, BrainResponse, ExecutionStep, ActionType
from .planner import Planner
from .executor import Executor
from .replanner import Replanner
from .workflow import BrainWorkflow
from .intent_types import IntentType
from .intent_router import get_intent_router
from app.action import get_action_manager


class BrainManager:
    """大脑管理器 - 统一入口"""

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.replanner = Replanner()
        self.workflow = None

        self.action_manager = get_action_manager()
        self.intent_router = get_intent_router()

        self._tools_map: Dict[str, Any] = {}

        logger.info("BrainManager 初始化完成，已集成行动模块和意图路由器")

    def register_tool(self, tool: Any) -> None:
        tool_name = tool.name if hasattr(tool, 'name') else tool.__name__
        self._tools_map[tool_name] = tool
        self.action_manager.register_tool(tool)
        logger.info(f"注册工具: {tool_name}")

    def register_tools(self, tools: List[Any]) -> None:
        for tool in tools:
            self.register_tool(tool)

    def register_builtin_tools(self) -> None:
        self.action_manager.register_builtin_tools()
        from app.action.tools import (
            get_current_time, search_knowledge, search_knowledge_with_filter,
            get_knowledge_stats, add_to_knowledge
        )
        for tool in [get_current_time, search_knowledge, search_knowledge_with_filter,
                     get_knowledge_stats, add_to_knowledge]:
            self._tools_map[tool.__name__] = tool

        logger.info(f"已注册内置工具: {list(self._tools_map.keys())}")

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tools_map.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools_map.keys())

    async def think(
            self,
            user_input: str,
            session_id: str,
            perception_context: Optional[Dict[str, Any]] = None,
            available_tools: Optional[List[Dict[str, Any]]] = None
    ) -> BrainResponse:
        """大脑思考入口（非流式）"""
        logger.info(f"[会话 {session_id}] 大脑开始思考: {user_input[:100]}...")

        workflow = BrainWorkflow(
            planner=self.planner,
            executor=self.executor,
            replanner=self.replanner,
            session_id=session_id
        )

        final_state = await workflow.run(
            user_input=user_input,
            perception_context=perception_context or {},
            available_tools=available_tools or []
        )

        response = BrainResponse(
            answer=final_state.response or "抱歉，我无法生成有效的回答。",
            plan=self._state_to_plan(final_state),
            execution_history=final_state.past_steps,
            confidence=0.8 if final_state.response else 0.0,
            needs_more_info=len(final_state.past_steps) >= final_state.max_iterations
        )

        logger.info(f"[会话 {session_id}] 大脑思考完成")
        return response

    async def think_stream(
            self,
            user_input: str,
            session_id: str,
            perception_context: Optional[Dict[str, Any]] = None,
            available_tools: Optional[List[Dict[str, Any]]] = None,
            search_mode: str = "none",
            is_expert: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        大脑思考入口（流式）- 支持前端模式控制

        模式逻辑：
        - 非专家模式 + 知识库搜索：强制使用知识库，不让 LLM 自由选择
        - 非专家模式 + 联网搜索：强制使用联网搜索，不让 LLM 自由选择
        - 非专家模式 + 不搜索：直接回答，不使用任何工具
        - 专家模式：LLM 自由决策，可同时使用两种搜索
        """
        logger.info(f"[会话 {session_id}] 大脑开始思考（流式）: {user_input[:100]}...")
        logger.info(f"[会话 {session_id}] 搜索模式: {search_mode}, 专家模式: {is_expert}")

        # ========== 专家模式：LLM 自由决策 ==========
        if is_expert:
            logger.info(f"[会话 {session_id}] 专家模式，LLM 可自由调用知识库和网络搜索工具")

            yield {"type": "status", "stage": "expert_mode", "message": "专家模式已启用，正在深度分析..."}

            workflow = BrainWorkflow(
                planner=self.planner,
                executor=self.executor,
                replanner=self.replanner,
                session_id=session_id
            )

            async for event in workflow.run_stream(
                    user_input=user_input,
                    perception_context=perception_context or {},
                    available_tools=available_tools or []
            ):
                yield event

            logger.info(f"[会话 {session_id}] 大脑思考完成（流式）")
            return

        # ========== 非专家模式 + 知识库搜索：强制使用知识库 ==========
        if search_mode == "knowledge":
            logger.info(f"[会话 {session_id}] 非专家模式：强制使用知识库搜索")

            yield {"type": "status", "stage": "knowledge_retrieval", "message": "正在检索知识库..."}
            yield {"type": "response_start", "stage": "response_generating"}

            # 执行知识库检索
            search_result = await self._single_knowledge_retrieval(user_input, session_id)

            # 基于检索结果生成回答
            async for chunk in self._generate_with_context(user_input, search_result, session_id):
                if chunk:
                    yield {"type": "response_chunk", "data": chunk}

            yield {"type": "response_end", "stage": "response_complete"}
            yield {"type": "complete", "stage": "completed", "summary": {
                "mode": "knowledge_search",
                "has_results": bool(search_result and "没有找到" not in search_result and "失败" not in search_result)
            }}
            return

        # ========== 非专家模式 + 联网搜索：强制使用联网搜索 ==========
        if search_mode == "web":
            logger.info(f"[会话 {session_id}] 非专家模式：强制使用联网搜索")

            yield {"type": "status", "stage": "web_search", "message": "正在联网搜索..."}
            yield {"type": "response_start", "stage": "response_generating"}

            # 执行联网搜索
            search_result = await self._web_search(user_input, session_id)

            # 基于搜索结果生成回答
            async for chunk in self._generate_with_context(user_input, search_result, session_id):
                if chunk:
                    yield {"type": "response_chunk", "data": chunk}

            yield {"type": "response_end", "stage": "response_complete"}
            yield {"type": "complete", "stage": "completed", "summary": {
                "mode": "web_search",
                "has_results": bool(search_result and "没有找到" not in search_result and "失败" not in search_result)
            }}
            return

        # ========== 非专家模式 + 无搜索：意图识别后处理 ==========
        intent_result = await self.intent_router.route(user_input, session_id)

        # 发送意图识别结果
        yield {
            "type": "intent",
            "stage": "routing",
            "data": {
                "intent": intent_result.intent.value,
                "confidence": intent_result.confidence,
                "reason": intent_result.reason,
                "needs_tools": intent_result.needs_tools,
                "needs_planning": intent_result.needs_planning
            }
        }

        # 简单意图：快速响应
        if intent_result.intent == IntentType.SIMPLE:
            logger.info(f"[会话 {session_id}] 简单意图，使用快速响应模式")

            yield {"type": "status", "stage": "fast_response", "message": "正在生成回答..."}
            yield {"type": "response_start", "stage": "response_generating"}

            async for chunk in self._fast_response(user_input, perception_context, session_id):
                if chunk:
                    yield {"type": "response_chunk", "data": chunk}

            yield {"type": "response_end", "stage": "response_complete"}
            yield {"type": "complete", "stage": "completed", "summary": {
                "mode": "fast",
                "intent": intent_result.intent.value,
                "search_disabled": True
            }}
            return

        # 历史查询意图：快速响应
        if intent_result.intent == IntentType.HISTORY:
            logger.info(f"[会话 {session_id}] 历史查询意图，使用快速响应模式")

            yield {"type": "status", "stage": "fast_response", "message": "正在查询历史记录..."}
            yield {"type": "response_start", "stage": "response_generating"}

            async for chunk in self._fast_response(user_input, perception_context, session_id):
                if chunk:
                    yield {"type": "response_chunk", "data": chunk}

            yield {"type": "response_end", "stage": "response_complete"}
            yield {"type": "complete", "stage": "completed", "summary": {
                "mode": "history",
                "intent": intent_result.intent.value
            }}
            return

        # 复杂问题：使用完整的 Plan-Execute-Replan（无搜索模式）
        logger.info(f"[会话 {session_id}] 复杂意图，使用完整规划模式（无预设搜索）")

        yield {"type": "status", "stage": "planning", "message": "正在分析问题并制定计划..."}

        workflow = BrainWorkflow(
            planner=self.planner,
            executor=self.executor,
            replanner=self.replanner,
            session_id=session_id
        )

        async for event in workflow.run_stream(
                user_input=user_input,
                perception_context=perception_context or {},
                available_tools=available_tools or []
        ):
            yield event

        logger.info(f"[会话 {session_id}] 大脑思考完成（流式）")

    async def _fast_response(
            self,
            user_input: str,
            perception_context: Optional[Dict[str, Any]],
            session_id: str
    ) -> AsyncGenerator[str, None]:
        """快速响应（直接调用 LLM，不经过规划层）"""
        conversation_history = self._extract_conversation_history(perception_context)

        if conversation_history:
            prompt = f"""## 对话历史
{conversation_history}

## 当前问题
{user_input}

请根据对话历史回答用户的问题。回答要简洁、自然、准确。
- 如果用户问的是刚才问过的问题，请从对话历史中回忆并回答
- 如果用户问的是历史记录，请基于已知的对话内容回答
- 不需要调用任何外部工具或搜索知识库"""
        else:
            prompt = f"请简洁、友好地回答用户的问题：{user_input}"

        messages = [
            SystemMessage(content="你是一个友好的AI助手。回答要简洁、自然。能够记住之前的对话内容。"),
            HumanMessage(content=prompt)
        ]

        try:
            from .llm_client import get_llm_client
            llm = get_llm_client()

            async for chunk in llm.stream(messages):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"[会话 {session_id}] 快速响应失败: {e}")
            yield f"抱歉，处理请求时出现问题: {str(e)}"

    async def _single_knowledge_retrieval(
            self,
            query: str,
            session_id: str
    ) -> Optional[str]:
        """单次知识检索（不经过规划层）"""
        try:
            result = await self.action_manager.execute_tool_call(
                tool_name="search_knowledge_base",
                tool_input={"query": query, "top_k": 5},
                session_id=session_id
            )
            return result if result else "未在知识库中找到相关信息"
        except Exception as e:
            logger.error(f"[会话 {session_id}] 知识检索失败: {e}")
            return f"知识库检索失败: {str(e)}"

    async def _web_search(
            self,
            query: str,
            session_id: str
    ) -> Optional[str]:
        """网络搜索（不经过规划层）"""
        try:
            result = await self.action_manager.execute_tool_call(
                tool_name="web_search",
                tool_input={"query": query, "num_results": 5, "search_type": "search"},
                session_id=session_id
            )
            return result if result else "未找到相关网络信息"
        except Exception as e:
            logger.error(f"[会话 {session_id}] 网络搜索失败: {e}")
            return f"网络搜索失败: {str(e)}"

    async def _generate_with_context(
            self,
            user_input: str,
            context: Optional[str],
            session_id: str
    ) -> AsyncGenerator[str, None]:
        """基于上下文生成回答"""
        from .llm_client import get_llm_client

        if context and "没有找到" not in context and "失败" not in context and "错误" not in context:
            prompt = f"""## 用户问题
{user_input}

## 检索到的信息
{context}

## 任务
请根据以上检索到的信息回答用户的问题。
- 如果信息充足，请基于信息回答
- 如果信息不足以回答，请诚实说明目前的信息库中没有相关内容
- 回答要清晰、有条理"""
        else:
            prompt = f"请回答用户的问题（如果无法搜索到相关信息，请诚实告知）：{user_input}"

        messages = [
            SystemMessage(content="你是一个专业的AI助手。请基于提供的信息回答问题。"),
            HumanMessage(content=prompt)
        ]

        try:
            llm = get_llm_client()
            async for chunk in llm.stream(messages):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"[会话 {session_id}] 流式生成失败: {e}")
            yield f"生成回答时出错: {str(e)}"

    def _extract_conversation_history(self, perception_context: Optional[Dict[str, Any]]) -> str:
        """从感知上下文提取对话历史"""
        if not perception_context:
            return ""

        short_term_memory = perception_context.get("short_term_memory", [])
        if not short_term_memory:
            return ""

        history_lines = []
        for item in short_term_memory[-10:]:
            if isinstance(item, dict):
                content = item.get("content", "")
                if ":" in content:
                    parts = content.split(":", 1)
                    role = parts[0] if len(parts) > 0 else "unknown"
                    msg_content = parts[1] if len(parts) > 1 else content
                    role_display = "用户" if role == "user" else "助手" if role == "assistant" else "系统"
                    history_lines.append(f"{role_display}: {msg_content}")
                else:
                    history_lines.append(content)
            elif hasattr(item, 'content'):
                history_lines.append(str(item.content))

        return "\n".join(history_lines)

    def _state_to_plan(self, state: BrainState):
        from .models import Plan
        return Plan(
            steps=state.plan,
            reasoning=""
        )

    def get_state_summary(self, state: BrainState) -> str:
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
    global _brain_manager
    if _brain_manager is None:
        _brain_manager = BrainManager()
    return _brain_manager