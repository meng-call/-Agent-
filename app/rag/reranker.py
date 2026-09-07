"""
合约风控审查 Agent 系统 — Cross-encoder 重排序器.

在法律检索的二阶段管道中作为精排步骤：
1. 初检（bi-encoder）：向量 + BM25 → 候选集（高召回）
2. 精排（cross-encoder）：Reranker 重打分（高精度）

Cross-encoder 同时编码 query 和 document，捕捉细粒度语义交互，
对法律条文的精确匹配场景（如"违约金上限"vs"损害赔偿范围"）
区分能力远超 bi-encoder 的独立编码。
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder 重排序器.

    基于 FlagEmbedding 的 bge-reranker 系列模型，
    对检索候选集重新打分排序。

    Usage::

        reranker = Reranker()
        scored = reranker.rerank(
            query="违约金超过法定上限怎么办",
            documents=["第585条：违约金过高可请求减少...", "第577条：违约责任..."],
        )
        # → [("第585条...", 0.95), ("第577条...", 0.42)]
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
        top_k: int = 5,
    ) -> None:
        """
        Args:
            model_name: HuggingFace reranker 模型名称.
            device: 运行设备（"cpu" / "cuda"）.
            top_k: 重排序后保留的结果数.
        """
        self.model_name = model_name
        self.device = device
        self.top_k = top_k
        self._model = None

    @property
    def model(self):
        """懒加载 reranker 模型."""
        if self._model is None:
            try:
                from FlagEmbedding import FlagReranker
                # 关闭 torch 梯度以节省内存
                self._model = FlagReranker(
                    self.model_name,
                    use_fp16=(self.device != "cpu"),
                    device=self.device,
                )
                logger.info(f"Reranker 模型加载完成: {self.model_name}")
            except ImportError:
                raise ImportError(
                    "FlagEmbedding 未安装，请执行: pip install FlagEmbedding>=1.3.0"
                )
        return self._model

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        top_k: Optional[int] = None,
    ) -> List[Tuple[int, float]]:
        """对文档列表重排序.

        Args:
            query: 查询文本.
            documents: 候选文档文本列表.
            top_k: 返回结果数，默认使用 self.top_k.

        Returns:
            [(doc_index, relevance_score), ...] 按分数降序排列.
        """
        if not documents:
            return []

        k = top_k or self.top_k

        try:
            # 构建 (query, doc) 对
            pairs = [[query, doc] for doc in documents]
            scores = self.model.compute_score(pairs, normalize=True)

            # 单文档时 scores 是标量，包装为列表
            if isinstance(scores, float):
                scores = [scores]

            # 按分数排序
            indexed: List[Tuple[int, float]] = list(enumerate(scores))
            indexed.sort(key=lambda x: x[1], reverse=True)

            return indexed[:k]

        except Exception as e:
            logger.error(f"Reranker 重排序失败: {e}")
            # 失败时返回原始顺序的前 k 个
            return [(i, 0.0) for i in range(min(k, len(documents)))]

    def is_ready(self) -> bool:
        """检查模型是否已加载."""
        try:
            _ = self.model
            return True
        except Exception:
            return False


def apply_rerank(
    reranker: Reranker,
    query: str,
    candidates: List[Any],
    text_getter=lambda x: x.text if hasattr(x, "text") else str(x),
) -> List[Tuple[int, float]]:
    """对候选结果列表应用重排序的便捷函数.

    Args:
        reranker: Reranker 实例.
        query: 查询文本.
        candidates: 候选结果列表.
        text_getter: 从候选项中提取文本的函数.

    Returns:
        [(original_index, rerank_score), ...] 按分数降序.
    """
    docs = [text_getter(c) for c in candidates]
    return reranker.rerank(query, docs)
