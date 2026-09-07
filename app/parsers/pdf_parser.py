"""
合约风控审查 Agent 系统 — PDF 文档解析器.

基于 pdfplumber 提取 PDF 中的文本内容。
"""

import logging
from pathlib import Path

from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF 文档解析器，提取所有页面纯文本."""

    async def parse(self, file_path: Path) -> str:
        """解析 PDF 文件，返回提取的纯文本.

        Args:
            file_path: PDF 文件路径.

        Returns:
            提取的纯文本内容，页面间以双换行分隔.

        Raises:
            FileNotFoundError: 文件不存在.
            ValueError: 文件不是 PDF 格式.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in (".pdf",):
            raise ValueError(f"不支持的文件格式: {suffix}，需要 .pdf")

        try:
            import pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber 未安装，请执行: pip install pdfplumber>=0.11.0"
            )

        text_parts: list[str] = []
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                total = len(pdf.pages)
                logger.info(f"PDFParser: 共 {total} 页 → {file_path.name}")

                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        text_parts.append(text.strip())

                extracted = "\n\n".join(text_parts)
                logger.info(
                    f"PDFParser: 提取完成, {len(extracted)} 字符, "
                    f"{len(text_parts)}/{total} 页有文本"
                )
                return extracted

        except Exception as e:
            logger.error(f"PDFParser: 解析失败 → {file_path.name}: {e}")
            raise RuntimeError(f"PDF 解析失败: {e}") from e
