"""
合约风控审查 Agent 系统 — BM25 关键词检索引擎.

用于与向量语义搜索互补：法律文本中的精确术语匹配
（如"违约金""不可抗力""善意第三人"）是向量搜索的薄弱环节，
BM25 关键词匹配天然适合这种场景。

与向量搜索结果通过 RRF（Reciprocal Rank Fusion）融合。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BM25Searcher:
    """BM25 关键词搜索引擎.

    使用 jieba 分词 + rank_bm25 实现中文法律文本的 BM25 检索。

    Usage::

        searcher = BM25Searcher()
        searcher.index(corpus_texts, corpus_metadata)
        results = searcher.search("违约金超过法定上限", top_k=10)
        # → [(doc_id, score, metadata), ...]
    """

    def __init__(self) -> None:
        self._corpus: List[str] = []
        self._metadata: List[Dict[str, Any]] = []
        self._bm25 = None
        self._indexed = False

    def index(
        self,
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """构建 BM25 索引.

        Args:
            texts: 文档文本列表.
            metadata: 对应的元数据列表，长度须与 texts 一致.
        """
        if not texts:
            logger.warning("BM25: 空语料，跳过索引")
            return

        try:
            import jieba
        except ImportError:
            raise ImportError("jieba 未安装，请执行: pip install jieba")

        from rank_bm25 import BM25Okapi

        # jieba 分词（精确模式）
        tokenized = [list(jieba.cut(text)) for text in texts]

        self._corpus = list(texts)
        self._metadata = metadata or [{}] * len(texts)
        self._bm25 = BM25Okapi(tokenized)
        self._indexed = True

        logger.info(f"BM25 索引完成: {len(tokenized)} 文档")

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Tuple[int, float, Dict[str, Any]]]:
        """BM25 关键词搜索.

        Args:
            query: 查询文本.
            top_k: 返回结果数.

        Returns:
            [(doc_index, bm25_score, metadata), ...] 按分数降序排列.
        """
        if not self._indexed or self._bm25 is None:
            return []

        try:
            import jieba
        except ImportError:
            return []

        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)

        # 取 top_k
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results: List[Tuple[int, float, Dict[str, Any]]] = []
        for doc_id, score in indexed_scores[:top_k]:
            if score > 0:  # 只返回有匹配的结果
                meta = self._metadata[doc_id] if doc_id < len(self._metadata) else {}
                results.append((doc_id, float(score), meta))

        return results

    def is_ready(self) -> bool:
        """索引是否已构建."""
        return self._indexed


def reciprocal_rank_fusion(
    vector_results: List[Tuple[int, float]],
    bm25_results: List[Tuple[int, float]],
    k: int = 60,
) -> List[Tuple[int, float]]:
    """通过 RRF 融合向量搜索和 BM25 搜索结果.

    公式: RRF(d) = Σ(1 / (k + rank_i(d)))

    其中 k 为常数（默认 60，行业标准），rank_i(d) 为文档 d 在
    第 i 个排序列表中的排名（从 1 开始）。

    融合后按 RRF 分数降序排列。

    Args:
        vector_results: [(doc_id, similarity_score), ...] 已排序.
        bm25_results: [(doc_id, bm25_score), ...] 已排序.
        k: RRF 平滑常数.

    Returns:
        [(doc_id, rrf_score), ...] 按 RRF 分数降序排列.
    """
    rrf_scores: Dict[int, float] = {}

    # 向量搜索结果贡献
    for rank, (doc_id, _score) in enumerate(vector_results, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    # BM25 结果贡献
    for rank, (doc_id, _score) in enumerate(bm25_results, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    # 按 RRF 分数降序排列
    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return fused
