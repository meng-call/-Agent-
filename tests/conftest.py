"""
合约风控审查 Agent 系统 — 共享 pytest fixtures.
"""

import pytest


@pytest.fixture
def sample_contract_text() -> str:
    """一份简化的买卖合同样例."""
    return """买卖合同

甲方（卖方）：XX科技有限公司
乙方（买方）：YY贸易有限公司

第一条 标的物
甲方向乙方出售XX型号服务器100台。

第二条 价款
每台人民币50000元，总价款人民币5000000元。

第三条 交付
甲方应于2024年3月1日前将全部货物交付至乙方指定地点。

第四条 付款方式
乙方应于收到货物后30日内支付全部价款。

第五条 违约责任
任何一方违反本合同约定，应向对方支付违约金人民币500000元。

第六条 争议解决
因本合同引起的争议，双方应友好协商解决；协商不成的，提交北京仲裁委员会仲裁。"""


@pytest.fixture
def sample_legal_risks() -> list:
    """模拟法律审查产出的风险列表."""
    return [
        {
            "risk_name": "违约金可能超过法定上限",
            "risk_level": "P0",
            "risk_consequence": "违约金条款可能被法院调减",
            "related_clause": "第五条 违约责任",
            "legal_basis": "《民法典》第585条",
            "criteria": "违约金超过实际损失30%",
            "example": "某案违约金被调减至实际损失1.3倍",
            "recommended_wording": "违约金不超过实际损失的30%",
            "remediation": "将违约金比例下调",
            "layer": "微观层",
        },
        {
            "risk_name": "争议解决条款约定不明",
            "risk_level": "P1",
            "risk_consequence": "仲裁机构选择可能无效",
            "related_clause": "第六条 争议解决",
            "legal_basis": "《仲裁法》第16条",
            "criteria": "仲裁机构名称不明确",
            "example": "",
            "recommended_wording": "提交北京仲裁委员会/北京国际仲裁中心",
            "remediation": "明确仲裁机构全称",
            "layer": "微观层",
        },
        {
            "risk_name": "标的物规格描述不完整",
            "risk_level": "P2",
            "risk_consequence": "可能引发交付争议",
            "related_clause": "第一条 标的物",
            "legal_basis": "",
            "criteria": "缺少技术规格参数",
            "example": "",
            "recommended_wording": "增加附件明确技术规格",
            "remediation": "补充技术规格附件",
            "layer": "中观层",
        },
    ]


@pytest.fixture
def sample_business_risks() -> list:
    """模拟商业审查产出的风险列表."""
    return [
        {
            "risk_name": "付款周期过长",
            "risk_level": "P0",
            "risk_consequence": "30天账期增加现金流压力",
            "related_clause": "第四条 付款方式",
            "criteria": "行业惯例为货到15日内付款",
            "example": "某供应商因30天账期导致现金流断裂",
            "recommended_wording": "收到货物后15日内支付",
            "negotiation_priority": "必须谈判修改",
            "detail": "30天账期超出行业惯例，建议缩短至15天",
            "layer": "微观层",
        },
    ]


@pytest.fixture
def sample_state(sample_contract_text, sample_legal_risks, sample_business_risks) -> dict:
    """模拟完整的 AgentState."""
    return {
        "contract_text": sample_contract_text,
        "contract_type": "买卖合同",
        "contract_sub_type": "动产买卖",
        "contract_category_id": 1,
        "contract_type_confidence": 0.92,
        "contract_type_analysis": "具备买卖合同的典型要素",
        "contract_key_features": ["标的物", "价款", "交付", "违约责任"],
        "contract_suggested_focus": "关注违约金条款合规性",
        "legal_risks": sample_legal_risks,
        "legal_summary": "共发现3个风险项，其中P0:1个",
        "legal_overall_conclusion": "有条件可签",
        "legal_preconditions": ["修改违约金条款"],
        "business_risks": sample_business_risks,
        "business_assessment": "付款条件需要谈判",
        "business_recommendation": "建议将付款周期缩短至15天",
        "business_overall_conclusion": "有条件可签",
        "business_preconditions": ["协商缩短付款周期"],
    }
