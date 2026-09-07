"""
合约风控审查 Agent 系统 — API 公共依赖注入.

提供路由层可复用的 FastAPI Depends 函数.
"""

from functools import lru_cache
from typing import Optional

from fastapi import Request
from langgraph.graph import StateGraph

from app.core.config import Settings, load_settings


@lru_cache()
def _cached_settings() -> Settings:
    """缓存配置单例（进程级）."""
    return load_settings()


def get_settings(request: Request) -> Settings:
    """FastAPI 依赖：获取应用配置.

    优先从 request.app.state.settings 读取（启动时由 lifespan 注入），
    如果不可用则回退到进程级缓存.

    Usage::

        @router.post("/review")
        async def review(settings: Settings = Depends(get_settings)):
            ...
    """
    try:
        app_settings = getattr(request.app.state, "settings", None)
        if app_settings is not None:
            return app_settings
    except Exception:
        pass
    return _cached_settings()


# ── 工作流实例缓存 ──────────────────────────────────────────────────

_workflow: Optional[StateGraph] = None


def get_workflow() -> StateGraph:
    """FastAPI 依赖：获取审查工作流实例（懒加载 + 进程级缓存）.

    首次调用时自动初始化 LLM 客户端、Embedding 模型、
    Milvus 连接和检索器，后续调用直接返回缓存实例.

    Usage::

        @router.post("/review")
        async def review(workflow: StateGraph = Depends(get_workflow)):
            result = workflow.invoke({"contract_text": "..."})
    """
    global _workflow
    if _workflow is not None:
        return _workflow

    settings = _cached_settings()
    from app.agents.graph import create_review_workflow
    _workflow = create_review_workflow(settings)
    return _workflow
