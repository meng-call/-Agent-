"""
报告节点 — 合并审查结果生成最终报告.

汇总 legal_review + business_risk 的产出，
统计风险等级分布 + 三层分布，
综合两个维度给出最终签署建议。
"""

from typing import Any, Dict, List

from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


def _derive_final_conclusion(
    legal_conclusion: str,
    business_conclusion: str,
) -> str:
    """综合法律和商业结论，给出最终裁决.

    规则:
    - 任一为"不建议签" → 最终"不建议签"
    - 任一为"有条件可签" → 最终"有条件可签"
    - 两者均为"可签" → 最终"可签"
    """
    if "不建议" in legal_conclusion or "不建议" in business_conclusion:
        return "不建议签"
    if "有条件" in legal_conclusion or "有条件" in business_conclusion:
        return "有条件可签"
    return "可签"


def _count_by_layer(risks: List[Dict]) -> Dict[str, int]:
    """按审查层统计风险数量."""
    counts = {"宏观层": 0, "中观层": 0, "微观层": 0, "未分类": 0}
    for r in risks:
        layer = r.get("layer", "未分类")
        counts[layer] = counts.get(layer, 0) + 1
    return counts


def _count_by_level(risks: List[Dict]) -> Dict[str, int]:
    """按风险等级统计."""
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for r in risks:
        level = r.get("risk_level", "")
        if level in counts:
            counts[level] += 1
    return counts


def report_node(state: AgentState) -> Dict[str, Any]:
    """合并法律审查与商业风险评估结果，生成最终结构化审查报告.

    Args:
        state: 当前工作流状态（含所有前置节点产出）.

    Returns:
        final_report 字典.
    """
    logger.info("Report: 开始合并审查结果...")

    legal_risks = state.get("legal_risks", [])
    business_risks = state.get("business_risks", [])
    error = state.get("error", "")

    # ── 统计 ──────────────────────────────────────────
    all_risks = legal_risks + business_risks

    legal_levels = _count_by_level(legal_risks)
    business_levels = _count_by_level(business_risks)
    legal_layers = _count_by_layer(legal_risks)
    business_layers = _count_by_layer(business_risks)

    total_levels = _count_by_level(all_risks)

    # ── 结论裁决 ──────────────────────────────────────
    legal_conclusion = state.get("legal_overall_conclusion", "有条件可签")
    business_conclusion = state.get("business_overall_conclusion", "有条件可签")
    final_conclusion = _derive_final_conclusion(legal_conclusion, business_conclusion)

    # ── 合并先决条件 ──────────────────────────────────
    legal_preconditions = state.get("legal_preconditions", [])
    business_preconditions = state.get("business_preconditions", [])
    all_preconditions = legal_preconditions + business_preconditions

    # ── 构建报告 ──────────────────────────────────────
    report = {
        "meta": {
            "contract_type": state.get("contract_type", "未知"),
            "contract_sub_type": state.get("contract_sub_type", ""),
            "contract_category_id": state.get("contract_category_id", 0),
            "contract_type_confidence": state.get("contract_type_confidence", 0.0),
            "contract_type_analysis": state.get("contract_type_analysis", ""),
            "contract_key_features": state.get("contract_key_features", []),
            "contract_suggested_focus": state.get("contract_suggested_focus", ""),
        },
        "verdict": {
            "final_conclusion": final_conclusion,
            "legal_conclusion": legal_conclusion,
            "business_conclusion": business_conclusion,
            "preconditions": all_preconditions,
            "reasoning": (
                f"法律审查结论：{legal_conclusion}；"
                f"商业审查结论：{business_conclusion}；"
                f"综合裁决：{final_conclusion}"
            ),
        },
        "statistics": {
            "total_risks": len(all_risks),
            "by_level": {
                "P0": total_levels["P0"],
                "P1": total_levels["P1"],
                "P2": total_levels["P2"],
            },
            "legal": {
                "total": len(legal_risks),
                "by_level": legal_levels,
                "by_layer": legal_layers,
            },
            "business": {
                "total": len(business_risks),
                "by_level": business_levels,
                "by_layer": business_layers,
            },
        },
        "legal_review": {
            "risks": legal_risks,
            "summary": state.get("legal_summary", ""),
        },
        "business_review": {
            "risks": business_risks,
            "overall_assessment": state.get("business_assessment", ""),
            "recommendation": state.get("business_recommendation", ""),
        },
        "has_error": bool(error),
        "error": error if error else None,
    }

    logger.info(
        "report.completed",
        total_risks=len(all_risks),
        P0=total_levels["P0"],
        P1=total_levels["P1"],
        P2=total_levels["P2"],
        final_conclusion=final_conclusion,
    )
    return {"final_report": report}
