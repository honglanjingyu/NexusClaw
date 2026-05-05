"""FastAPI 路由定义"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from loguru import logger
import json
import asyncio

from .models import (
    ChatRequest, ChatResponse,
    KnowledgeAddRequest, KnowledgeSearchRequest,
    KnowledgeAddResponse, KnowledgeSearchResponse,  # 添加这两个导入
    SessionCreateRequest,
    SessionResponse, StatusResponse, MemoryStatsResponse, HealthResponse
)
from .dependencies import get_agent, get_session_manager
from main import Agent, SessionManager

# 创建路由器
router = APIRouter(prefix="/api/v1", tags=["Agent"])


# ========== 健康检查 ==========

@router.get("/health", response_model=HealthResponse)
async def health_check(agent: Agent = Depends(get_agent)):
    """健康检查接口"""
    return HealthResponse(
        status="healthy",
        initialized=agent._initialized,
        timestamp=datetime.now().isoformat()
    )


@router.get("/ping")
async def ping():
    """测试连通性"""
    return {"message": "pong", "timestamp": datetime.now().isoformat()}


# ========== 对话接口 ==========

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: Agent = Depends(get_agent),
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    与 Agent 对话

    - **message**: 用户消息内容
    - **session_id**: 会话ID（可选，不提供则自动创建）
    - **stream**: 是否流式响应（暂不支持在非流式接口）
    """
    if not agent._initialized:
        return ChatResponse(
            success=False,
            response="系统正在初始化，请稍后再试...",
            session_id="",
            steps_executed=0,
            elapsed_ms=0,
            error="System initializing"
        )

    # 获取或创建会话
    session_id = session_manager.get_or_create(request.session_id)

    # 设置会话
    if agent._memory_manager:
        agent._memory_manager.set_session(session_id)

    # 执行对话
    result = await agent.chat(request.message)

    return ChatResponse(
        success=result["success"],
        response=result.get("response", ""),
        session_id=session_id,
        steps_executed=result.get("steps_executed", 0),
        elapsed_ms=result.get("elapsed_ms", 0),
        error=result.get("error") if not result["success"] else None
    )


# app/api/routes.py - 修改 chat_stream 函数

@router.post("/chat/stream")
async def chat_stream(
        request: ChatRequest,
        agent: Agent = Depends(get_agent),
        session_manager: SessionManager = Depends(get_session_manager)
):
    """
    流式对话接口
    """
    if not agent._initialized:
        async def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'data': '系统正在初始化'})}\n\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    session_id = session_manager.get_or_create(request.session_id)

    if agent._memory_manager:
        agent._memory_manager.set_session(session_id)

    async def generate():
        """生成流式响应"""
        try:
            # 发送会话信息
            yield f"data: {json.dumps({'type': 'session', 'data': {'session_id': session_id}})}\n\n"

            # 获取感知结果
            perception_result = await agent._perception_manager.perceive(
                input_text=request.message,
                session_id=session_id,
                include_long_term=True,
                top_k=5
            )

            available_tools = []
            for tool_name in agent._action_manager.list_tools():
                available_tools.append({
                    "name": tool_name,
                    "description": agent._get_tool_description(tool_name)
                })

            full_response = ""

            # 流式思考 - 直接处理事件
            async for event in agent._brain_manager.think_stream(
                    user_input=request.message,
                    session_id=session_id,
                    perception_context=perception_result.to_dict(),
                    available_tools=available_tools
            ):
                event_type = event.get("type")

                if event_type == "response_chunk":
                    chunk = event.get("data", "")
                    if chunk:
                        full_response += chunk
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

                elif event_type == "response_start":
                    yield f"data: {json.dumps({'type': 'response_start'})}\n\n"

                elif event_type == "response_end":
                    yield f"data: {json.dumps({'type': 'response_end'})}\n\n"

                elif event_type == "status":
                    yield f"data: {json.dumps({'type': 'status', 'data': event.get('message', '')})}\n\n"

                elif event_type == "plan":
                    yield f"data: {json.dumps({'type': 'plan', 'data': event.get('steps', [])})}\n\n"

                elif event_type == "step_start":
                    yield f"data: {json.dumps({'type': 'step_start', 'data': event.get('step', '')})}\n\n"

                elif event_type == "step_complete":
                    yield f"data: {json.dumps({'type': 'step_complete', 'data': event.get('step', '')})}\n\n"

                elif event_type == "tool_call":
                    yield f"data: {json.dumps({'type': 'tool_call', 'data': event.get('tool', '')})}\n\n"

                elif event_type == "complete":
                    yield f"data: {json.dumps({'type': 'complete', 'data': event.get('summary', {})})}\n\n"

            # 保存到记忆
            if full_response and agent._memory_manager:
                agent._memory_manager.add_user_message(request.message)
                agent._memory_manager.add_assistant_message(full_response)

            if agent._perception_manager:
                agent._perception_manager.add_conversation_to_memory(request.message, full_response)

        except Exception as e:
            logger.error(f"流式响应错误: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ========== 会话管理 ==========

@router.post("/session", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """创建新会话"""
    session_id = session_manager.get_or_create(user_name=request.user_name)
    session_info = session_manager._sessions.get(session_id, {})

    return SessionResponse(
        session_id=session_id,
        created_at=session_info.get("created_at").isoformat() if session_info.get("created_at") else None,
        user_name=session_info.get("user_name", request.user_name)
    )


@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    agent: Agent = Depends(get_agent)
):
    """清空指定会话的记忆"""
    # 切换到指定会话并清空
    old_session = agent.get_session_id()

    agent._current_session_id = session_id
    agent.clear_session()

    # 恢复原会话（如果有）
    if old_session and old_session != session_id:
        agent._current_session_id = old_session

    return {"success": True, "message": f"会话 {session_id} 已清空"}


@router.post("/session/{session_id}/new")
async def new_session(
    session_id: Optional[str] = None,
    agent: Agent = Depends(get_agent)
):
    """创建新会话（切换当前会话）"""
    agent.new_session()

    return {
        "success": True,
        "session_id": agent.get_session_id(),
        "message": "已创建新会话"
    }


# ========== 知识库管理 ==========

@router.post("/knowledge", response_model=KnowledgeAddResponse)
async def add_knowledge(
    request: KnowledgeAddRequest,
    agent: Agent = Depends(get_agent)
):
    """添加知识到知识库"""
    result = await agent.add_knowledge(request.content, request.category)
    return KnowledgeAddResponse(
        success=result["success"],
        message=result["message"]
    )


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    agent: Agent = Depends(get_agent)
):
    """搜索知识库"""
    if request.category:
        # 使用分类过滤
        if agent._action_manager:
            result = await agent._action_manager.execute_tool_call(
                tool_name="search_knowledge_with_filter",
                tool_input={
                    "query": request.query,
                    "category": request.category,
                    "top_k": request.top_k
                },
                session_id=agent.get_session_id()
            )
        else:
            result = "知识库服务不可用"
        return KnowledgeSearchResponse(
            success=True,
            message=result
        )
    else:
        result = await agent.search_knowledge(request.query, request.top_k)
        return KnowledgeSearchResponse(
            success=result["success"],
            message=result["message"]
        )


@router.get("/knowledge/stats")
async def get_knowledge_stats(agent: Agent = Depends(get_agent)):
    """获取知识库统计信息"""
    result = await agent.get_knowledge_stats()
    return result


# ========== 系统状态 ==========

@router.get("/status", response_model=StatusResponse)
async def get_status(
    agent: Agent = Depends(get_agent),
    session_manager: SessionManager = Depends(get_session_manager)
):
    """获取系统状态"""
    status = agent.get_status()
    return StatusResponse(
        initialized=status["initialized"],
        session_id=status.get("session_id", ""),
        tools=status.get("tools", []),
        active_sessions=session_manager.get_all()
    )


@router.get("/memory/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(agent: Agent = Depends(get_agent)):
    """获取记忆统计"""
    stats = await agent.get_memory_stats()
    return MemoryStatsResponse(
        short_term=stats.get("short_term", 0),
        working=stats.get("working", 0),
        long_term=stats.get("long_term", 0),
        total=stats.get("total", 0)
    )


@router.get("/tools")
async def list_tools(agent: Agent = Depends(get_agent)):
    """列出所有可用工具"""
    return {
        "success": True,
        "tools": agent.list_tools()
    }