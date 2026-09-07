"""
合约风控审查 Agent 系统 — 审查记录与风险项 ORM 模型.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReviewRecord(Base):
    """存储每次审查的完整结果."""

    __tablename__ = "review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, comment="关联合同 ID"
    )
    final_conclusion: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="最终裁决：可签/有条件可签/不建议签"
    )
    legal_conclusion: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="法律审查结论"
    )
    business_conclusion: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="商业审查结论"
    )
    total_risks: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="风险总数"
    )
    preconditions: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="签署先决条件列表"
    )
    reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="综合裁决推理"
    )
    meta_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="合同分类信息快照"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="审查时间"
    )

    # 关联
    contract: Mapped["ContractRecord"] = relationship(
        "ContractRecord", back_populates="reviews"
    )
    risks: Mapped[List["RiskRecord"]] = relationship(
        "RiskRecord", back_populates="review", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ReviewRecord id={self.id} contract_id={self.contract_id} "
            f"conclusion={self.final_conclusion}>"
        )


class RiskRecord(Base):
    """存储每个识别出的风险项."""

    __tablename__ = "risk_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("review_records.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联审查记录 ID",
    )
    risk_name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="风险名称"
    )
    risk_level: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="风险等级：P0/P1/P2"
    )
    risk_consequence: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="风险后果"
    )
    related_clause: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, comment="关联条款"
    )
    layer: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="审查层次：宏观层/中观层/微观层"
    )
    review_category: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="审查类别：legal/business"
    )
    legal_basis: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="法律依据"
    )
    criteria: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="判别标准"
    )
    example: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="风险示例"
    )
    recommended_wording: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="建议条文"
    )
    remediation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="整改建议"
    )
    negotiation_priority: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="谈判优先级（仅商业风险）"
    )
    detail: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="商业风险详细说明"
    )

    # 关联
    review: Mapped["ReviewRecord"] = relationship(
        "ReviewRecord", back_populates="risks"
    )

    def __repr__(self) -> str:
        return f"<RiskRecord id={self.id} name={self.risk_name} level={self.risk_level}>"
