"""
合约风控审查 Agent 系统 — 异步数据库会话管理.

提供 SQLAlchemy 异步引擎创建、会话获取和表初始化.
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import MySQLSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine = None
_session_factory: Optional[async_sessionmaker] = None


def _create_engine(settings: MySQLSettings, echo: bool = False):
    """创建异步引擎（进程级单例）."""
    global _engine
    if _engine is not None:
        return _engine

    logger.info(
        "db.engine_creating",
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )
    _engine = create_async_engine(
        settings.url,
        echo=echo,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # 连接前检测可用性
    )
    return _engine


def _get_session_factory(settings: MySQLSettings) -> async_sessionmaker:
    """获取异步会话工厂（进程级单例）."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = _create_engine(settings, echo=(settings.database == "test"))
    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _session_factory


async def get_async_session(
    settings: MySQLSettings,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：获取异步数据库会话.

    每个请求获取独立会话，请求结束后自动关闭.

    Usage::

        from fastapi import Depends
        from app.db.session import get_async_session

        @router.get("/items")
        async def list_items(
            session: AsyncSession = Depends(get_async_session),
        ):
            ...
    """
    factory = _get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(settings: MySQLSettings) -> None:
    """创建所有表（开发环境使用，生产请用 Alembic 迁移）.

    导入所有模型后调用此函数，自动建表.
    """
    from app.db.base import Base
    # 触发模型注册
    import app.models  # noqa: F401

    engine = _create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    table_names = list(Base.metadata.tables.keys())
    logger.info("db.tables_created", tables=table_names)


async def dispose_engine() -> None:
    """关闭数据库连接池（应用关闭时调用）."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("db.engine_disposed")
