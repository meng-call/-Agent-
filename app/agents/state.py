"""
合约风控审查 Agent 系统 — LangGraph Agent 状态定义.

定义在审查工作流中流转的共享状态 TypedDict.
"""

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """多 Agent 审查工作流共享状态.

    字段说明:
        contract_text: 原始合同文本（用户输入）.
        contract_type: 合同分类结果（dispatch 节点产出）.
        contract_sub_type: 合同子类型（如"房产租赁"）.
        contract_category_id: 12 类分类编号 1-12.
        contract_type_confidence: 分类置信度 0.0~1.0.
        contract_type_analysis: 分类依据说明.
        contract_key_features: 从合同文本提取的关键特征列表.
        contract_suggested_focus: 建议审查重点.
        legal_risks: 法律合规风险列表（legal_review 节点产出）.
        legal_summary: 法律审查摘要.
        legal_overall_conclusion: 法律审查结论（可签/有条件可签/不建议签）.
        legal_preconditions: 签署前必须满足的先决条件.
        business_risks: 商业风险列表（business_risk 节点产出）.
        business_assessment: 商业整体评估.
        business_recommendation: 商业建议.
        business_overall_conclusion: 商业审查结论（可签/有条件可签/不建议签）.
        business_preconditions: 商业建议签署前必须满足的先决条件.
        final_report: 最终合并审查报告（report 节点产出）.
        error: 全局错误信息.
    """

    # ---- 输入 ----
    contract_text: str

    # ---- Dispatch 节点产出 ----
    contract_type: str
    contract_sub_type: str
    contract_category_id: int
    contract_type_confidence: float
    contract_type_analysis: str
    contract_key_features: List[str]
    contract_suggested_focus: str

    # ---- Legal Review 节点产出 ----
    legal_risks: List[Dict[str, Any]]
    legal_summary: str
    legal_overall_conclusion: str
    legal_preconditions: List[str]

    # ---- Business Risk 节点产出 ----
    business_risks: List[Dict[str, Any]]
    business_assessment: str
    business_recommendation: str
    business_overall_conclusion: str
    business_preconditions: List[str]

    # ---- Report 节点产出 ----
    final_report: Dict[str, Any]

    # ---- 错误 ----
    error: str
