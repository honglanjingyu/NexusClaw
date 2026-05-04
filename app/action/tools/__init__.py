# app/action/tools/__init__.py
"""内置行动工具 - 自动发现和注册"""

import importlib
import inspect
from pathlib import Path
from typing import List, Callable, Any
from loguru import logger

# 需要排除的文件（非工具文件）
EXCLUDE_FILES = {
    "__init__.py",
    "__pycache__",
}

# 需要排除的函数名（非工具函数）
EXCLUDE_FUNCTIONS = {
    "get_long_term_memory",  # 内部辅助函数
}


def discover_tools() -> List[Callable]:
    """
    自动发现 tools 目录下的所有工具函数

    规则：
    1. 只发现 .py 文件
    2. 只发现异步函数（async def）
    3. 函数名不以下划线开头
    4. 排除 EXCLUDE_FUNCTIONS 中的函数
    """
    tools = []
    tools_dir = Path(__file__).parent

    for py_file in tools_dir.glob("*.py"):
        if py_file.name in EXCLUDE_FILES:
            continue

        module_name = f"app.action.tools.{py_file.stem}"

        try:
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
                # 排除条件
                if name in EXCLUDE_FUNCTIONS:
                    continue
                if name.startswith("_"):
                    continue
                if not inspect.iscoroutinefunction(obj):
                    continue

                tools.append(obj)
                logger.debug(f"发现工具: {name} from {py_file.name}")

        except Exception as e:
            logger.error(f"加载模块 {module_name} 失败: {e}")

    return tools


def get_all_tools() -> List[Callable]:
    """获取所有自动发现的工具"""
    return discover_tools()


# 为了保持向后兼容，手动导出的工具列表可以通过自动发现获得
__all__ = [f.__name__ for f in discover_tools()]