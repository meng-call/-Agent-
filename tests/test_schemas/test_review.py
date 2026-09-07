"""
API Schema 验证测试.
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import APIResponse
from app.schemas.review import (
    ReviewData,
    ReviewMeta,
    ReviewRequest,
    ReviewResponse,
    ReviewSection,
    ReviewVerdict,
    RiskItem,
)


class TestReviewRequest:
    """审查请求 Schema."""

    def test_valid_request(self):
        """合法请求."""
        req = ReviewRequest(contract_text="甲方与乙方达成如下协议...")
        assert len(req.contract_text) > 0

    def test_empty_text_rejected(self):
        """空文本被拒绝."""
        with pytest.raises(ValidationError):
            ReviewRequest(contract_text="")

    def test_optional_contract_name(self):
        """合同名称可选."""
        req = ReviewRequest(contract_text="test", contract_name="采购合同")
        assert req.contract_name == "采购合同"

        req2 = ReviewRequest(contract_text="test")
        assert req2.contract_name is None

    def test_text_too_long(self):
        """超长文本被拒绝（>200000 字符）."""
        with pytest.raises(ValidationError):
            ReviewRequest(contract_text="x" * 200_001)


class TestRiskItem:
    """风险项 Schema."""

    def test_minimal_fields(self):
        """仅有必填字段."""
        r = RiskItem(
            risk_name="违约金过高",
            risk_level="P0",
            risk_consequence="可能被法院调减",
        )
        assert r.risk_name == "违约金过高"
        assert r.risk_level == "P0"
        assert r.layer == "微观层"  # 默认值

    def test_full_fields(self):
        """所有字段."""
        r = RiskItem(
            risk_name="违约金过高",
            risk_level="P0",
            risk_consequence="可能被法院调减",
            related_clause="第5条",
            layer="微观层",
            legal_basis="《民法典》第585条",
            criteria="超过实际损失30%",
            example="某案例...",
            recommended_wording="不超过实际损失30%",
            remediation="下调违约金比例",
            negotiation_priority="必须修改",
            detail="详细分析...",
        )
        assert r.legal_basis == "《民法典》第585条"
        assert r.negotiation_priority == "必须修改"


class TestReviewVerdict:
    """审查结论 Schema."""

    def test_valid_verdict(self):
        v = ReviewVerdict(
            final_conclusion="有条件可签",
            legal_conclusion="有条件可签",
            business_conclusion="可签",
        )
        assert v.final_conclusion == "有条件可签"
        assert v.preconditions == []


class TestAPIResponse:
    """通用响应 Schema."""

    def test_ok(self):
        """成功响应工厂."""
        resp = APIResponse.ok(data={"id": 1})
        assert resp.code == 0
        assert resp.message == "success"
        assert resp.data == {"id": 1}

    def test_error(self):
        """错误响应工厂."""
        resp = APIResponse.error("服务不可用", code=503)
        assert resp.code == 503
        assert resp.message == "服务不可用"
        assert resp.data is None

    def test_generic_type(self):
        """泛型类型正确."""
        resp = APIResponse[str].ok(data="hello")
        assert resp.data == "hello"
