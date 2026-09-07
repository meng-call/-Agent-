"""
法律审查节点 — 合同合规性检查.

基于 RAG 检索的法律条文 + LLM 审查合同条款是否合规，
按照三层分析法（宏观→中观→微观）识别法律风险并给出修订建议和签署结论。
"""

from pathlib import Path
from typing import Any, Dict

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.llm.client import LLMClient
from app.rag.retriever import LegalRetriever

logger = get_logger(__name__)


def _load_prompt() -> str:
    """加载 legal_review agent 的 system prompt."""
    prompt_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "config" / "agents" / "legal_review.md"
    )
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning(f"Prompt 文件未找到: {prompt_path}")
    return "你是合同法律审查专家，检查合同合规性并输出 JSON。"


def _get_law_category_for_contract_type(contract_type: str) -> str:
    """映射合同类型到法律类别，用于 Milvus 元数据预过滤.

    缩小检索范围，避免检索到完全不相关的法律领域条文.
    """
    mapping = {
        "买卖合同": "民法-合同编",
        "租赁合同": "民法-合同编",
        "服务类合同": "民法-合同编",
        "知识产权类合同": "知识产权法",
        "担保类合同": "民法-担保",
        "借贷与赠与合同": "民法-合同编",
        "互联网协议": "电子商务法",
        "婚姻家事类合同": "婚姻家庭法",
        "劳动用工类合同": "劳动法",
        "房地产类合同": "房地产法",
        "建设工程类合同": "建设工程法",
        "公司投资类合同": "公司法",
    }
    return mapping.get(contract_type, "")


def _build_retrieval_query(state: AgentState) -> str:
    """构建 RAG 检索查询 — 融入合同类型和关键特征."""
    contract_type = state.get("contract_type", "")
    sub_type = state.get("contract_sub_type", "")
    suggested_focus = state.get("contract_suggested_focus", "")
    contract_text = state.get("contract_text", "")

    # 用合同类型 + 审查重点 + 前 800 字作为检索查询
    parts = [p for p in [contract_type, sub_type, suggested_focus] if p]
    query = " ".join(parts) + f" {contract_text[:800]}"
    return query


def create_legal_review_node(llm: LLMClient, retriever: LegalRetriever):
    """创建法律审查节点（闭包注入 LLM 客户端 + 检索器）.

    Args:
        llm: LLMClient 实例.
        retriever: LegalRetriever 实例.

    Returns:
        可放入 LangGraph 的节点函数.
    """
    system_prompt = _load_prompt()

    def legal_review_node(state: AgentState) -> Dict[str, Any]:
        """执行法律合规审查."""
        contract_text = state.get("contract_text", "")
        if not contract_text:
            logger.warning("合同文本为空，跳过法律审查")
            return {
                "legal_risks": [],
                "legal_summary": "合同文本为空，无法审查",
                "legal_overall_conclusion": "不建议签",
                "legal_preconditions": [],
            }

        logger.info("LegalReview: 开始三层法律合规审查...")

        # Step 1: RAG 检索相关法律条文（含类别预过滤）
        query = _build_retrieval_query(state)
        law_cat = _get_law_category_for_contract_type(
            state.get("contract_type", "")
        )
        legal_context = retriever.retrieve_context(
            query, top_k=5, filter_category=law_cat or None,
        )
        logger.info("legal_review.retrieved", context_len=len(legal_context))

        # Step 2: 组装 prompt（含合同类型信息供三层分析参考）
        contract_type = state.get("contract_type", "未知")
        sub_type = state.get("contract_sub_type", "")
        suggested_focus = state.get("contract_suggested_focus", "")

        type_hint = f"合同类型: {contract_type}"
        if sub_type:
            type_hint += f"（{sub_type}）"

        user_prompt = f"""## {type_hint}

## 建议审查重点
{suggested_focus or "请按照三层分析法全面审查"}

## 合同文本

{contract_text}

## 相关法律条文

{legal_context}

请按照三层分析法（宏观→中观→微观）逐条审查合同合规性，输出 JSON 格式结果。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Step 3: 调用 LLM
        result = llm.chat_json(messages, temperature=0.2)

        if "error" in result:
            logger.error(f"LegalReview LLM 调用失败: {result['error']}")
            return {
                "legal_risks": [],
                "legal_summary": f"审查失败: {result.get('error', '')}",
                "legal_overall_conclusion": "不建议签",
                "legal_preconditions": [],
                "error": result.get("error", ""),
            }

        risks = result.get("risks", [])
        summary = result.get("summary", "")
        conclusion = result.get("overall_conclusion", "有条件可签")
        preconditions = result.get("preconditions", [])

        # 统计各层风险
        macro = sum(1 for r in risks if r.get("layer") == "宏观层")
        meso = sum(1 for r in risks if r.get("layer") == "中观层")
        micro = sum(1 for r in risks if r.get("layer") == "微观层")

        logger.info(
            "legal_review.completed",
            risk_count=len(risks),
            layer_macro=macro,
            layer_meso=meso,
            layer_micro=micro,
            conclusion=conclusion,
        )
        return {
            "legal_risks": risks,
            "legal_summary": summary,
            "legal_overall_conclusion": conclusion,
            "legal_preconditions": preconditions,
        }

    return legal_review_node
