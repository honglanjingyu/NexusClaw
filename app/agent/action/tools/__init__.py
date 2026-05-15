# app/agent/action/tools/__init__.py
"""内置行动工具 - 自动发现和注册到 MCP"""

import importlib
import inspect
from pathlib import Path
from typing import List, Callable, Any
from loguru import logger

EXCLUDE_FILES = {"__init__.py", "__pycache__"}
EXCLUDE_FUNCTIONS = {"get_long_term_memory"}


def discover_tools() -> List[Callable]:
    """自动发现 tools 目录下的所有工具函数"""
    tools = []
    tools_dir = Path(__file__).parent  # 当前目录

    for py_file in tools_dir.glob("*.py"):
        if py_file.name in EXCLUDE_FILES:
            continue

        # 修复: 正确的模块路径是 app.agent.action.tools.xxx
        module_name = f"app.agent.action.tools.{py_file.stem}"

        try:
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
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