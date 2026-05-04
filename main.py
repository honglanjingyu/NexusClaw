#!/usr/bin/env python
"""
Agent 系统主入口 - 日志输出到文件
"""

import asyncio
import sys
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent))

# 屏蔽 Pydantic 警告
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from loguru import logger

# ============================================================
# 日志配置：只输出到文件，控制台只显示用户交互
# ============================================================

# 创建日志目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 移除所有默认处理器
logger.remove()

# 只添加文件处理器，不输出到控制台
logger.add(
    LOG_DIR / "agent_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
    level="DEBUG",
    encoding="utf-8"
)

# 可选：同时保留一个单独的详细日志文件用于调试
logger.add(
    LOG_DIR / "debug_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    encoding="utf-8"
)


# 控制台输出函数（用于用户交互）
def cout(*args, **kwargs):
    """纯用户交互输出，不加任何颜色/格式控制"""
    kwargs.setdefault('flush', True)
    print(*args, **kwargs)


# 可选：用一个简单的控制台日志记录关键信息（如果需要的话）
# 但建议全部输出到文件，保持控制台干净

# ============================================================
# 会话管理
# ============================================================

class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, dict] = {}

    def get_or_create(self, session_id: str = None, user_name: str = "user") -> str:
        if session_id and session_id in self._sessions:
            return session_id
        new_session_id = session_id or str(uuid.uuid4())[:8]
        self._sessions[new_session_id] = {
            "session_id": new_session_id,
            "created_at": datetime.now(),
            "user_name": user_name
        }
        return new_session_id

    def get_all(self) -> List[str]:
        return list(self._sessions.keys())


# ============================================================
# Agent 核心类
# ============================================================

class Agent:
    def __init__(self):
        self._initialized = False
        self._brain_manager = None
        self._action_manager = None
        self._memory_manager = None
        self._perception_manager = None
        self._session_manager = SessionManager()
        self._current_session_id = None

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        # 日志只写文件，不干扰控制台
        logger.info("=" * 50)
        logger.info("正在初始化 Agent 系统...")
        logger.info("=" * 50)

        try:
            from app.action import get_action_manager
            self._action_manager = get_action_manager()
            self._action_manager.register_builtin_tools()
            logger.info(f"行动模块初始化完成，工具数: {len(self._action_manager.list_tools())}")

            from app.brain import get_brain_manager
            self._brain_manager = get_brain_manager()
            logger.info("大脑模块初始化完成")

            from app.memory import get_memory_manager
            self._memory_manager = get_memory_manager()
            logger.info("记忆模块初始化完成")

            from app.perception import PerceptionManager
            vector_store = None
            if self._memory_manager and self._memory_manager.long_term.vector_store:
                vector_store = self._memory_manager.long_term.vector_store
            self._perception_manager = PerceptionManager(vector_store_manager=vector_store)
            logger.info("感知模块初始化完成")

            self._current_session_id = self._session_manager.get_or_create()

            if self._memory_manager:
                self._memory_manager.set_session(self._current_session_id)

            self._initialized = True

            logger.info("=" * 50)
            logger.info("✅ Agent 系统初始化完成！")
            logger.info(f"   会话ID: {self._current_session_id}")
            logger.info(f"   可用工具: {len(self._action_manager.list_tools())} 个")
            logger.info("=" * 50)

            return True

        except Exception as e:
            logger.error(f"Agent 初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def chat(self, user_input: str) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "response": "系统正在初始化，请稍后再试..."}

        if self._memory_manager:
            self._memory_manager.set_session(self._current_session_id)

        start_time = datetime.now()

        try:
            perception_result = await self._perception_manager.perceive(
                input_text=user_input,
                session_id=self._current_session_id,
                include_long_term=True,
                top_k=5
            )

            available_tools = []
            for tool_name in self._action_manager.list_tools():
                available_tools.append({
                    "name": tool_name,
                    "description": self._get_tool_description(tool_name)
                })

            brain_response = await self._brain_manager.think(
                user_input=user_input,
                session_id=self._current_session_id,
                perception_context=perception_result.to_dict(),
                available_tools=available_tools
            )

            if brain_response.answer:
                if self._memory_manager:
                    self._memory_manager.add_user_message(user_input)
                    self._memory_manager.add_assistant_message(brain_response.answer)
                    logger.info(f"对话已保存: user='{user_input[:50]}...', assistant='{brain_response.answer[:50]}...'")

                if self._perception_manager:
                    self._perception_manager.add_conversation_to_memory(user_input, brain_response.answer)

            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            return {
                "success": True,
                "response": brain_response.answer,
                "steps_executed": len(brain_response.execution_history),
                "elapsed_ms": elapsed_ms
            }

        except Exception as e:
            logger.error(f"处理失败: {e}")
            return {"success": False, "response": f"处理失败: {str(e)}"}

    def _get_tool_description(self, tool_name: str) -> str:
        descriptions = {
            "get_current_time": "获取当前真实时间",
            "search_knowledge": "从知识库搜索信息",
            "search_knowledge_with_filter": "按分类搜索知识",
            "get_knowledge_stats": "获取知识库统计信息",
            "add_to_knowledge": "添加知识到知识库",
            "web_search": "网络搜索，参数 query: 搜索词",
            "web_search_advanced": "高级网络搜索"
        }
        return descriptions.get(tool_name, f"工具: {tool_name}")

    async def add_knowledge(self, content: str, category: str = "general") -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="add_to_knowledge",
                tool_input={"content": content, "category": category, "source": "user"},
                session_id=self._current_session_id
            )
            success = "✅" in result or "成功" in result
            return {"success": success, "message": result}
        except Exception as e:
            return {"success": False, "message": f"添加失败: {str(e)}"}

    async def search_knowledge(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="search_knowledge",
                tool_input={"query": query, "top_k": top_k},
                session_id=self._current_session_id
            )
            return {"success": True, "message": result}
        except Exception as e:
            return {"success": False, "message": f"搜索失败: {str(e)}"}

    async def get_knowledge_stats(self) -> Dict[str, Any]:
        if not self._initialized:
            return {"success": False, "message": "Agent 未初始化"}
        try:
            result = await self._action_manager.execute_tool_call(
                tool_name="get_knowledge_stats",
                tool_input={},
                session_id=self._current_session_id
            )
            return {"success": True, "message": result}
        except Exception as e:
            return {"success": False, "message": f"获取失败: {str(e)}"}

    def list_tools(self) -> List[str]:
        if self._action_manager:
            return self._action_manager.list_tools()
        return []

    def clear_session(self):
        if self._perception_manager:
            self._perception_manager.clear_session(self._current_session_id)
        if self._memory_manager:
            self._memory_manager.clear_session()
        logger.info(f"会话已清空: {self._current_session_id}")

    def new_session(self):
        self._current_session_id = self._session_manager.get_or_create()
        if self._memory_manager:
            self._memory_manager.set_session(self._current_session_id)
        logger.info(f"新会话已创建: {self._current_session_id}")

    def get_session_id(self) -> str:
        return self._current_session_id

    def get_status(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "tools": self.list_tools(),
            "session_id": self._current_session_id,
            "active_sessions": len(self._session_manager.get_all())
        }

    async def get_memory_stats(self) -> Dict[str, Any]:
        if self._memory_manager:
            stats = self._memory_manager.get_stats()
            return {
                "short_term": stats.short_term_count,
                "working": stats.working_count,
                "long_term": stats.long_term_count,
                "total": stats.total_count
            }
        return {}


# ============================================================
# 命令行界面
# ============================================================

class AgentCLI:
    def __init__(self):
        self.agent = Agent()
        self.running = True

        self.commands = {
            "/help": self.cmd_help, "/h": self.cmd_help,
            "/exit": self.cmd_exit, "/quit": self.cmd_exit, "/q": self.cmd_exit,
            "/clear": self.cmd_clear, "/c": self.cmd_clear,
            "/new": self.cmd_new_session,
            "/tools": self.cmd_tools,
            "/status": self.cmd_status,
            "/stats": self.cmd_stats,
            "/kb": self.cmd_kb_stats,
            "/search": self.cmd_search,
            "/add": self.cmd_add_knowledge,
        }

    def print_banner(self):
        banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🤖 AI Agent 系统                                           ║
║                                                              ║
║   集成模块: 感知模块 | 记忆模块 | 大脑模块 | 行动模块         ║
║                                                              ║
║   命令: /help, /clear, /new, /tools, /kb, /search, /exit     ║
║                                                              ║
║   日志文件: logs/agent_YYYY-MM-DD.log                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
        cout(banner)

    async def cmd_help(self, args: str = ""):
        cout("""
📖 可用命令:
   /help, /h     - 显示帮助
   /clear, /c    - 清空当前会话
   /new          - 创建新会话
   /tools        - 列出可用工具
   /kb           - 查看知识库状态
   /search <词>  - 搜索知识库
   /add <内容>   - 添加知识
   /status       - 系统状态
   /stats        - 记忆统计
   /exit, /q     - 退出程序
""")

    async def cmd_exit(self, args: str = ""):
        cout("\n👋 再见！")
        self.running = False

    async def cmd_clear(self, args: str = ""):
        self.agent.clear_session()
        cout("✅ 会话已清空")

    async def cmd_new_session(self, args: str = ""):
        self.agent.new_session()
        cout(f"✅ 新会话: {self.agent.get_session_id()}")

    async def cmd_tools(self, args: str = ""):
        tools = self.agent.list_tools()
        if tools:
            cout(f"\n🔧 可用工具 ({len(tools)} 个):")
            for tool in tools:
                cout(f"   • {tool}")
        else:
            cout("\n⚠️ 暂无工具")

    async def cmd_status(self, args: str = ""):
        status = self.agent.get_status()
        cout(f"\n📊 系统状态:")
        cout(f"   初始化: {'✅' if status['initialized'] else '❌'}")
        cout(f"   会话ID: {status['session_id']}")
        cout(f"   工具数: {len(status['tools'])}")

    async def cmd_stats(self, args: str = ""):
        stats = await self.agent.get_memory_stats()
        if stats:
            cout(f"\n📊 记忆统计:")
            cout(f"   短期记忆: {stats['short_term']} 条")
            cout(f"   工作记忆: {stats['working']} 条")
            cout(f"   长期记忆: {stats['long_term']} 条")
            cout(f"   总计: {stats['total']} 条")
        else:
            cout("\n⚠️ 无法获取统计")

    async def cmd_kb_stats(self, args: str = ""):
        result = await self.agent.get_knowledge_stats()
        if result["success"]:
            first_line = result['message'].split('\n')[0] if '\n' in result['message'] else result['message']
            cout(f"\n📚 {first_line}")
        else:
            cout(f"\n❌ {result['message']}")

    async def cmd_search(self, args: str = ""):
        if not args.strip():
            cout("⚠️ 请提供搜索词")
            return

        cout(f"\n🔍 搜索: {args}")
        result = await self.agent.search_knowledge(args.strip(), top_k=5)

        if result["success"]:
            cout(f"\n{result['message']}")
        else:
            cout(f"\n❌ {result['message']}")

    async def cmd_add_knowledge(self, args: str = ""):
        if not args.strip():
            cout("⚠️ 请提供知识内容")
            return

        cout(f"\n📝 添加知识...")
        result = await self.agent.add_knowledge(args.strip())

        if result["success"]:
            cout(f"✅ {result['message']}")
        else:
            cout(f"❌ {result['message']}")

    async def chat_with_agent(self, user_input: str):
        result = await self.agent.chat(user_input)

        if result["success"]:
            cout(f"\n🤖 {result['response']}")
        else:
            cout(f"\n❌ {result['response']}")

    async def run(self):
        self.print_banner()

        cout("\n正在初始化...")
        success = await self.agent.initialize()

        if not success:
            cout("\n❌ 初始化失败，请检查日志文件 logs/agent_*.log")
            return

        cout("\n" + "=" * 60)
        cout("💬 开始对话 (输入 /help 查看帮助)")
        cout("=" * 60)

        while self.running:
            try:
                session_short = self.agent.get_session_id()[:6]
                user_input = input(f"\n[{session_short}] > ").strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    parts = user_input.split(maxsplit=1)
                    cmd = parts[0].lower()
                    args = parts[1] if len(parts) > 1 else ""

                    if cmd in self.commands:
                        await self.commands[cmd](args)
                    else:
                        cout(f"❌ 未知命令: {cmd}")
                else:
                    await self.chat_with_agent(user_input)

            except KeyboardInterrupt:
                cout("\n\n👋 再见！")
                break
            except EOFError:
                break
            except Exception as e:
                cout(f"\n❌ 错误: {e}")


async def main():
    cli = AgentCLI()
    await cli.run()
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        cout("\n\n👋 再见！")
        sys.exit(0)