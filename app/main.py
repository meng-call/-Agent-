"""
合约风控审查 Agent 系统 — FastAPI 应用入口.

创建 FastAPI 实例，注册中间件和路由。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import Settings, load_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动时加载配置，关闭时清理资源."""
    settings = load_settings()
    app.state.settings = settings
    yield
    # 关闭数据库连接池
    try:
        from app.db.session import dispose_engine
        await dispose_engine()
    except Exception:
        pass


SCALAR_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>合约风控审查 Agent 系统 - API 文档</title>
  <style>body {{ margin: 0; padding: 0; }}</style>
</head>
<body>
  <script id="api-reference" data-url="{openapi_url}"></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  <script>
    const config = {{
      theme: "default",
      hideDownloadButton: true,
      hideTestRequestButton: false,
      defaultHttpClient: {{ targetKey: "python", clientKey: "requests" }},
      metaData: {{
        title: "合约风控审查 Agent 系统",
        description: "AI-powered contract risk control review",
      }},
    }}
    document.getElementById("api-reference").dataset.configuration = JSON.stringify(config)
  </script>
</body>
</html>"""


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例."""
    app = FastAPI(
        title="合约风控审查 Agent 系统",
        description="AI-powered contract risk control review with multi-agent workflow",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,          # 停用默认 Swagger
        redoc_url=None,         # 停用 ReDoc
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 中文 API 文档（Scalar）
    @app.get("/docs", include_in_schema=False)
    async def scalar_docs(request: Request) -> HTMLResponse:
        openapi_url = str(request.url_for("openapi"))
        return HTMLResponse(SCALAR_HTML.format(openapi_url=openapi_url))

    # 前端首页
    @app.get("/", include_in_schema=False)
    async def frontend() -> HTMLResponse:
        frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
        return HTMLResponse(frontend_path.read_text(encoding="utf-8"))

    # 注册业务路由
    from app.api.routes import health_router, review_router

    app.include_router(health_router)
    app.include_router(review_router)

    return app


app = create_app()
