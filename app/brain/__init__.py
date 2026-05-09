# app/brain/__init__.py
"""大脑模块 (Brain Module)

提供 Agent 的核心决策能力：
- 理解与推理：LLM 驱动的意图理解和任务解析
- 规划分解：将复杂任务拆解为可执行步骤
- 执行决策：决定调用哪个工具或直接回答
- 反思修正：根据执行结果动态调整计划
- 意图路由：快速区分简单/复杂问题
"""

from .models import (
    BrainState,
    Plan,
    Action,
    ExecutionStep,
    BrainResponse,
    ActionType,
)
from .llm_client import LLMClient, get_llm_client
from .planner import Planner
from .executor import Executor
from .replanner import Replanner
from .brain_manager import BrainManager, get_brain_manager
from .workflow import BrainWorkflow
from .intent_types import IntentType, IntentResult  # 新增
from .intent_router import IntentRouter, get_intent_router  # 新增

__all__ = [
    # 数据模型
    "BrainState",
    "Plan",
    "Action",
    "ExecutionStep",
    "BrainResponse",
    "ActionType",
    # 核心组件
    "LLMClient",
    "get_llm_client",
    "Planner",
    "Executor",
    "Replanner",
    "BrainManager",
    "get_brain_manager",
    "BrainWorkflow",
    # 意图路由
    "IntentType",
    "IntentResult",
    "IntentRouter",
    "get_intent_router",
]