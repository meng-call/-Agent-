"""
LLM 客户端封装.

基于 OpenAI SDK，兼容 DeepSeek 等 OpenAI-API 兼容的 LLM 供应商。
Professional 规模：工厂模式 + streaming + retry + JSON mode。
"""

import json
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.core.config import LLMSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── 可重试的 HTTP 状态码 ────────────────────────────────

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # 秒

# HTML 响应特征（LLM API 偶尔返回 CDN/代理/错误页而非 JSON）
_HTML_SIGNATURES = (
    "<!doctype", "<html", "<head", "<body", "<script", "<meta",
    "<title", "<link ", "<div", "<span", "<table", "text/html",
)


def _looks_like_html(text: str) -> bool:
    """检测文本是否为 HTML 页面（而非 LLM 正常响应）."""
    if not text or not text.strip():
        return False
    lower = text.strip().lower()[:200]
    return any(sig in lower for sig in _HTML_SIGNATURES)


def _is_retryable(error: Exception) -> bool:
    """判断异常是否可重试."""
    # OpenAI SDK 的 APIStatusError 含 status_code 属性
    if hasattr(error, "status_code"):
        return getattr(error, "status_code") in _RETRYABLE_STATUS
    # 网络层异常（连接超时、DNS 等）可重试
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True
    # RateLimitError 也可重试
    type_name = type(error).__name__
    if "RateLimit" in type_name or "Timeout" in type_name:
        return True
    return False


def _backoff_delay(attempt: int) -> float:
    """指数退避：1s, 2s, 4s, 8s..."""
    return _BASE_DELAY * (2 ** (attempt - 1))


class LLMClient:
    """OpenAI-API 兼容的 LLM 客户端.

    Professional 规模特性：
    - 指数退避自动重试（429/5xx/网络异常）
    - JSON mode 支持（针对支持 response_format 的供应商）
    - 自动处理 JSON 包裹格式

    用法::

        settings = LLMSettings(api_key="...", model="deepseek-chat")
        client = LLMClient(settings)
        text = client.chat([{"role": "user", "content": "你好"}])
        data = client.chat_json([{"role": "user", "content": "返回JSON..."}])
    """

    def __init__(self, settings: LLMSettings) -> None:
        base_url = settings.base_url
        if not base_url:
            base_url = "https://api.deepseek.com/v1"

        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=base_url,
        )
        self.model = settings.model
        self.temperature = settings.temperature
        self.max_tokens = settings.max_tokens

    # ── 公开 API ──────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """发送聊天请求，含指数退避重试.

        Args:
            messages: OpenAI 格式消息列表.
            temperature: 覆盖默认 temperature.
            max_tokens: 覆盖默认 max_tokens.

        Returns:
            LLM 文本响应. 全部重试耗尽后返回空字符串.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 2):  # 1 initial + N retries
            try:
                return self._do_chat(messages, temperature, max_tokens)
            except Exception as e:
                last_error = e
                if attempt <= _MAX_RETRIES and _is_retryable(e):
                    delay = _backoff_delay(attempt)
                    logger.warning(
                        "llm.retry",
                        attempt=attempt,
                        max_retries=_MAX_RETRIES + 1,
                        delay=round(delay, 1),
                        error=str(e),
                    )
                    time.sleep(delay)
                else:
                    logger.error("llm.fatal_error", error=str(e))
                    break

        return ""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式聊天 — 同步生成器，逐 token 产出.

        用于 SSE (Server-Sent Events) 或逐块渲染场景.

        Args:
            messages: OpenAI 格式消息列表.
            temperature: 覆盖默认 temperature.
            max_tokens: 覆盖默认 max_tokens.

        Yields:
            每个 chunk 的增量文本 (str).
            网络错误时 yield "[STREAM_ERROR: ...]" 后终止.

        Usage::

            for chunk in client.chat_stream(messages):
                print(chunk, end="", flush=True)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.warning(f"流式调用失败: {e}")
            yield f"[STREAM_ERROR: {e}]"

    async def chat_stream_async(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式聊天 — 异步生成器.

        用于 FastAPI StreamingResponse SSE 场景.

        Usage::

            async for chunk in client.chat_stream_async(messages):
                yield f"data: {chunk}\\n\\n"
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.warning(f"流式调用失败: {e}")
            yield f"[STREAM_ERROR: {e}]"

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """发送聊天请求并解析 JSON 响应.

        优先使用 JSON mode（response_format），解析失败时回退到正则提取.

        Args:
            messages: OpenAI 格式消息列表.
            temperature: 覆盖默认 temperature.
            max_tokens: 覆盖默认 max_tokens.

        Returns:
            解析后的 JSON 字典. 解析失败时返回含 error 键的字典.
        """
        # 优先尝试 JSON mode
        text = self._do_chat_json_mode(messages, temperature, max_tokens)
        if not text:
            # 回退：标准 chat + 正则提取
            text = self.chat(messages, temperature=temperature, max_tokens=max_tokens)

        if not text:
            return {"error": "LLM 返回空响应"}

        try:
            return self._parse_json(text)
        except ValueError as e:
            # HTML 响应或其它非 JSON 内容
            logger.warning(f"响应非 JSON: {e}")
            return {"error": str(e), "raw_response": text[:2000]}
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}\n原始响应: {text[:500]}")
            return {"error": f"JSON 解析失败: {str(e)}", "raw_response": text[:2000]}

    # ── 内部实现 ──────────────────────────────────────────

    def _do_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """单次 LLM API 调用（不含重试）."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        content = response.choices[0].message.content or ""

        # 上游 API 有时返回 HTML 错误页而非正常文本
        if _looks_like_html(content):
            snippet = content.strip()[:200]
            logger.error("llm.html_response_detected", content_preview=snippet)
            raise RuntimeError(
                f"LLM API 返回了 HTML 页面而非正常响应"
                f"（可能原因：API 网关/代理错误、服务暂时不可用）。"
                f"响应片段: {snippet}"
            )

        return content

    def _do_chat_json_mode(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """尝试 JSON mode 调用.

        JSON mode 要求:
        - system/user prompt 中必须出现 "JSON" 一词
        - temperature 通常设为 0（确定性输出）
        - 部分供应商不支持，失败时返回空字符串.

        Returns:
            成功时返回文本，失败时返回空字符串让调用方回退.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,  # JSON mode 建议 temperature=0
                max_tokens=max_tokens or self.max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            # JSON mode 不支持时静默回退到标准 chat
            logger.debug(f"JSON mode 不可用，回退标准模式: {e}")
            return ""

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON 对象.

        支持三种格式：
        1. ```json ... ``` 代码块
        2. ``` ... ``` 无语言标记代码块
        3. 直接 { ... } JSON 对象

        嵌套 JSON 场景：当响应中包含多段 JSON 时，取包含 "risks" 或
        "contract_type" 等审查关键字段的 JSON 对象.

        Raises:
            json.JSONDecodeError: 无法提取有效 JSON.
            ValueError: 检测到 HTML 响应而非 JSON.
        """
        # 提早检测 HTML — 上游 API/代理偶尔返回错误页
        if _looks_like_html(text):
            raise ValueError(
                f"响应是 HTML 页面而非 JSON。可能是 API 网关/代理返回了错误页。"
                f"响应片段: {text.strip()[:300]}"
            )

        # 尝试匹配 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # 尝试匹配所有顶级 JSON 对象
        candidates = list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text))
        if len(candidates) == 1:
            return json.loads(candidates[0].group(0))
        elif len(candidates) > 1:
            # 多个 JSON 对象：选包含审查关键字段的那个
            review_keys = {"risks", "contract_type", "risk_level", "summary",
                           "overall_assessment", "recommendation"}
            for candidate in candidates:
                try:
                    obj = json.loads(candidate.group(0))
                    if any(k in obj for k in review_keys):
                        return obj
                except json.JSONDecodeError:
                    continue

        # 最后尝试整体匹配
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        raise json.JSONDecodeError("无法提取 JSON", text, 0)
