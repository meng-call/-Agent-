"""
合约风控审查 Agent 系统 — 法律知识检索器.

组合 Embedding 模型与 Milvus 客户端，提供端到端检索接口：
输入自然语言查询 → Embedding → ANN 搜索 → 返回 Top-K 法律条文片段。

支持混合检索：BM25 关键词 + 向量语义 → RRF 融合.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.rag.embedding import EmbeddingModel
from app.rag.milvus_client import MilvusManager

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """单条检索结果."""

    text: str
    source: str = ""
    law_category: str = ""
    article_number: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalConfig:
    """检索配置."""

    top_k: int = 5
    score_threshold: float = 0.0
    metric_type: str = "COSINE"

    # 混合检索
    enable_hybrid: bool = True
    bm25_weight: float = 0.3  # BM25 在 RRF 融合后的结果截取权重（未直接使用，RRF 自动平衡）

    # 重排序
    enable_rerank: bool = True
    rerank_top_k: int = 5
    rerank_model: str = "BAAI/bge-reranker-v2-m3"


class LegalRetriever:
    """法律知识检索器.

    用法::

        retriever = LegalRetriever(milvus_manager, embedding_model)
        results = retriever.retrieve("租赁合同违约金最高多少？")

        # 混合检索（BM25 + 向量）
        results = retriever.retrieve_hybrid("违约金超过法定上限")
    """

    def __init__(
        self,
        milvus: MilvusManager,
        embedding: EmbeddingModel,
        config: Optional[RetrievalConfig] = None,
    ) -> None:
        """
        Args:
            milvus: MilvusManager 实例.
            embedding: EmbeddingModel 实例.
            config: 检索配置.
        """
        self.milvus = milvus
        self.embedding = embedding
        self.config = config or RetrievalConfig()

        # BM25 搜索引擎（懒初始化）
        self._bm25_searcher = None
        self._corpus_doc_ids: List[int] = []

        # Cross-encoder 重排序器（懒初始化）
        self._reranker = None

    # ── 公开 API ──────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filter_category: Optional[str] = None,
    ) -> List[SearchResult]:
        """向量语义检索.

        Args:
            query: 自然语言查询.
            top_k: 返回结果数，默认使用 config.top_k.
            score_threshold: 最低相似度阈值，低于此值的结果被过滤.
            filter_category: 可选，按法律类别过滤.

        Returns:
            排序后的 SearchResult 列表.
        """
        k = top_k or self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold

        # Step 1: 编码查询
        query_vectors = self.embedding.encode_queries([query])

        # Step 2: 构建过滤表达式
        filter_expr: Optional[str] = None
        if filter_category:
            filter_expr = f'law_category == "{filter_category}"'

        # Step 3: Milvus 搜索
        raw_results = self.milvus.search(
            query_vectors=query_vectors,
            limit=k,
            output_fields=["text", "source", "law_category", "article_number"],
            metric_type=self.config.metric_type,
        )

        # Step 4: 解析并过滤结果
        return self._parse_search_results(raw_results, threshold)

    def retrieve_hybrid(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filter_category: Optional[str] = None,
    ) -> List[SearchResult]:
        """混合检索：BM25 关键词 + 向量语义 → RRF 融合.

        对法律检索场景，BM25 能精确匹配"违约金""不可抗力"等法律术语，
        向量搜索捕获语义相近但措辞不同的条文，RRF 融合两者优势.

        Args:
            query: 自然语言查询.
            top_k: 最终返回结果数.
            score_threshold: 最低相似度阈值.
            filter_category: 可选，按法律类别过滤.

        Returns:
            融合后排序的 SearchResult 列表.
        """
        k = top_k or self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold

        # 确保 BM25 索引已构建
        self._ensure_bm25_index()

        # ── 并行执行两种检索 ──────────────────────────────────
        # 向量检索
        vector_results = self.retrieve(
            query, top_k=k * 2, score_threshold=threshold,
            filter_category=filter_category,
        )

        # BM25 关键词检索
        bm25_raw: List[Tuple[int, float]] = []
        if self._bm25_searcher and self._bm25_searcher.is_ready():
            bm25_hits = self._bm25_searcher.search(query, top_k=k * 2)
            # 映射 BM25 内部 index → Milvus id
            for doc_idx, score, _meta in bm25_hits:
                if doc_idx < len(self._corpus_doc_ids):
                    milvus_id = self._corpus_doc_ids[doc_idx]
                    bm25_raw.append((milvus_id, score))

        # ── RRF 融合 ──────────────────────────────────────────
        if not bm25_raw:
            logger.debug("BM25 未返回结果，回退纯向量检索")
            return vector_results[:k]

        # 向量结果 → [(doc_id, score)]
        vec_ranked = [(r.metadata.get("id", 0), r.score) for r in vector_results]

        from app.rag.bm25 import reciprocal_rank_fusion
        fused = reciprocal_rank_fusion(vec_ranked, bm25_raw)

        # ── 构建结果 ──────────────────────────────────────────
        # 建立 doc_id → SearchResult 映射
        vec_map: Dict[int, SearchResult] = {}
        for r in vector_results:
            doc_id = r.metadata.get("id", 0)
            if doc_id:
                vec_map[doc_id] = r

        # BM25 独有结果（向量搜索未召回）需从 Milvus 查询
        bm25_only_ids = [
            doc_id for doc_id, _ in fused[:k]
            if doc_id not in vec_map and doc_id > 0
        ]
        if bm25_only_ids:
            bm25_entities = self._fetch_by_ids(bm25_only_ids)
            for entity in bm25_entities:
                doc_id = entity.get("id", 0)
                vec_map[doc_id] = SearchResult(
                    text=entity.get("text", ""),
                    source=entity.get("source", ""),
                    law_category=entity.get("law_category", ""),
                    article_number=entity.get("article_number", ""),
                    score=0.0,
                    metadata={"id": doc_id},
                )

        # 按 RRF 排序输出
        hybrid_results: List[SearchResult] = []
        for doc_id, rrf_score in fused[:k]:
            if doc_id in vec_map:
                result = vec_map[doc_id]
                result.score = rrf_score
                hybrid_results.append(result)

        logger.info(
            f"混合检索: query='{query[:50]}...', "
            f"向量={len(vector_results)}, BM25={len(bm25_raw)}, "
            f"融合={len(hybrid_results)}"
        )

        # ── Cross-encoder 重排序（可选）─────────────────────
        if self.config.enable_rerank:
            hybrid_results = self._apply_rerank(query, hybrid_results)

        return hybrid_results

    def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        use_hybrid: Optional[bool] = None,
        **kwargs,
    ) -> str:
        """检索并拼接为上下文文本，用于注入 LLM prompt.

        Args:
            query: 查询文本.
            top_k: 返回结果数.
            use_hybrid: 是否使用混合检索，默认使用 config.enable_hybrid.
            **kwargs: 传给 retrieve() 的额外参数.

        Returns:
            拼接后的上下文字符串，格式为 "【来源: xxx 第N条】文本...".
        """
        hybrid = use_hybrid if use_hybrid is not None else self.config.enable_hybrid

        if hybrid and self._bm25_searcher and self._bm25_searcher.is_ready():
            results = self.retrieve_hybrid(query, top_k=top_k, **kwargs)
        else:
            results = self.retrieve(query, top_k=top_k, **kwargs)

        if not results:
            return "未找到相关法律条文。"

        context_parts: List[str] = []
        for r in results:
            header = f"【{r.law_category}】" if r.law_category else "【法律条文】"
            if r.article_number:
                header = f"【{r.law_category} {r.article_number}】"
            context_parts.append(f"{header}\n{r.text}\n")

        return "\n".join(context_parts)

    # ── BM25 索引管理 ─────────────────────────────────────────

    def _ensure_bm25_index(self) -> None:
        """懒构建 BM25 索引（从 Milvus 全量加载语料）."""
        if self._bm25_searcher is not None:
            return

        try:
            from app.rag.bm25 import BM25Searcher
        except ImportError:
            logger.warning("BM25 模块不可用，混合检索将回退纯向量模式")
            return

        logger.info("正在构建 BM25 索引...")
        try:
            # 查询 Milvus 全量文档
            stats = self.milvus.get_stats()
            total_count = stats.get("row_count", 0)
            if total_count == 0:
                logger.warning("Milvus Collection 为空，跳过 BM25 索引")
                return

            # 分批获取全部文档（避免一次 query 内存爆炸）
            batch_size = 500
            all_texts: List[str] = []
            all_metadata: List[Dict[str, Any]] = []
            self._corpus_doc_ids = []

            # 使用 query iterator 遍历全量数据
            offset = 0
            while offset < total_count:
                batch = self.milvus.client.query(
                    collection_name=self.milvus.collection_name,
                    filter="id >= 0",
                    output_fields=["id", "text", "source", "law_category", "article_number"],
                    limit=batch_size,
                    offset=offset,
                )
                if not batch:
                    break
                for doc in batch:
                    all_texts.append(doc.get("text", ""))
                    all_metadata.append({
                        "id": doc.get("id"),
                        "source": doc.get("source", ""),
                        "law_category": doc.get("law_category", ""),
                        "article_number": doc.get("article_number", ""),
                    })
                    self._corpus_doc_ids.append(doc.get("id"))
                offset += len(batch)

            if not all_texts:
                return

            self._bm25_searcher = BM25Searcher()
            self._bm25_searcher.index(all_texts, all_metadata)
            logger.info(f"BM25 索引就绪: {len(all_texts)} 文档")

        except Exception as e:
            logger.error(f"BM25 索引构建失败: {e}")
            self._bm25_searcher = None

    def _fetch_by_ids(self, ids: List[int]) -> List[Dict[str, Any]]:
        """按 ID 批量从 Milvus 获取文档."""
        if not ids:
            return []
        try:
            id_list = ", ".join(str(i) for i in ids)
            return self.milvus.client.query(
                collection_name=self.milvus.collection_name,
                filter=f"id in [{id_list}]",
                output_fields=["id", "text", "source", "law_category", "article_number"],
                limit=len(ids),
            )
        except Exception as e:
            logger.warning(f"按 ID 查询失败: {e}")
            return []

    # ── Reranker ─────────────────────────────────────────────

    def _ensure_reranker(self) -> None:
        """懒初始化 cross-encoder reranker."""
        if self._reranker is not None:
            return
        try:
            from app.rag.reranker import Reranker
            self._reranker = Reranker(
                model_name=self.config.rerank_model,
                top_k=self.config.rerank_top_k,
            )
        except ImportError:
            logger.warning("Reranker 模块不可用")
            self._reranker = False  # 标记为已尝试但失败

    def _apply_rerank(
        self,
        query: str,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """对候选结果应用 cross-encoder 重排序."""
        self._ensure_reranker()
        if not self._reranker or self._reranker is False:
            return results
        if len(results) <= 1:
            return results

        try:
            docs = [r.text for r in results]
            scored = self._reranker.rerank(query, docs, top_k=self.config.rerank_top_k)

            reranked: List[SearchResult] = []
            for idx, score in scored:
                results[idx].score = score
                reranked.append(results[idx])

            logger.info(f"Rerank: {len(results)} → {len(reranked)} (top {self.config.rerank_top_k})")
            return reranked
        except Exception as e:
            logger.warning(f"Rerank 失败，回退原始结果: {e}")
            return results

    # ── 内部方法 ──────────────────────────────────────────────

    @staticmethod
    def _parse_search_results(
        raw_results: List[List[Dict[str, Any]]],
        threshold: float,
    ) -> List[SearchResult]:
        """解析 Milvus 原始搜索结果."""
        results: List[SearchResult] = []
        if not raw_results or not raw_results[0]:
            return results

        for hit in raw_results[0]:
            score = hit.get("distance", 0.0)
            if score < threshold:
                continue

            entity = hit.get("entity", {})
            results.append(SearchResult(
                text=entity.get("text", ""),
                source=entity.get("source", ""),
                law_category=entity.get("law_category", ""),
                article_number=entity.get("article_number", ""),
                score=score,
                metadata={"id": hit.get("id")},
            ))

        return results
