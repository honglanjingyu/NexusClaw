#!/usr/bin/env python
"""测试网络搜索工具"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def demo_search():
    print("=" * 50)
    print("测试网络搜索工具")
    print("=" * 50)

    from app.action import get_action_manager

    manager = get_action_manager()
    manager.register_builtin_tools()

    print(f"\n已注册工具: {manager.list_tools()}")

    # 测试1: 普通网页搜索
    print("\n1. 网页搜索 'Python 异步编程':")
    result = await manager.execute_tool_call(
        tool_name="web_search",
        tool_input={"query": "Python 异步编程", "num_results": 3}
    )
    print(result)

    # 测试2: 新闻搜索
    print("\n2. 新闻搜索 '人工智能':")
    result = await manager.execute_tool_call(
        tool_name="web_search",
        tool_input={"query": "人工智能", "num_results": 2, "search_type": "news"}
    )
    print(result)

    # 测试3: 高级搜索
    print("\n3. 高级搜索 (GitHub 站点限制):")
    result = await manager.execute_tool_call(
        tool_name="web_search_advanced",
        tool_input={"query": "langchain", "site": "github.com", "num_results": 2}
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(demo_search())