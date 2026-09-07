"""
合约风控审查 Agent 系统 — 合同记录 ORM 模型.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContractRecord(Base):
    """存储上传的合同文本及其分类元数据."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_text: Mapped[str] = mapped_column(Text, nullable=False, comment="合同全文")
    contract_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="合同分类结果"
    )
    contract_sub_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="合同子类型"
    )
    original_filename: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, comment="原始上传文件名"
    )
    text_length: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="合同文本长度"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )

    # 一对多：一个合同可被多次审查
    reviews: Mapped[List["ReviewRecord"]] = relationship(
        "ReviewRecord", back_populates="contract", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ContractRecord id={self.id} type={self.contract_type} "
            f"len={self.text_length}>"
        )
