# app/agent/forget/__init__.py
"""遗忘模块 - 让 Agent 忘记特定记忆"""

from .forget_manager import ForgetManager
from .memory_eraser import MemoryEraser, get_memory_eraser
from .time_range_forget import TimeRangeForgetManager


def get_forget_manager():
    """获取 ForgetManager 单例"""
    from .forget_manager import ForgetManager
    return ForgetManager()


def get_time_range_forget_manager():
    """获取 TimeRangeForgetManager 单例"""
    from .time_range_forget import TimeRangeForgetManager
    return TimeRangeForgetManager()


__all__ = [
    "ForgetManager",
    "get_forget_manager",
    "MemoryEraser",
    "get_memory_eraser",
    "TimeRangeForgetManager",
    "get_time_range_forget_manager",
]