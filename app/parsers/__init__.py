"""
合约风控审查 Agent 系统 — 文档解析器模块.

解析器优先级: Docling → pdfplumber / python-docx (fallback).
"""

from app.parsers.base import BaseParser
from app.parsers.docx_parser import DocxParser
from app.parsers.docling_parser import DoclingParser
from app.parsers.pdf_parser import PDFParser

__all__ = [
    "BaseParser",
    "DoclingParser",
    "DocxParser",
    "PDFParser",
]
