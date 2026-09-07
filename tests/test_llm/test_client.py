"""
LLM 客户端单元测试 — JSON 解析 + 重试逻辑.
"""

import json

import pytest

from app.llm.client import _backoff_delay, _is_retryable, LLMClient


class TestBackoffDelay:
    """指数退避延迟计算."""

    def test_first_attempt(self):
        """第 1 次重试延迟 1s."""
        assert _backoff_delay(1) == 1.0

    def test_second_attempt(self):
        """第 2 次重试延迟 2s."""
        assert _backoff_delay(2) == 2.0

    def test_third_attempt(self):
        """第 3 次重试延迟 4s."""
        assert _backoff_delay(3) == 4.0

    def test_fourth_attempt(self):
        """第 4 次重试延迟 8s."""
        assert _backoff_delay(4) == 8.0


class TestIsRetryable:
    """可重试异常判断."""

    def test_429_retryable(self):
        """429 Rate Limit 可重试."""
        err = Exception("rate limit")
        err.status_code = 429
        assert _is_retryable(err)

    def test_500_retryable(self):
        """500 Internal Server Error 可重试."""
        err = Exception("server error")
        err.status_code = 500
        assert _is_retryable(err)

    def test_502_retryable(self):
        """502 Bad Gateway 可重试."""
        err = Exception()
        err.status_code = 502
        assert _is_retryable(err)

    def test_503_retryable(self):
        """503 Service Unavailable 可重试."""
        err = Exception()
        err.status_code = 503
        assert _is_retryable(err)

    def test_504_retryable(self):
        """504 Gateway Timeout 可重试."""
        err = Exception()
        err.status_code = 504
        assert _is_retryable(err)

    def test_400_not_retryable(self):
        """400 Bad Request 不可重试."""
        err = Exception()
        err.status_code = 400
        assert not _is_retryable(err)

    def test_401_not_retryable(self):
        """401 Unauthorized 不可重试."""
        err = Exception()
        err.status_code = 401
        assert not _is_retryable(err)

    def test_404_not_retryable(self):
        """404 Not Found 不可重试."""
        err = Exception()
        err.status_code = 404
        assert not _is_retryable(err)

    def test_connection_error_retryable(self):
        """网络连接异常可重试."""
        assert _is_retryable(ConnectionError("timeout"))
        assert _is_retryable(TimeoutError("timeout"))

    def test_rate_limit_by_name(self):
        """异常类名含 'RateLimit' 可重试."""

        class RateLimitError(Exception):
            pass

        assert _is_retryable(RateLimitError())

    def test_timeout_by_name(self):
        """异常类名含 'Timeout' 可重试."""

        class RequestTimeoutError(Exception):
            pass

        assert _is_retryable(RequestTimeoutError())

    def test_normal_exception_not_retryable(self):
        """普通异常不可重试."""
        assert not _is_retryable(ValueError("bad value"))
        assert not _is_retryable(KeyError("missing key"))


class TestParseJson:
    """JSON 解析策略测试."""

    def test_code_block_json(self):
        """"```json ... ```" 代码块解析."""
        text = '```json\n{"risks": [{"risk_name": "test"}]}\n```'
        result = LLMClient._parse_json(text)
        assert result["risks"][0]["risk_name"] == "test"

    def test_code_block_no_language(self):
        """"``` ... ```" 无语言标记代码块."""
        text = '```\n{"contract_type": "买卖合同"}\n```'
        result = LLMClient._parse_json(text)
        assert result["contract_type"] == "买卖合同"

    def test_direct_json(self):
        """直接 JSON 对象."""
        text = '{"risks": [], "summary": "无风险"}'
        result = LLMClient._parse_json(text)
        assert result["risks"] == []
        assert result["summary"] == "无风险"

    def test_json_with_surrounding_text(self):
        """JSON 嵌入在普通文本中."""
        text = '以下是分析结果：\n{"contract_type": "租赁合同", "confidence": 0.9}\n请审核。'
        result = LLMClient._parse_json(text)
        assert result["contract_type"] == "租赁合同"
        assert result["confidence"] == 0.9

    def test_multiple_json_selects_review_keys(self):
        """多个 JSON 对象时选择含审查关键字段的."""
        text = (
            '{"a": 1}'
            '{"risks": [{"risk_name": "违约金过高"}], "summary": "需修改"}'
            '{"b": 2}'
        )
        result = LLMClient._parse_json(text)
        assert "risks" in result
        assert result["risks"][0]["risk_name"] == "违约金过高"

    def test_invalid_json_raises(self):
        """无效 JSON 引发异常."""
        with pytest.raises((json.JSONDecodeError, ValueError)):
            LLMClient._parse_json("这不是JSON")

    def test_empty_string_raises(self):
        """空字符串."""
        with pytest.raises((json.JSONDecodeError, ValueError)):
            LLMClient._parse_json("")
