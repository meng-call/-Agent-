"""
合约风控审查 Agent 系统 — SQLAlchemy ORM 基类.

所有模型继承自此 Base，统一命名约定.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 命名约定：确保索引、约束、外键有可读的名称
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """所有 ORM 模型的基类."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
