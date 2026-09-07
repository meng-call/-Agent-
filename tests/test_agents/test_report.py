"""
Report 节点纯函数测试 — 结论裁决 + 统计.
"""

import pytest

from app.agents.nodes.report import (
    _count_by_layer,
    _count_by_level,
    _derive_final_conclusion,
    report_node,
)


class TestDeriveFinalConclusion:
    """综合裁决规则."""

    def test_both_approve(self):
        """双方可签 → 可签."""
        assert _derive_final_conclusion("可签", "可签") == "可签"

    def test_legal_conditional(self):
        """法律有条件 → 有条件可签."""
        assert _derive_final_conclusion("有条件可签", "可签") == "有条件可签"

    def test_business_conditional(self):
        """商业有条件 → 有条件可签."""
        assert _derive_final_conclusion("可签", "有条件可签") == "有条件可签"

    def test_both_conditional(self):
        """双方有条件 → 有条件可签."""
        assert _derive_final_conclusion("有条件可签", "有条件可签") == "有条件可签"

    def test_legal_reject(self):
        """法律不建议签 → 不建议签（无论如何）."""
        assert _derive_final_conclusion("不建议签", "可签") == "不建议签"
        assert _derive_final_conclusion("不建议签", "有条件可签") == "不建议签"
        assert _derive_final_conclusion("不建议签", "不建议签") == "不建议签"

    def test_business_reject(self):
        """商业不建议签 → 不建议签."""
        assert _derive_final_conclusion("可签", "不建议签") == "不建议签"
        assert _derive_final_conclusion("有条件可签", "不建议签") == "不建议签"

    def test_partial_match_keywords(self):
        """包含关键词即匹配（如'不建议签xxx'）."""
        assert _derive_final_conclusion("不建议签署", "可签") == "不建议签"


class TestCountByLevel:
    """风险等级统计."""

    def test_empty(self):
        assert _count_by_level([]) == {"P0": 0, "P1": 0, "P2": 0}

    def test_mixed(self):
        risks = [
            {"risk_level": "P0"},
            {"risk_level": "P0"},
            {"risk_level": "P1"},
            {"risk_level": "P2"},
            {"risk_level": ""},  # 空等级不计入
        ]
        counts = _count_by_level(risks)
        assert counts["P0"] == 2
        assert counts["P1"] == 1
        assert counts["P2"] == 1

    def test_unknown_level_ignored(self):
        """未知等级不被计入."""
        risks = [{"risk_level": "P3"}, {"risk_level": "XX"}]
        counts = _count_by_level(risks)
        assert counts == {"P0": 0, "P1": 0, "P2": 0}


class TestCountByLayer:
    """审查层统计."""

    def test_empty(self):
        assert _count_by_layer([])["宏观层"] == 0
        assert _count_by_layer([])["中观层"] == 0
        assert _count_by_layer([])["微观层"] == 0

    def test_mixed_layers(self):
        risks = [
            {"layer": "宏观层"},
            {"layer": "宏观层"},
            {"layer": "中观层"},
            {"layer": "微观层"},
            {"layer": "微观层"},
            {"layer": "微观层"},
        ]
        counts = _count_by_layer(risks)
        assert counts == {"宏观层": 2, "中观层": 1, "微观层": 3, "未分类": 0}

    def test_default_to_uncategorized(self):
        """无 layer 字段默认为'未分类'."""
        risks = [{"risk_name": "test"}]
        counts = _count_by_layer(risks)
        assert counts["未分类"] == 1


class TestReportNode:
    """report_node 完整输出."""

    def test_report_structure(self, sample_state):
        """报告结构完整."""
        result = report_node(sample_state)
        report = result["final_report"]

        # 顶层结构
        assert "meta" in report
        assert "verdict" in report
        assert "statistics" in report
        assert "legal_review" in report
        assert "business_review" in report

    def test_meta_passthrough(self, sample_state):
        """meta 信息正确传递."""
        result = report_node(sample_state)
        meta = result["final_report"]["meta"]

        assert meta["contract_type"] == "买卖合同"
        assert meta["contract_category_id"] == 1
        assert meta["contract_type_confidence"] == 0.92

    def test_verdict_logic(self, sample_state):
        """裁决逻辑 — 双方有条件 → 最终有条件."""
        result = report_node(sample_state)
        verdict = result["final_report"]["verdict"]

        assert verdict["final_conclusion"] == "有条件可签"
        assert verdict["legal_conclusion"] == "有条件可签"
        assert verdict["business_conclusion"] == "有条件可签"

    def test_statistics(self, sample_state):
        """统计数据正确."""
        result = report_node(sample_state)
        stats = result["final_report"]["statistics"]

        assert stats["total_risks"] == 4  # 3 legal + 1 business
        assert stats["by_level"]["P0"] == 2
        assert stats["by_level"]["P1"] == 1
        assert stats["by_level"]["P2"] == 1

    def test_error_flag(self, sample_state):
        """错误标志 — 无错误时 has_error=False."""
        result = report_node(sample_state)
        assert not result["final_report"]["has_error"]
        assert result["final_report"]["error"] is None

    def test_with_error(self, sample_state):
        """错误传播."""
        state_with_error = {**sample_state, "error": "LLM 调用超时"}
        result = report_node(state_with_error)
        assert result["final_report"]["has_error"]
        assert result["final_report"]["error"] == "LLM 调用超时"

    def test_preconditions_merged(self, sample_state):
        """法律 + 商业先决条件合并."""
        result = report_node(sample_state)
        preconditions = result["final_report"]["verdict"]["preconditions"]
        assert "修改违约金条款" in preconditions
        assert "协商缩短付款周期" in preconditions

    def test_empty_state(self):
        """空 state 不崩溃."""
        result = report_node({})
        report = result["final_report"]
        assert report["verdict"]["final_conclusion"] == "有条件可签"  # 默认值
        assert report["statistics"]["total_risks"] == 0
