"""
LegalRetriever 检索器测试（不依赖 Milvus 连接）.
"""

import pytest

from app.rag.retriever import RetrievalConfig, SearchResult


class TestSearchResult:
    """SearchResult 数据类测试."""

    def test_default_values(self):
        """默认值正确."""
        r = SearchResult(text="测试文本")
        assert r.text == "测试文本"
        assert r.source == ""
        assert r.law_category == ""
        assert r.article_number == ""
        assert r.score == 0.0
        assert r.metadata == {}

    def test_full_fields(self):
        """所有字段正确赋值."""
        r = SearchResult(
            text="违约金不得超过...",
            source="民法典.pdf",
            law_category="民法-合同编",
            article_number="第585条",
            score=0.92,
            metadata={"id": 42},
        )
        assert r.source == "民法典.pdf"
        assert r.law_category == "民法-合同编"
        assert r.article_number == "第585条"
        assert r.score == 0.92
        assert r.metadata["id"] == 42


class TestRetrievalConfig:
    """检索配置测试."""

    def test_defaults(self):
        """默认配置值."""
        cfg = RetrievalConfig()
        assert cfg.top_k == 5
        assert cfg.score_threshold == 0.0
        assert cfg.metric_type == "COSINE"
        assert cfg.enable_hybrid is True
        assert cfg.enable_rerank is True
        assert cfg.rerank_top_k == 5

    def test_custom(self):
        """自定义配置."""
        cfg = RetrievalConfig(
            top_k=10,
            score_threshold=0.5,
            enable_hybrid=False,
            enable_rerank=False,
        )
        assert cfg.top_k == 10
        assert cfg.score_threshold == 0.5
        assert not cfg.enable_hybrid
        assert not cfg.enable_rerank


class TestParseSearchResults:
    """Milvus 原始结果解析测试."""

    def test_empty_results(self):
        """空结果."""
        from app.rag.retriever import LegalRetriever
        results = LegalRetriever._parse_search_results([], 0.0)
        assert results == []

    def test_none_first_element(self):
        """第一层为空列表."""
        from app.rag.retriever import LegalRetriever
        results = LegalRetriever._parse_search_results([[]], 0.0)
        assert results == []

    def test_normal_results(self):
        """标准结果解析."""
        from app.rag.retriever import LegalRetriever
        raw = [[
            {
                "id": 1,
                "distance": 0.95,
                "entity": {
                    "text": "违约金超过造成损失的百分之三十...",
                    "source": "民法典.pdf",
                    "law_category": "民法-合同编",
                    "article_number": "第585条",
                },
            },
            {
                "id": 2,
                "distance": 0.72,
                "entity": {
                    "text": "当事人可以约定违约金...",
                    "source": "民法典.pdf",
                    "law_category": "民法-合同编",
                    "article_number": "第585条",
                },
            },
        ]]
        results = LegalRetriever._parse_search_results(raw, 0.0)
        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[0].metadata["id"] == 1
        assert results[1].article_number == "第585条"

    def test_score_threshold_filter(self):
        """阈值过滤生效."""
        from app.rag.retriever import LegalRetriever
        raw = [[
            {
                "id": 1,
                "distance": 0.95,
                "entity": {"text": "高分结果", "source": "", "law_category": "", "article_number": ""},
            },
            {
                "id": 2,
                "distance": 0.45,
                "entity": {"text": "低分结果", "source": "", "law_category": "", "article_number": ""},
            },
        ]]
        results = LegalRetriever._parse_search_results(raw, 0.5)
        assert len(results) == 1
        assert results[0].metadata["id"] == 1
