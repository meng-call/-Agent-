"""
合约风控审查 Agent 系统 — 健康检查端点.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """服务健康检查，返回运行状态."""
    return {"status": "ok"}
