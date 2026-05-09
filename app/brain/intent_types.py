# app/brain/intent_types.py
"""意图类型定义 - 独立文件，避免循环导入"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class IntentType(str, Enum):
    """意图类型"""
    SIMPLE = "simple"      # 简单问题：闲聊、问候、感谢等
    HISTORY = "history"    # 历史查询：问我问过什么问题等
    KNOWLEDGE = "knowledge"  # 知识检索：需要查知识库
    COMPLEX = "complex"    # 复杂问题：需要多步规划


class IntentResult(BaseModel):
    """意图识别结果"""
    intent: IntentType = Field(description="意图类型")
    confidence: float = Field(default=0.0, description="置信度 0-1")
    reason: str = Field(default="", description="判断理由")
    needs_tools: bool = Field(default=False, description="是否需要工具调用")
    needs_planning: bool = Field(default=False, description="是否需要完整规划")
    estimated_complexity: int = Field(default=1, description="预估复杂度 1-5")