"""依赖注入 - 管理全局 Agent 实例"""

from typing import Optional, Dict
import asyncio
from loguru import logger

# 注意：这里需要正确导入 Agent
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import Agent, SessionManager

# 全局 Agent 实例
_agent: Optional[Agent] = None
_agent_lock = asyncio.Lock()


async def get_agent() -> Agent:
    """获取全局 Agent 实例（单例，懒加载）"""
    global _agent

    async with _agent_lock:
        if _agent is None:
            _agent = Agent()
            await _agent.initialize()

        return _agent


async def reset_agent():
    """重置 Agent（用于测试或重新初始化）"""
    global _agent
    async with _agent_lock:
        _agent = None


# 会话管理器（用于跟踪活跃会话）
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """获取会话管理器"""
    return _session_manager