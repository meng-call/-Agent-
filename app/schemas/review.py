"""
合约风控审查 Agent 系统 — 合同审查 API Schema.

定义审查请求/响应的 Pydantic 数据模型.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── 请求 ──────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    """合同审查请求（纯文本模式）."""

    contract_text: str = Field(
        ...,
        min_length=1,
        max_length=200_000,
        description="待审查的合同原文文本",
        examples=["甲方与乙方就XX事项达成如下协议：\n第一条 ..."],
    )
    contract_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description="合同名称（可选，用于结果标识）",
    )


# ── 风险项 ────────────────────────────────────────────────────────

class RiskItem(BaseModel):
    """单个风险项 — 统一法律 & 商业风险字段."""

    risk_name: str = Field(..., description="风险名称")
    risk_level: str = Field(..., description="风险等级：P0 / P1 / P2")
    risk_consequence: str = Field(..., description="风险后果")
    related_clause: str = Field(default="", description="相关条款位置")
    layer: str = Field(default="微观层", description="审查层：宏观层 / 中观层 / 微观层")

    # 法律审查特有
    legal_basis: Optional[str] = Field(default=None, description="法律依据（法条编号+条文）")
    criteria: Optional[str] = Field(default=None, description="判别标准")
    example: Optional[str] = Field(default=None, description="风险示例/判例")
    recommended_wording: Optional[str] = Field(default=None, description="推荐措辞")
    remediation: Optional[str] = Field(default=None, description="整改建议")

    # 商业审查特有
    negotiation_priority: Optional[str] = Field(default=None, description="谈判优先级")
    detail: Optional[str] = Field(default=None, description="详细分析")


# ── 报告子结构 ────────────────────────────────────────────────────

class ReviewMeta(BaseModel):
    """审查元信息."""

    contract_type: str = Field(default="未知", description="合同分类")
    contract_sub_type: str = Field(default="", description="合同子类型")
    contract_category_id: int = Field(default=0, description="分类编号 1-12")
    contract_type_confidence: float = Field(default=0.0, description="分类置信度")
    contract_type_analysis: str = Field(default="", description="分类依据")
    contract_key_features: List[str] = Field(default_factory=list, description="关键特征")
    contract_suggested_focus: str = Field(default="", description="建议审查重点")


class ReviewVerdict(BaseModel):
    """审查结论."""

    final_conclusion: str = Field(..., description="最终裁决：可签 / 有条件可签 / 不建议签")
    legal_conclusion: str = Field(..., description="法律审查结论")
    business_conclusion: str = Field(..., description="商业审查结论")
    preconditions: List[str] = Field(default_factory=list, description="签署前置条件")
    reasoning: str = Field(default="", description="裁决推理过程")


class LevelStats(BaseModel):
    """按风险等级统计."""

    P0: int = 0
    P1: int = 0
    P2: int = 0


class LayerStats(BaseModel):
    """按审查层统计."""

    macro: int = Field(default=0, alias="宏观层")
    meso: int = Field(default=0, alias="中观层")
    micro: int = Field(default=0, alias="微观层")


class ReviewStatistics(BaseModel):
    """审查统计."""

    total_risks: int = 0
    by_level: LevelStats = Field(default_factory=LevelStats)
    legal: Dict[str, Any] = Field(default_factory=dict)
    business: Dict[str, Any] = Field(default_factory=dict)


class ReviewSection(BaseModel):
    """审查章节（法律 or 商业）."""

    risks: List[RiskItem] = Field(default_factory=list)
    summary: str = Field(default="", description="审查摘要")
    overall_assessment: Optional[str] = Field(default=None, description="整体评估（商业）")
    recommendation: Optional[str] = Field(default=None, description="谈判建议（商业）")


# ── 响应 ──────────────────────────────────────────────────────────

class ReviewData(BaseModel):
    """审查报告完整数据."""

    meta: ReviewMeta = Field(default_factory=ReviewMeta)
    verdict: ReviewVerdict
    statistics: ReviewStatistics = Field(default_factory=ReviewStatistics)
    legal_review: ReviewSection = Field(default_factory=ReviewSection)
    business_review: ReviewSection = Field(default_factory=ReviewSection)
    has_error: bool = False
    error: Optional[str] = None
    reviewed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="审查完成时间",
    )


class ReviewResponse(BaseModel):
    """合同审查 API 响应."""

    code: int = 0
    message: str = "success"
    data: Optional[ReviewData] = None
