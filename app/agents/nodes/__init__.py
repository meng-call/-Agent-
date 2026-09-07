"""
合约风控审查 Agent 系统 — Agent 节点.

每个节点封装一个独立的审查步骤，通过 LangGraph StateGraph 串联。
dispatch / legal_review / business_risk 使用工厂函数模式（闭包注入依赖），
report 为纯函数。
"""

from app.agents.nodes.business_risk import create_business_risk_node
from app.agents.nodes.dispatch import create_dispatch_node
from app.agents.nodes.legal_review import create_legal_review_node
from app.agents.nodes.report import report_node

__all__ = [
    "create_dispatch_node",
    "create_legal_review_node",
    "create_business_risk_node",
    "report_node",
]
