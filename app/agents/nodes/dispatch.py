"""
调度节点 — 合同类型识别.

读取合同文本，通过 LLM 判断合同类型（固定 12 类），
为下游审查节点提供分类信息和建议审查重点。
"""

from pathlib import Path
from typing import Any, Dict

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.llm.client import LLMClient

logger = get_logger(__name__)


def _load_prompt() -> str:
    """加载 dispatch agent 的 system prompt."""
    prompt_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "config" / "agents" / "dispatch.md"
    )
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning(f"Prompt 文件未找到: {prompt_path}")
    return "你是一个合同类型分析专家，判断合同类型并输出 JSON。"


def create_dispatch_node(llm: LLMClient):
    """创建调度节点（闭包注入 LLM 客户端）.

    Args:
        llm: LLMClient 实例.

    Returns:
        可放入 LangGraph 的节点函数.
    """
    system_prompt = _load_prompt()

    def dispatch_node(state: AgentState) -> Dict[str, Any]:
        """识别合同类型，写入 state."""
        contract_text = state.get("contract_text", "")
        if not contract_text:
            logger.warning("合同文本为空，跳过类型识别")
            return {
                "contract_type": "未知",
                "contract_type_confidence": 0.0,
                "contract_type_analysis": "合同文本为空",
                "contract_sub_type": "",
                "contract_category_id": 0,
                "contract_key_features": [],
                "contract_suggested_focus": "",
            }

        logger.info("dispatch.started", text_len=len(contract_text))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": contract_text},
        ]

        result = llm.chat_json(messages, temperature=0.1)

        if "error" in result:
            logger.error("dispatch.llm_failed", error=result.get("error", ""))
            return {
                "contract_type": "未知",
                "contract_type_confidence": 0.0,
                "contract_type_analysis": f"LLM 错误: {result.get('error', '')}",
                "contract_sub_type": "",
                "contract_category_id": 0,
                "contract_key_features": [],
                "contract_suggested_focus": "",
                "error": result.get("error", ""),
            }

        contract_type = result.get("contract_type", "未知")
        sub_type = result.get("sub_type", "")
        category_id = result.get("category_id", 0)
        confidence = result.get("confidence", 0.0)
        analysis = result.get("analysis", "")
        key_features = result.get("key_features", [])
        suggested_focus = result.get("suggested_focus", "")

        logger.info(
            "dispatch.completed",
            contract_type=contract_type,
            sub_type=sub_type,
            category_id=category_id,
            confidence=round(confidence, 2),
        )
        return {
            "contract_type": contract_type,
            "contract_sub_type": sub_type,
            "contract_category_id": category_id,
            "contract_type_confidence": confidence,
            "contract_type_analysis": analysis,
            "contract_key_features": key_features,
            "contract_suggested_focus": suggested_focus,
        }

    return dispatch_node
