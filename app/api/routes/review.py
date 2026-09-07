"""
合约风控审查 Agent 系统 — 合同审查 API 端点.

POST /api/review        — 文本直接审查
POST /api/review/upload — 文件上传审查（PDF/DOCX）
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from langgraph.graph import StateGraph

from app.api.deps import get_settings, get_workflow
from app.core.config import Settings
from app.core.logging import get_logger
from app.parsers.base import BaseParser
from app.schemas.review import (
    ReviewData,
    ReviewMeta,
    ReviewRequest,
    ReviewResponse,
    ReviewSection,
    ReviewStatistics,
    ReviewVerdict,
    RiskItem,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["review"])

# 文件上传限制：10MB
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


# ── 辅助函数 ────────────────────────────────────────────────────────

def _pick_parser(file_path: Path) -> BaseParser:
    """选择最佳解析器：Docling 优先，pdfplumber/docx 回退."""
    suffix = file_path.suffix.lower()

    # 尝试 Docling（统一解析，布局理解更好）
    try:
        from app.parsers.docling_parser import DoclingParser
        docling = DoclingParser()
        if docling.is_available():
            logger.debug("使用 Docling 解析器")
            return docling
    except Exception:
        pass

    # 回退到轻量解析器
    if suffix == ".pdf":
        from app.parsers.pdf_parser import PDFParser
        return PDFParser()
    elif suffix == ".docx":
        from app.parsers.docx_parser import DocxParser
        return DocxParser()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}，支持 {', '.join(sorted(_SUPPORTED_EXTENSIONS))}",
        )


async def _parse_uploaded_file(file: UploadFile) -> str:
    """解析上传的文件为纯文本.

    Args:
        file: FastAPI UploadFile 对象.

    Returns:
        提取的纯文本.

    Raises:
        HTTPException: 文件格式不支持或解析失败.
    """
    # 1. 校验扩展名
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}，支持 {', '.join(sorted(_SUPPORTED_EXTENSIONS))}",
        )

    # 2. 读取文件内容（带大小限制）
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小 {len(content) / 1024 / 1024:.1f}MB 超出上限 10MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    # 3. 写入临时文件供解析器使用
    with tempfile.NamedTemporaryFile(
        suffix=suffix,
        delete=False,
        prefix="contract_upload_",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        parser = _pick_parser(tmp_path)
        text = await parser.parse(tmp_path)
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="文件解析结果为空，请检查文件是否包含可提取的文本")
        logger.info("file.parsed", filename=file.filename, text_len=len(text))
        return text
    except HTTPException:
        raise
    except Exception as e:
        logger.error("file.parse_failed", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail=f"文件解析失败: {e}")
    finally:
        # 清理临时文件
        try:
            tmp_path.unlink()
        except Exception:
            pass


def _transform_report(raw_report: Dict[str, Any]) -> ReviewData:
    """将工作流产出的 raw final_report dict 转换为 ReviewData Schema.

    处理 LLM 返回字段与 Schema 之间的差异，确保响应格式稳定.
    """
    meta = raw_report.get("meta", {})
    verdict = raw_report.get("verdict", {})
    stats = raw_report.get("statistics", {})
    legal = raw_report.get("legal_review", {})
    business = raw_report.get("business_review", {})

    # 转换风险项
    def _to_risk_items(risks: list) -> list[RiskItem]:
        items: list[RiskItem] = []
        for r in (risks or []):
            try:
                items.append(RiskItem(
                    risk_name=r.get("risk_name", "未命名风险"),
                    risk_level=r.get("risk_level", "P2"),
                    risk_consequence=r.get("risk_consequence", ""),
                    related_clause=r.get("related_clause", ""),
                    layer=r.get("layer", "微观层"),
                    legal_basis=r.get("legal_basis"),
                    criteria=r.get("criteria"),
                    example=r.get("example"),
                    recommended_wording=r.get("recommended_wording"),
                    remediation=r.get("remediation"),
                    negotiation_priority=r.get("negotiation_priority"),
                    detail=r.get("detail"),
                ))
            except Exception as e:
                logger.warning("risk_item.transform_skipped", error=str(e))
        return items

    return ReviewData(
        meta=ReviewMeta(
            contract_type=meta.get("contract_type", "未知"),
            contract_sub_type=meta.get("contract_sub_type", ""),
            contract_category_id=meta.get("contract_category_id", 0),
            contract_type_confidence=meta.get("contract_type_confidence", 0.0),
            contract_type_analysis=meta.get("contract_type_analysis", ""),
            contract_key_features=meta.get("contract_key_features", []),
            contract_suggested_focus=meta.get("contract_suggested_focus", ""),
        ),
        verdict=ReviewVerdict(
            final_conclusion=verdict.get("final_conclusion", "有条件可签"),
            legal_conclusion=verdict.get("legal_conclusion", ""),
            business_conclusion=verdict.get("business_conclusion", ""),
            preconditions=verdict.get("preconditions", []),
            reasoning=verdict.get("reasoning", ""),
        ),
        statistics=ReviewStatistics(
            total_risks=stats.get("total_risks", 0),
            by_level=stats.get("by_level", {}),
            legal=stats.get("legal", {}),
            business=stats.get("business", {}),
        ),
        legal_review=ReviewSection(
            risks=_to_risk_items(legal.get("risks", [])),
            summary=legal.get("summary", ""),
        ),
        business_review=ReviewSection(
            risks=_to_risk_items(business.get("risks", [])),
            summary=business.get("overall_assessment", ""),
            overall_assessment=business.get("overall_assessment"),
            recommendation=business.get("recommendation"),
        ),
        has_error=raw_report.get("has_error", False),
        error=raw_report.get("error"),
    )


async def _run_review(contract_text: str, workflow: StateGraph, settings: Settings) -> ReviewData:
    """执行审查工作流并转换为 API 响应格式.

    Args:
        contract_text: 合同纯文本.
        workflow: 已初始化的 LangGraph 工作流.
        settings: 应用配置.

    Returns:
        ReviewData 结构化响应.
    """
    logger.info("review.started", text_len=len(contract_text))

    try:
        raw_state = workflow.invoke({"contract_text": contract_text})
    except Exception as e:
        logger.error("review.workflow_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"审查工作流执行失败: {e}")

    final_report = raw_state.get("final_report")
    if not final_report:
        raise HTTPException(status_code=500, detail="审查工作流未返回有效报告")

    result = _transform_report(final_report)
    logger.info(
        "review.completed",
        conclusion=result.verdict.final_conclusion,
        total_risks=result.statistics.total_risks,
    )
    return result


async def _persist_review(
    contract_text: str,
    review_data: ReviewData,
    filename: Optional[str],
) -> None:
    """将审查结果持久化到 MySQL（不阻塞 API 响应）.

    数据库不可用时静默跳过，仅记录警告日志.
    """
    try:
        from app.core.config import load_settings
        from app.db.session import _get_session_factory
        from app.models import ContractRecord, ReviewRecord, RiskRecord

        settings = load_settings()
        if not settings.mysql.password or not settings.mysql.host:
            logger.debug("persist.skipped", reason="MySQL 未配置")
            return

        factory = _get_session_factory(settings.mysql)

        async with factory() as session:
            meta = review_data.meta
            verdict = review_data.verdict

            # 合同记录
            contract = ContractRecord(
                contract_text=contract_text,
                contract_type=meta.contract_type,
                contract_sub_type=meta.contract_sub_type,
                original_filename=filename,
                text_length=len(contract_text),
            )
            session.add(contract)
            await session.flush()  # 获取 contract.id

            # 审查记录
            review = ReviewRecord(
                contract_id=contract.id,
                final_conclusion=verdict.final_conclusion,
                legal_conclusion=verdict.legal_conclusion,
                business_conclusion=verdict.business_conclusion,
                total_risks=review_data.statistics.total_risks,
                preconditions=verdict.preconditions or [],
                reasoning=verdict.reasoning,
                meta_snapshot={
                    "contract_type": meta.contract_type,
                    "contract_sub_type": meta.contract_sub_type,
                    "contract_category_id": meta.contract_category_id,
                    "contract_type_confidence": meta.contract_type_confidence,
                    "contract_type_analysis": meta.contract_type_analysis,
                    "contract_key_features": meta.contract_key_features,
                    "contract_suggested_focus": meta.contract_suggested_focus,
                },
            )
            session.add(review)
            await session.flush()

            # 法律风险项
            for risk in review_data.legal_review.risks:
                session.add(RiskRecord(
                    review_id=review.id,
                    risk_name=risk.risk_name,
                    risk_level=risk.risk_level,
                    risk_consequence=risk.risk_consequence,
                    related_clause=risk.related_clause,
                    layer=risk.layer,
                    review_category="legal",
                    legal_basis=risk.legal_basis,
                    criteria=risk.criteria,
                    example=risk.example,
                    recommended_wording=risk.recommended_wording,
                    remediation=risk.remediation,
                ))

            # 商业风险项
            for risk in review_data.business_review.risks:
                session.add(RiskRecord(
                    review_id=review.id,
                    risk_name=risk.risk_name,
                    risk_level=risk.risk_level,
                    risk_consequence=risk.risk_consequence,
                    related_clause=risk.related_clause,
                    layer=risk.layer,
                    review_category="business",
                    negotiation_priority=risk.negotiation_priority,
                    detail=risk.detail,
                ))

            await session.commit()
            logger.info(
                "persist.completed",
                contract_id=contract.id,
                review_id=review.id,
                total_risks=review.total_risks,
            )
    except Exception as e:
        logger.warning("persist.failed", error=str(e)[:200])


# ── 端点 ────────────────────────────────────────────────────────────

@router.post(
    "/review",
    response_model=ReviewResponse,
    summary="合同审查（文本）",
    description="提交合同文本，执行多 Agent 审查工作流，返回结构化审查报告。",
)
async def review_text(
    body: ReviewRequest,
    background_tasks: BackgroundTasks,
    workflow: StateGraph = Depends(get_workflow),
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    """文本合同审查."""
    contract_text = body.contract_text.strip()
    if not contract_text:
        raise HTTPException(status_code=422, detail="contract_text 不能为空")

    data = await _run_review(contract_text, workflow, settings)

    # 后台持久化（不阻塞响应）
    background_tasks.add_task(
        _persist_review,
        contract_text=contract_text,
        review_data=data,
        filename=None,
    )
    return ReviewResponse(code=0, message="success", data=data)


@router.post(
    "/review/upload",
    response_model=ReviewResponse,
    summary="合同审查（文件上传）",
    description="上传 PDF 或 DOCX 合同文件，自动解析文本后执行审查工作流。",
)
async def review_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="合同文件（PDF 或 DOCX，≤10MB）"),
    workflow: StateGraph = Depends(get_workflow),
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    """文件上传合同审查."""
    # 1. 解析上传文件
    contract_text = await _parse_uploaded_file(file)

    # 2. 执行审查
    data = await _run_review(contract_text, workflow, settings)

    # 后台持久化
    background_tasks.add_task(
        _persist_review,
        contract_text=contract_text,
        review_data=data,
        filename=file.filename,
    )
    return ReviewResponse(code=0, message="success", data=data)


@router.get(
    "/review/health",
    summary="审查服务健康检查",
    description="检查审查工作流是否已初始化并可调用。",
)
async def review_health(
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """审查模块健康检查 — 验证工作流是否就绪."""
    try:
        workflow = get_workflow()
        return {
            "status": "ok",
            "workflow_ready": workflow is not None,
            "llm_model": settings.llm.model,
            "llm_provider": settings.llm.provider,
        }
    except Exception as e:
        return {
            "status": "error",
            "workflow_ready": False,
            "error": str(e),
        }
