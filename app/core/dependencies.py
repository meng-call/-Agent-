"""
合约风控审查 Agent 系统 — 公共依赖注入.

提供跨模块可复用的依赖获取函数.
"""

from app.api.deps import get_settings, get_workflow

__all__ = [
    "get_settings",
    "get_workflow",
]
