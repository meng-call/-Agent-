"""
合约风控审查 Agent 系统 — API 路由模块.
"""

from app.api.routes.health import router as health_router
from app.api.routes.review import router as review_router

__all__ = [
    "health_router",
    "review_router",
]
