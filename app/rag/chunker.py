"""
合约风控审查 Agent 系统 — 法律文本语义分块器.

基于句子边界进行语义分块，保留文档结构（标题、条款编号），
为每个 chunk 附加元数据（出处、法条编号、生效日期）。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    """文档分块，包含文本内容和元数据."""

    text: str
    index: int
    source: str = ""
    law_category: str = ""
    article_number: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkerConfig:
    """分块器配置."""

    chunk_size: int = 512
    chunk_overlap: int = 64
    separators: List[str] = field(default_factory=lambda: [
        "\n\n", "\n", "。", "；", "；",
    ])

    # 最小 chunk 长度 — 短于此值的片段不单独成块
    min_chunk_length: int = 50


class SemanticChunker:
    """语义分块器：基于句子边界 + 重叠窗口对法律文本切分."""

    def __init__(self, config: Optional[ChunkerConfig] = None) -> None:
        self.config = config or ChunkerConfig()

    def chunk(self, text: str, source: str = "", category: str = "") -> List[Chunk]:
        """
        将法律文本分割为语义块.

        Args:
            text: 输入法律文本.
            source: 文本来源（如 "民法典.pdf"）.
            category: 法律类别（如 "民事-合同编"）.

        Returns:
            Chunk 列表，每个包含文本和元数据.
        """
        # Step 1: 按句子/段落分割
        sentences = self._split_sentences(text)

        # Step 2: 根据 chunk_size 合并句子，保留 overlap
        chunks = self._merge_sentences(sentences, source, category)

        # Step 3: 提取法条编号
        for chunk in chunks:
            chunk.article_number = self._extract_article_number(chunk.text)

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """按中文标点和换行分割句子."""
        # 先用双换行分隔段落
        paragraphs = re.split(r"\n\n+", text)
        sentences: List[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # 按句末标点分割
            parts = re.split(r"(?<=[。；；！？\.\!\?])", para)
            for part in parts:
                part = part.strip()
                if part:
                    sentences.append(part)

        return sentences

    def _merge_sentences(
        self, sentences: List[str], source: str, category: str
    ) -> List[Chunk]:
        """将句子合并为指定大小的 chunk，带重叠."""
        chunks: List[Chunk] = []
        current_text = ""
        chunk_index = 0

        for sentence in sentences:
            # 如果加入这个句子会超过 chunk_size
            if len(current_text) + len(sentence) > self.config.chunk_size and len(current_text) >= self.config.min_chunk_length:
                chunks.append(Chunk(
                    text=current_text.strip(),
                    index=chunk_index,
                    source=source,
                    law_category=category,
                ))
                chunk_index += 1
                # 重叠：保留最后 overlap 个字符
                if self.config.chunk_overlap > 0 and len(current_text) > self.config.chunk_overlap:
                    overlap_text = current_text[-self.config.chunk_overlap:]
                    # 从下一个句子边界开始
                    current_text = overlap_text + sentence
                else:
                    current_text = sentence
            else:
                if current_text:
                    current_text += sentence
                else:
                    current_text = sentence

        # 最后一个 chunk
        if current_text.strip() and len(current_text.strip()) >= self.config.min_chunk_length:
            chunks.append(Chunk(
                text=current_text.strip(),
                index=chunk_index,
                source=source,
                law_category=category,
            ))

        return chunks

    def _extract_article_number(self, text: str) -> str:
        """从文本中提取法条编号（如 '第585条'）."""
        patterns = [
            r"第[一二三四五六七八九十百千\d]+条",
            r"第[一二三四五六七八九十百千\d]+款",
            r"第[一二三四五六七八九十百千\d]+项",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        return ""


def chunk_document(
    text: str,
    source: str = "",
    category: str = "",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> List[Chunk]:
    """
    便捷函数：对法律文本进行分块.

    Args:
        text: 输入文本.
        source: 来源标识.
        category: 法律类别.
        chunk_size: 块大小（字符数）.
        chunk_overlap: 重叠大小（字符数）.

    Returns:
        Chunk 列表.
    """
    config = ChunkerConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunker = SemanticChunker(config)
    return chunker.chunk(text, source=source, category=category)
