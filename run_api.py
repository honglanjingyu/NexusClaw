# run_api.py - 完整修复版（添加认证路由）

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from loguru import logger

# ============================================================
# 日志配置
# ============================================================

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(
    LOG_DIR / "debug_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    encoding="utf-8"
)


def cout(*args, **kwargs):
    kwargs.setdefault('flush', True)
    print(*args, **kwargs)


from app.mcp import get_mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化 Agent 系统...")

    try:
        mcp_manager = get_mcp_manager(use_local=True)

        from app.action.tools import discover_tools
        tools = discover_tools()
        for tool in tools:
            mcp_manager.register_tool(
                name=tool.__name__,
                handler=tool,
                description=tool.__doc__ or f"Tool: {tool.__name__}"
            )
        logger.info(f"MCP 已注册 {len(tools)} 个工具")
    except Exception as e:
        logger.error(f"MCP 初始化失败: {e}")

    from app.api.dependencies import get_agent

    try:
        agent = await get_agent()
        logger.info("Agent 系统初始化完成")
    except Exception as e:
        logger.error(f"Agent 初始化失败: {e}")

    yield

    logger.info("正在关闭 Agent 系统...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent API",
        description="AI Agent 系统 API 接口 (MCP 协议)",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册业务路由
    from app.api.routes import router
    app.include_router(router)

    # 注册认证路由
    from app.api.auth_routes import router as auth_router
    app.include_router(auth_router)

    @app.get("/mcp/health")
    async def mcp_health():
        from app.mcp import get_mcp_manager
        mcp_manager = get_mcp_manager(use_local=True)
        return {
            "status": "ok",
            "tools": list(mcp_manager._tools.keys()),
            "tool_count": len(mcp_manager._tools)
        }

    # ========== 静态文件服务 ==========
    web_dir = Path(__file__).parent / "web"

    if web_dir.exists():
        # 检查子目录是否存在，如果不存在则创建
        css_dir = web_dir / "css"
        js_dir = web_dir / "js"

        if not css_dir.exists():
            css_dir.mkdir(parents=True)
            logger.warning(f"创建 CSS 目录: {css_dir}")

        if not js_dir.exists():
            js_dir.mkdir(parents=True)
            logger.warning(f"创建 JS 目录: {js_dir}")

        # 挂载静态文件目录
        if css_dir.exists():
            app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
            logger.info(f"CSS 目录已挂载: {css_dir}")

        if js_dir.exists():
            app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
            logger.info(f"JS 目录已挂载: {js_dir}")

        # 挂载根静态目录
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        async def serve_index():
            # 检查用户是否已登录
            index_path = web_dir / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return {"message": "index.html not found"}

        @app.get("/login.html")
        async def serve_login():
            login_path = web_dir / "login.html"
            if login_path.exists():
                return FileResponse(str(login_path))
            return {"message": "login.html not found"}

        # 处理其他 HTML 页面
        @app.get("/{filename}.html")
        async def serve_html(filename: str):
            file_path = web_dir / f"{filename}.html"
            if file_path.exists():
                return FileResponse(str(file_path))
            return {"message": f"{filename}.html not found"}

        logger.info(f"Web 前端已加载: {web_dir}")
        logger.info(f"  访问地址: http://localhost:8002/")
        logger.info(f"  登录地址: http://localhost:8002/login.html")
        logger.info(f"  CSS 路径: /css/")
        logger.info(f"  JS 路径: /js/")
    else:
        logger.warning(f"Web 前端目录不存在: {web_dir}")

        @app.get("/")
        async def root():
            return {
                "name": "Agent API (MCP)",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/api/v1/health",
                "mcp_health": "/mcp/health",
                "auth": {
                    "register": "/api/auth/register",
                    "login": "/api/auth/login",
                    "verify": "/api/auth/verify"
                }
            }

    return app


def main():
    import argparse

    parser = argparse.ArgumentParser(description="启动 Agent API 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8002, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="热重载模式")
    parser.add_argument("--mcp-port", type=int, default=8003, help="MCP 服务器端口")
    parser.add_argument("--mcp-mode", choices=["stdio", "http", "embedded"],
                        default="embedded", help="MCP 运行模式")
    parser.add_argument("--console-log", action="store_true", help="同时输出日志到控制台")

    args = parser.parse_args()

    if args.console_log:
        logger.add(
            sys.stdout,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="INFO",
            colorize=True
        )

    if args.mcp_mode == "http":
        cout(f"\n⚠️  请单独运行: python run_mcp_server.py --mode http --port {args.mcp_port}")
    elif args.mcp_mode == "stdio":
        cout(f"\n⚠️  请单独运行: python run_mcp_server.py --mode stdio")

    app = create_app()

    cout(f"\n{'=' * 50}")
    cout(f"🚀 Agent API 服务已启动 (MCP 模式)")
    cout(f"{'=' * 50}")
    cout(f"📍 地址: http://{args.host}:{args.port}")
    cout(f"📖 API 文档: http://{args.host}:{args.port}/docs")
    cout(f"🎨 Web 界面: http://{args.host}:{args.port}/")
    cout(f"🔐 登录页面: http://{args.host}:{args.port}/login.html")
    cout(f"🔧 MCP 状态: http://{args.host}:{args.port}/mcp/health")
    cout(f"🛠️  MCP 模式: {args.mcp_mode}")
    cout(f"📁 日志目录: logs/")
    cout(f"{'=' * 50}\n")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()