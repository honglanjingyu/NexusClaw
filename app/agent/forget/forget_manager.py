# app/agent/forget/forget_manager.py
"""遗忘管理器 - 处理用户的遗忘请求"""

import re
from typing import Optional
from loguru import logger

from .memory_eraser import MemoryEraser


class ForgetManager:
    """遗忘管理器 - 彻底清除记忆"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._eraser: MemoryEraser = MemoryEraser()
        self._initialized = True
        logger.info("ForgetManager 初始化完成")

    def is_forget_request(self, user_input: str) -> bool:
        """判断是否是遗忘请求"""
        patterns = [
            r'忘掉[：:]',
            r'忘记[：:]',
            r'遗忘[：:]',
            r'清除记忆[：:]',
            r'删除记忆[：:]',
            r'忘掉\s+',
            r'忘记\s+',
        ]
        for pattern in patterns:
            if re.search(pattern, user_input):
                return True
        return False

    def extract_keyword(self, user_input: str) -> Optional[str]:
        """提取要遗忘的关键词"""
        return self._eraser.extract_keyword(user_input)

    async def process_forget_request(self, user_input: str, session_id: str) -> Optional[str]:
        """处理遗忘请求"""
        if not self.is_forget_request(user_input):
            return None

        keyword = self.extract_keyword(user_input)

        if not keyword:
            return "❓ 请指定要遗忘的内容，例如：忘掉:白兔"

        result = await self._eraser.forget(keyword, session_id)

        if result["success"]:
            return f"🧹 {result['message']}"
        else:
            return f"❌ {result['message']}"


# 全局单例
_forget_manager: Optional[ForgetManager] = None


def get_forget_manager() -> ForgetManager:
    """获取遗忘管理器单例"""
    global _forget_manager
    if _forget_manager is None:
        _forget_manager = ForgetManager()
    return _forget_manager