# app/api/auth_routes.py
"""认证相关 API 路由"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional
from loguru import logger

from app.db.database import get_db_manager
from app.auth.jwt_utils import create_token, decode_token, get_user_id_from_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ========== 请求/响应模型 ==========

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class RegisterResponse(BaseModel):
    """注册响应"""
    success: bool
    message: str
    user_id: Optional[int] = None
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    message: str
    token: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None


class VerifyResponse(BaseModel):
    """Token 验证响应"""
    success: bool
    user_id: Optional[int] = None
    username: Optional[str] = None


class SessionVerifyRequest(BaseModel):
    """会话验证请求"""
    session_id: str


class SessionVerifyResponse(BaseModel):
    """会话验证响应"""
    success: bool
    authorized: bool
    message: str


# ========== API 端点 ==========

@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest):
    """
    用户注册
    """
    logger.info(f"注册请求: username={request.username}")

    db = get_db_manager()

    # 创建用户
    user = db.create_user(request.username, request.password)

    if not user:
        return RegisterResponse(
            success=False,
            message="用户名已存在或注册失败"
        )

    return RegisterResponse(
        success=True,
        message="注册成功",
        user_id=user.id,
        username=user.username
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录
    """
    logger.info(f"登录请求: username={request.username}")

    db = get_db_manager()

    # 验证用户
    user = db.authenticate_user(request.username, request.password)

    if not user:
        return LoginResponse(
            success=False,
            message="用户名或密码错误"
        )

    # 创建 token
    token = create_token(user.id, user.username)

    return LoginResponse(
        success=True,
        message="登录成功",
        token=token,
        user_id=user.id,
        username=user.username
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_token(authorization: str = Header(None)):
    """
    验证 Token 是否有效
    """
    if not authorization:
        return VerifyResponse(success=False)

    # 提取 Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    payload = decode_token(token)

    if not payload:
        return VerifyResponse(success=False)

    return VerifyResponse(
        success=True,
        user_id=payload.get("user_id"),
        username=payload.get("username")
    )


@router.post("/session/verify", response_model=SessionVerifyResponse)
async def verify_session_access(
    request: SessionVerifyRequest,
    authorization: str = Header(None)
):
    """
    验证用户是否有权访问指定会话
    """
    if not authorization:
        return SessionVerifyResponse(
            success=False,
            authorized=False,
            message="未提供认证信息"
        )

    # 提取 token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    # 获取用户ID
    user_id = get_user_id_from_token(token)

    if not user_id:
        return SessionVerifyResponse(
            success=False,
            authorized=False,
            message="Token 无效或已过期"
        )

    # 验证会话访问权限
    db = get_db_manager()
    authorized = db.verify_session_access(user_id, request.session_id)

    if authorized:
        return SessionVerifyResponse(
            success=True,
            authorized=True,
            message="有权限访问"
        )
    else:
        return SessionVerifyResponse(
            success=True,
            authorized=False,
            message="无权访问此会话"
        )


@router.get("/sessions")
async def get_user_sessions(authorization: str = Header(None)):
    """
    获取当前用户的所有会话
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    # 提取 token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    user_id = get_user_id_from_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    db = get_db_manager()
    sessions = db.get_user_sessions(user_id)

    return {
        "success": True,
        "sessions": sessions
    }