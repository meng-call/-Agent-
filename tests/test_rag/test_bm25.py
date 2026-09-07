"""
BM25 搜索引擎 + RRF 融合算法测试.
"""

import pytest

from app.rag.bm25 import BM25Searcher, reciprocal_rank_fusion


class TestBM25Searcher:
    """BM25 检索引擎测试."""

    @pytest.fixture
    def corpus(self) -> list:
        """中文法律文本语料."""
        return [
            "违约金超过造成损失的百分之三十的，视为过分高于造成的损失",
            "当事人可以约定一方违约时向对方支付一定数额的违约金",
            "约定的违约金低于造成的损失的，当事人可以请求增加",
            "买卖合同是出卖人转移标的物所有权于买受人，买受人支付价款的合同",
            "不可抗力是指不能预见、不能避免且不能克服的客观情况",
        ]

    @pytest.fixture
    def searcher(self, corpus) -> BM25Searcher:
        """索引已构建的 BM25Searcher."""
        s = BM25Searcher()
        s.index(corpus)
        return s

    def test_index_empty(self):
        """空语料索引不报错."""
        s = BM25Searcher()
        s.index([])
        assert not s.is_ready()

    def test_index_and_search(self, searcher, corpus):
        """索引构建后能正常搜索."""
        assert searcher.is_ready()

        results = searcher.search("违约金超过法定上限", top_k=3)
        assert len(results) > 0
        # 第一条应该包含"违约金"关键词
        top_text = corpus[results[0][0]]
        assert "违约金" in top_text

    def test_search_no_match(self, searcher):
        """不相关查询返回空结果."""
        results = searcher.search("火星探测计划", top_k=5)
        # 不相关查询分数为 0，被过滤
        assert len(results) == 0

    def test_search_top_k(self, searcher):
        """top_k 限制生效."""
        results = searcher.search("违约金", top_k=1)
        assert 0 <= len(results) <= 1

    def test_unindexed_search_returns_empty(self):
        """未构建索引时搜索返回空列表."""
        s = BM25Searcher()
        assert s.search("违约金") == []

    def test_metadata_stored(self, corpus):
        """元数据正确关联."""
        meta = [{"id": i, "source": f"law_{i}"} for i in range(len(corpus))]
        s = BM25Searcher()
        s.index(corpus, meta)

        results = s.search("违约金", top_k=3)
        for doc_id, _score, doc_meta in results:
            assert doc_meta["id"] == doc_id


class TestReciprocalRankFusion:
    """RRF 融合算法测试."""

    def test_basic_fusion(self):
        """两条结果列表正确融合."""
        vec = [(1, 0.95), (2, 0.80), (3, 0.60)]
        bm25 = [(2, 8.5), (4, 5.0), (1, 3.0)]

        fused = reciprocal_rank_fusion(vec, bm25)

        assert len(fused) == 4  # 1,2,3,4 四个唯一文档
        # 文档 2 在两个列表中排名都靠前，应该排第一
        assert fused[0][0] == 2

    def test_empty_bm25(self):
        """BM25 为空时仅返回向量结果."""
        vec = [(1, 0.95), (2, 0.80)]
        fused = reciprocal_rank_fusion(vec, [])
        assert len(fused) == 2
        # 保持向量搜索的原始排序
        assert fused[0][0] == 1

    def test_empty_vector(self):
        """向量为空时仅返回 BM25 结果."""
        bm25 = [(3, 5.0), (4, 3.0)]
        fused = reciprocal_rank_fusion([], bm25)
        assert len(fused) == 2
        assert fused[0][0] == 3

    def test_both_empty(self):
        """两边都为空."""
        fused = reciprocal_rank_fusion([], [])
        assert fused == []

    def test_rank_boost(self):
        """高排名文档获得更高 RRF 分数."""
        vec = [(1, 0.9), (2, 0.5)]
        bm25 = [(1, 8.0)]  # 文档1 在 BM25 中也排第一

        fused = reciprocal_rank_fusion(vec, bm25)
        # 文档1 在两个列表都排第一 → 分数最高
        scores = {doc_id: score for doc_id, score in fused}
        assert scores[1] > scores.get(2, 0)
