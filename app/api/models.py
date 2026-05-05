"""API 请求/响应数据模型"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ========== 请求模型 ==========

class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="会话ID，不提供则创建新会话")
    stream: bool = Field(False, description="是否流式响应")


class KnowledgeAddRequest(BaseModel):
    """添加知识请求"""
    content: str = Field(..., description="知识内容", min_length=1)
    category: str = Field("general", description="分类")
    source: str = Field("api", description="来源")


class KnowledgeSearchRequest(BaseModel):
    """搜索知识请求"""
    query: str = Field(..., description="搜索关键词", min_length=1)
    top_k: int = Field(5, description="返回数量", ge=1, le=20)
    category: Optional[str] = Field(None, description="分类过滤")


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    user_name: str = Field("user", description="用户名")


# ========== 响应模型 ==========

class ChatResponse(BaseModel):
    """对话响应"""
    success: bool = Field(..., description="是否成功")
    response: str = Field(..., description="助手回复")
    session_id: str = Field(..., description="会话ID")
    steps_executed: int = Field(0, description="执行步骤数")
    elapsed_ms: float = Field(0.0, description="耗时(毫秒)")
    error: Optional[str] = Field(None, description="错误信息")


class KnowledgeAddResponse(BaseModel):
    """添加知识响应"""
    success: bool
    message: str


class KnowledgeSearchResponse(BaseModel):
    """搜索知识响应"""
    success: bool
    message: str
    results: Optional[List[Dict[str, Any]]] = None


class SessionResponse(BaseModel):
    """会话信息响应"""
    session_id: str
    created_at: Optional[str] = None
    user_name: str


class StatusResponse(BaseModel):
    """系统状态响应"""
    initialized: bool
    session_id: str
    tools: List[str]
    active_sessions: List[str]


class MemoryStatsResponse(BaseModel):
    """记忆统计响应"""
    short_term: int
    working: int
    long_term: int
    total: int


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    initialized: bool
    timestamp: str