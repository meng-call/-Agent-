"""
合约风控审查 Agent 系统 — LangGraph 工作流编排.

构建和编译多 Agent 审查流水线：

    START → dispatch → [legal_review ∥ business_risk] → report → END

dispatch 后通过 Send API 并行执行两个审查节点，report 节点合并结果。
"""

import logging
from typing import Any, Dict, List

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.nodes.business_risk import create_business_risk_node
from app.agents.nodes.dispatch import create_dispatch_node
from app.agents.nodes.legal_review import create_legal_review_node
from app.agents.nodes.report import report_node
from app.agents.state import AgentState
from app.core.config import Settings
from app.llm.client import LLMClient
from app.rag.retriever import LegalRetriever

logger = logging.getLogger(__name__)


def _fan_out_to_reviews(state: AgentState) -> List[Send]:
    """从 dispatch 节点扇出到两个并行的审查节点.

    LangGraph 的 Send API：返回 Send 对象列表，
    框架并行执行所有目标节点，完成后在 report 节点汇合.

    Args:
        state: dispatch 节点完成后的工作流状态.

    Returns:
        两个 Send 对象，分别指向 legal_review 和 business_risk.
    """
    logger.info(
        "Fan-out: dispatch → [legal_review, business_risk] "
        f"(contract_type={state.get('contract_type', '?')})"
    )
    return [
        Send("legal_review", state),
        Send("business_risk", state),
    ]


def create_graph(
    llm: LLMClient,
    retriever: LegalRetriever,
    settings: Settings,
) -> StateGraph:
    """构建并编译审查工作流图.

    Args:
        llm: LLM 客户端实例.
        retriever: 法律知识检索器实例.
        settings: 应用配置.

    Returns:
        编译后的 LangGraph StateGraph，可通过 .invoke() 调用.
    """
    # ── 创建节点工厂（闭包注入依赖） ──────────────────────
    dispatch = create_dispatch_node(llm)
    legal_review = create_legal_review_node(llm, retriever)
    business_risk = create_business_risk_node(llm, retriever)

    # ── 构建图 ──────────────────────────────────────────
    builder = StateGraph(AgentState)

    # 注册节点
    builder.add_node("dispatch", dispatch)
    builder.add_node("legal_review", legal_review)
    builder.add_node("business_risk", business_risk)
    builder.add_node("report", report_node)

    # 边：START → dispatch
    builder.add_edge(START, "dispatch")

    # 条件边：dispatch → 并行 fan-out 到两个审查节点
    builder.add_conditional_edges(
        "dispatch",
        _fan_out_to_reviews,
        # path_map: Send 中的目标节点必须在列表中
        ["legal_review", "business_risk"],
    )

    # 两个审查节点都完成后 → report
    builder.add_edge("legal_review", "report")
    builder.add_edge("business_risk", "report")

    # report → END
    builder.add_edge("report", END)

    graph = builder.compile()
    logger.info("审查工作流图编译完成")
    return graph


def create_review_workflow(
    settings: Settings,
) -> StateGraph:
    """便捷工厂：从 Settings 创建完整的审查工作流.

    自动初始化 LLM 客户端、Embedding 模型、Milvus 连接和检索器.

    Args:
        settings: 应用配置.

    Returns:
        编译后的工作流图.
    """
    # LLM 客户端
    llm = LLMClient(settings.llm)

    # RAG 检索器
    from app.rag.embedding import EmbeddingModel
    from app.rag.milvus_client import MilvusManager

    embedding = EmbeddingModel(
        model_name=settings.embedding.model,
        device=settings.embedding.device,
    )
    milvus = MilvusManager(
        uri=settings.milvus.db_uri,
        db_name=settings.milvus.db_name,
        collection_name=settings.milvus.collection_name,
    )
    # 确保 Collection 已加载到内存（Milvus Lite 重启后需重新加载）
    if milvus.collection_exists():
        try:
            milvus.load_collection()
        except Exception:
            pass  # 已加载则忽略
    retriever = LegalRetriever(milvus=milvus, embedding=embedding)

    return create_graph(llm=llm, retriever=retriever, settings=settings)
