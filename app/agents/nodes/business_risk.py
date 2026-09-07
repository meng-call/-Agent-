"""
商业风险节点 — 合同商业公平性评估.

基于合同文本 + LLM 评估条款的商业公平性和交易风险，
按照三层分析法（宏观→中观→微观）识别商业风险并给出谈判建议和签署结论。
"""

from pathlib import Path
from typing import Any, Dict

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.llm.client import LLMClient
from app.rag.retriever import LegalRetriever

logger = get_logger(__name__)


def _load_prompt() -> str:
    """加载 business_risk agent 的 system prompt."""
    prompt_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "config" / "agents" / "business_risk.md"
    )
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning(f"Prompt 文件未找到: {prompt_path}")
    return "你是商业风险分析师，评估合同条款的商业公平性并输出 JSON。"


def _get_business_law_category(contract_type: str) -> str:
    """映射合同类型到法律类别（商业风险侧重经济法规）."""
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
    """构建检索查询 — 侧重商业条款."""
    contract_type = state.get("contract_type", "")
    sub_type = state.get("contract_sub_type", "")
    contract_text = state.get("contract_text", "")
    query = f"{contract_type} {sub_type} 商业风险 违约责任 付款条款 权利义务 责任上限 {contract_text[:800]}"
    return query


def create_business_risk_node(llm: LLMClient, retriever: LegalRetriever):
    """创建商业风险节点（闭包注入 LLM 客户端 + 检索器）.

    Args:
        llm: LLMClient 实例.
        retriever: LegalRetriever 实例.

    Returns:
        可放入 LangGraph 的节点函数.
    """
    system_prompt = _load_prompt()

    def business_risk_node(state: AgentState) -> Dict[str, Any]:
        """执行商业风险评估."""
        contract_text = state.get("contract_text", "")
        if not contract_text:
            logger.warning("合同文本为空，跳过商业风险评估")
            return {
                "business_risks": [],
                "business_assessment": "合同文本为空，无法评估",
                "business_recommendation": "",
                "business_overall_conclusion": "不建议签",
                "business_preconditions": [],
            }

        logger.info("BusinessRisk: 开始三层商业风险评估...")

        # Step 1: RAG 检索相关法律条文（作为评估基准，含类别预过滤）
        query = _build_retrieval_query(state)
        law_cat = _get_business_law_category(state.get("contract_type", ""))
        legal_context = retriever.retrieve_context(
            query, top_k=5, filter_category=law_cat or None,
        )
        logger.info("business_risk.retrieved", context_len=len(legal_context))

        # Step 2: 组装 prompt（含合同类型信息）
        contract_type = state.get("contract_type", "未知")
        sub_type = state.get("contract_sub_type", "")
        suggested_focus = state.get("contract_suggested_focus", "")

        type_hint = f"合同类型: {contract_type}"
        if sub_type:
            type_hint += f"（{sub_type}）"

        user_prompt = f"""## {type_hint}

## 建议审查重点
{suggested_focus or "请按照三层分析法全面评估"}

## 合同文本

{contract_text}

## 相关法律条文参考

{legal_context}

请按照三层分析法（宏观→中观→微观）从商业角度评估合同条款，输出 JSON 格式结果。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Step 3: 调用 LLM
        result = llm.chat_json(messages, temperature=0.3)

        if "error" in result:
            logger.error(f"BusinessRisk LLM 调用失败: {result['error']}")
            return {
                "business_risks": [],
                "business_assessment": f"评估失败: {result.get('error', '')}",
                "business_recommendation": "",
                "business_overall_conclusion": "不建议签",
                "business_preconditions": [],
                "error": result.get("error", ""),
            }

        risks = result.get("risks", [])
        assessment = result.get("overall_assessment", "")
        recommendation = result.get("recommendation", "")
        conclusion = result.get("overall_conclusion", "有条件可签")
        preconditions = result.get("preconditions", [])

        # 统计各层风险
        macro = sum(1 for r in risks if r.get("layer") == "宏观层")
        meso = sum(1 for r in risks if r.get("layer") == "中观层")
        micro = sum(1 for r in risks if r.get("layer") == "微观层")

        logger.info(
            "business_risk.completed",
            risk_count=len(risks),
            layer_macro=macro,
            layer_meso=meso,
            layer_micro=micro,
            conclusion=conclusion,
        )
        return {
            "business_risks": risks,
            "business_assessment": assessment,
            "business_recommendation": recommendation,
            "business_overall_conclusion": conclusion,
            "business_preconditions": preconditions,
        }

    return business_risk_node
