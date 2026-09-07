"""
合约风控审查 Agent 系统 — 通用 API 响应格式.
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应包装.

    Fields:
        code: 业务状态码，0 表示成功.
        message: 状态描述.
        data: 响应数据.
    """

    code: int = 0
    message: str = "success"
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> "APIResponse":
        """快速构建成功响应."""
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, message: str, code: int = 1) -> "APIResponse":
        """快速构建错误响应."""
        return cls(code=code, message=message, data=None)
