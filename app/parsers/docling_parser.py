"""
合约风控审查 Agent 系统 — Docling 文档解析器.

基于 IBM Docling 的统一文档解析，支持 PDF/DOCX/PPTX/HTML 等多种格式，
具备深度学习布局理解、表格结构识别和 Markdown 导出能力。

相比 pdfplumber + python-docx 组合的优势：
- 统一的 API，无需按扩展名分发解析器
- 深度学习表格识别（TableFormer），合同中的价格表/交付清单不再丢结构
- Markdown 输出保留标题/段落/列表层级，LLM 理解更准确
- OCR 回退（扫描版 PDF 也能提取文本）
"""

import logging
from pathlib import Path

from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class DoclingParser(BaseParser):
    """基于 Docling 的统一文档解析器.

    支持 PDF、DOCX、PPTX、HTML、Markdown 等 15+ 格式，
    输出结构化 Markdown 文本。

    Usage::

        parser = DoclingParser()
        text = await parser.parse(Path("contract.pdf"))
        # 返回 Markdown 格式文本，保留标题、表格、段落结构
    """

    def __init__(
        self,
        enable_ocr: bool = False,
        enable_table_structure: bool = True,
        max_file_size: int = 20_971_520,  # 20 MB
        max_num_pages: int = 100,
    ) -> None:
        """
        Args:
            enable_ocr: 是否启用 OCR（扫描版 PDF 需要，会增加处理时间）.
            enable_table_structure: 是否启用表格结构识别.
            max_file_size: 最大文件大小（字节）.
            max_num_pages: 最大页数限制.
        """
        self.enable_ocr = enable_ocr
        self.enable_table_structure = enable_table_structure
        self.max_file_size = max_file_size
        self.max_num_pages = max_num_pages
        self._converter = None

    @property
    def converter(self):
        """懒加载 Docling DocumentConverter."""
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except ImportError:
                raise ImportError(
                    "Docling 未安装，请执行: pip install docling>=2.0.0"
                )
            self._converter = DocumentConverter()
        return self._converter

    async def parse(self, file_path: Path) -> str:
        """解析文档，返回 Markdown 格式文本.

        Args:
            file_path: 文档文件路径.

        Returns:
            Markdown 格式的文档内容.

        Raises:
            FileNotFoundError: 文件不存在.
            RuntimeError: 解析失败.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            from docling.datamodel.base_models import ConversionStatus
        except ImportError:
            raise ImportError("Docling 未安装，请执行: pip install docling>=2.0.0")

        try:
            result = self.converter.convert(
                str(file_path),
                max_file_size=self.max_file_size,
                max_num_pages=self.max_num_pages,
            )

            if result.status == ConversionStatus.SUCCESS:
                markdown = result.document.export_to_markdown()
                logger.info(
                    f"DoclingParser: {file_path.name} → {len(markdown)} 字符 (Markdown)"
                )
                return markdown

            elif result.status == ConversionStatus.PARTIAL_SUCCESS:
                logger.warning(
                    f"DoclingParser: {file_path.name} 部分解析成功, "
                    f"共 {len(result.errors)} 个错误"
                )
                return result.document.export_to_markdown()

            else:
                raise RuntimeError(
                    f"Docling 解析完全失败: "
                    + "; ".join(e.error_message for e in result.errors)
                )

        except Exception as e:
            logger.error(f"DoclingParser: 解析失败 → {file_path.name}: {e}")
            raise RuntimeError(f"Docling 解析失败: {e}") from e

    def is_available(self) -> bool:
        """检查 Docling 是否可用."""
        try:
            import docling  # noqa: F401
            return True
        except ImportError:
            return False
