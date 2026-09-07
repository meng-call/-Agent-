"""
合约风控审查 Agent 系统 — LLM 客户端模块.

基于 OpenAI SDK，兼容 DeepSeek 等 OpenAI-API 兼容的 LLM 供应商。
"""

from app.llm.client import LLMClient

__all__ = ["LLMClient"]
