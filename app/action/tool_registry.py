# app/action/tool_registry.py
"""工具注册表 - 管理所有可用工具"""

from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass
from loguru import logger
import asyncio
import inspect

from .models import ToolInfo


@dataclass
class RegisteredTool:
    """已注册的工具"""
    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    input_schema: Optional[Dict[str, Any]] = None
    is_async: bool = True


class ToolRegistry:
    """
    工具注册表 - 单例模式

    管理所有可用的工具，支持：
    - 注册/注销工具
    - 根据名称获取工具
    - 列出所有工具
    - 执行工具调用
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tools: Dict[str, RegisteredTool] = {}
        self._initialized = True
        logger.info("ToolRegistry 初始化完成")

    def register(
            self,
            name: str,
            description: str,
            handler: Callable[..., Awaitable[Any]],
            input_schema: Optional[Dict[str, Any]] = None,
            is_async: bool = True
    ) -> None:
        """
        注册工具

        Args:
            name: 工具名称
            description: 工具描述
            handler: 工具处理函数
            input_schema: 输入参数 schema
            is_async: 是否异步函数
        """
        if name in self._tools:
            logger.warning(f"工具 '{name}' 已存在，将被覆盖")

        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            handler=handler,
            input_schema=input_schema,
            is_async=is_async
        )
        logger.info(f"注册工具: {name}")

    def register_tool(self, tool: Any) -> None:
        """
        注册工具（支持多种格式）

        支持的格式：
        1. LangChain 风格: 有 name, description, ainvoke 方法
        2. 普通异步函数: 从函数名和文档字符串提取信息
        3. 普通同步函数: 自动包装为异步
        4. 带 @tool 装饰器的函数

        Args:
            tool: 工具对象或函数
        """
        # 检查是否是 LangChain 风格的工具对象
        if hasattr(tool, 'name') and hasattr(tool, 'description') and hasattr(tool, 'ainvoke'):
            self.register(
                name=tool.name,
                description=tool.description,
                handler=tool.ainvoke
            )
        # 检查是否是函数（同步或异步）
        elif callable(tool):
            # 获取函数名
            name = getattr(tool, '__name__', str(tool))

            # 获取描述（从文档字符串或默认值）
            description = tool.__doc__
            if description:
                # 只取第一行作为简短描述
                description = description.strip().split('\n')[0]
            else:
                description = f"工具: {name}"

            # 检查是否是异步函数
            is_async = inspect.iscoroutinefunction(tool)

            if not is_async:
                # 同步函数，包装为异步
                async def async_wrapper(**kwargs):
                    return tool(**kwargs)
                handler = async_wrapper
            else:
                handler = tool

            self.register(
                name=name,
                description=description,
                handler=handler,
                is_async=True
            )
        else:
            raise ValueError(f"无法识别的工具类型: {type(tool)}")

    def register_tools(self, tools: List[Any]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register_tool(tool)

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"注销工具: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[RegisteredTool]:
        """获取工具"""
        return self._tools.get(name)

    def get_tool_info(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        tool = self._tools.get(name)
        if tool:
            return ToolInfo(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                is_async=tool.is_async
            )
        return None

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def list_tools_info(self) -> List[ToolInfo]:
        """列出所有工具信息"""
        return [
            ToolInfo(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                is_async=tool.is_async
            )
            for tool in self._tools.values()
        ]

    def get_tools_description(self) -> str:
        """获取工具描述文本（用于 LLM Prompt）"""
        if not self._tools:
            return "无可用工具"

        lines = []
        for name, tool in self._tools.items():
            lines.append(f"- {name}: {tool.description}")
        return "\n".join(lines)

    async def execute(
            self,
            tool_name: str,
            input_data: Dict[str, Any],
            session_id: str = ""  # 添加 session_id 参数
    ) -> str:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            input_data: 工具参数
            session_id: 会话ID

        Returns:
            str: 工具执行结果
        """
        tool = self._tools.get(tool_name)

        if tool is None:
            error_msg = f"工具 '{tool_name}' 不存在"
            logger.error(error_msg)
            return error_msg

        try:
            logger.info(f"执行工具: {tool_name}, 参数: {input_data}, session_id: {session_id}")

            # 调用工具函数，传递 session_id（如果工具函数支持）
            result = await tool.handler(**input_data, session_id=session_id)

            # 处理不同类型的结果
            if isinstance(result, tuple) and len(result) == 2:
                result = result[0]
            elif hasattr(result, 'content'):
                result = result.content

            logger.info(f"工具 '{tool_name}' 执行成功")
            return str(result)

        except TypeError as e:
            # 如果工具不支持 session_id 参数，尝试不传递
            if "unexpected keyword argument 'session_id'" in str(e):
                logger.warning(f"工具 '{tool_name}' 不支持 session_id 参数，尝试不带参数调用")
                try:
                    result = await tool.handler(**input_data)
                    if isinstance(result, tuple) and len(result) == 2:
                        result = result[0]
                    elif hasattr(result, 'content'):
                        result = result.content
                    return str(result)
                except Exception as e2:
                    error_msg = f"工具 '{tool_name}' 执行失败: {str(e2)}"
                    logger.error(error_msg)
                    return error_msg
            else:
                error_msg = f"工具 '{tool_name}' 执行失败: {str(e)}"
                logger.error(error_msg)
                return error_msg

        except Exception as e:
            error_msg = f"工具 '{tool_name}' 执行失败: {str(e)}"
            logger.error(error_msg)
            return error_msg


# 全局单例
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表单例"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry