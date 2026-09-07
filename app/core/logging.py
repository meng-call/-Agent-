"""
合约风控审查 Agent 系统 — 结构化日志配置.

基于 structlog 实现 Professional 规模的结构化日志：
- JSON 格式输出，每个字段独立可索引
- 自动注入模块名、时间戳
- 支持上下文绑定（session_id / node_name）
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """初始化结构化日志系统.

    Args:
        level: 日志级别 (DEBUG / INFO / WARNING / ERROR).
        json_format: True=JSON 输出（生产），False=彩色控制台（开发）.
    """
    # 标准库日志桥接
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        # 生产：结构化 JSON
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.format_exc_info,
                timestamper,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper(), logging.INFO)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )
    else:
        # 开发：彩色控制台
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.ExceptionRenderer(),
                timestamper,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper(), logging.INFO)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stdout),
            cache_logger_on_first_use=True,
        )

    # 抑制第三方库的 DEBUG 日志
    for lib in ("httpx", "openai", "pymilvus", "sentence_transformers"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(
    name: Optional[str] = None,
    **bindings: Any,
) -> structlog.BoundLogger:
    """获取绑定上下文的 logger.

    Args:
        name: logger 名称（通常用 __name__）.
        **bindings: 要绑定的上下文键值对，如 session_id="xxx".

    Returns:
        绑定了上下文的 structlog BoundLogger.

    Usage::

        logger = get_logger(__name__, session_id="abc123")
        logger.info("review.started", contract_type="买卖合同")
    """
    logger = structlog.get_logger(name or __name__)
    if bindings:
        logger = logger.bind(**bindings)
    return logger
