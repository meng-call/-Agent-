"""
合约风控审查 Agent 系统 — 文档解析器抽象基类.

后续阶段实现 pdf_parser, docx_parser 具体解析器。
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    """文档解析器抽象基类，所有解析器需实现 parse() 方法."""

    @abstractmethod
    async def parse(self, file_path: Path) -> str:
        """解析文档，返回纯文本内容."""
        ...
