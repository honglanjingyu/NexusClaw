#!/usr/bin/env python
"""FastAPI 服务启动入口 - 简化版"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("正在初始化 Agent 系统...")

    from app.api.dependencies import get_agent

    try:
        agent = await get_agent()
        logger.info("Agent 系统初始化完成")
    except Exception as e:
        logger.error(f"Agent 初始化失败: {e}")

    yield

    logger.info("正在关闭 Agent 系统...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="Agent API",
        description="AI Agent 系统 API 接口",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    from app.api.routes import router
    app.include_router(router)

    # 静态文件服务 - 将 web 目录挂载到根路径
    web_dir = Path(__file__).parent / "web"

    if web_dir.exists():
        # 先挂载静态文件（这样 /style.css 等可以直接访问）
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        # 然后添加根路径的 HTML 响应
        from fastapi.responses import FileResponse

        @app.get("/")
        async def serve_index():
            """提供前端页面"""
            index_path = web_dir / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return {"message": "Web frontend not found"}

        logger.info(f"Web 前端已加载: {web_dir}")
    else:
        @app.get("/")
        async def root():
            return {
                "name": "Agent API",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/api/v1/health"
            }

        logger.warning(f"Web 前端目录不存在: {web_dir}")

    return app


def main():
    """启动服务"""
    import argparse

    parser = argparse.ArgumentParser(description="启动 Agent API 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="热重载模式")

    args = parser.parse_args()

    app = create_app()

    print(f"\n{'=' * 50}")
    print(f"🚀 Agent API 服务已启动")
    print(f"{'=' * 50}")
    print(f"📍 地址: http://{args.host}:{args.port}")
    print(f"📖 API 文档: http://{args.host}:{args.port}/docs")
    print(f"🎨 Web 界面: http://{args.host}:{args.port}/")
    print(f"{'=' * 50}\n")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()