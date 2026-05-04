#!/usr/bin/env python
"""修复时间工具调用 - 直接测试"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def demo_time_tool():
    """直接测试时间工具"""
    print("=" * 50)
    print("测试时间工具直接调用")
    print("=" * 50)

    from app.action import get_action_manager

    manager = get_action_manager()
    manager.register_builtin_tools()

    print(f"已注册工具: {manager.list_tools()}")

    # 直接调用工具
    print("\n1. 直接调用 get_current_time:")
    result = await manager.execute_tool_call(
        tool_name="get_current_time",
        tool_input={},
        session_id="test"
    )
    print(f"   结果: {result}")

    # 测试带时区参数
    print("\n2. 带时区参数调用:")
    result = await manager.execute_tool_call(
        tool_name="get_current_time",
        tool_input={"timezone": "Asia/Shanghai"},
        session_id="test"
    )
    print(f"   结果: {result}")

    return result


async def demo_brain_time():
    """测试大脑模块的时间查询"""
    print("\n" + "=" * 50)
    print("测试大脑模块时间查询")
    print("=" * 50)

    from app.brain import get_brain_manager
    from app.action import get_action_manager

    # 确保工具已注册
    action_manager = get_action_manager()
    action_manager.register_builtin_tools()

    brain = get_brain_manager()

    # 注册工具到大脑
    from app.action.tools import get_current_time
    brain.register_tool(get_current_time)

    print(f"大脑注册的工具: {brain.list_tools()}")

    # 测试查询
    print("\n查询: 现在几点了？")

    response = await brain.think(
        user_input="现在几点了？请调用工具获取真实时间",
        session_id="test-brain",
        perception_context={},
        available_tools=[
            {"name": "get_current_time", "description": "获取当前真实时间，返回格式如 2026-05-04 18:30:00"}
        ]
    )

    print(f"\n回答: {response.answer}")

    # 打印执行历史
    print("\n执行历史:")
    for step in response.execution_history:
        print(f"  - 步骤: {step.step}")
        print(f"    动作类型: {step.action.type.value}")
        if step.action.type.value == "tool_call":
            print(f"    工具名: {step.action.tool_name}")
            print(f"    工具参数: {step.action.tool_input}")
        print(f"    结果: {step.result}")
        print()


async def main():
    # 测试1: 直接调用
    time_result = await demo_time_tool()

    # 测试2: 通过大脑调用
    await demo_brain_time()


if __name__ == "__main__":
    asyncio.run(main())