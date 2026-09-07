# 合约风控审查 Agent 系统 — 架构说明

## 分层架构

```
┌─────────────────────────────────────────────┐
│  API 层 (app/api/)                           │
│  FastAPI routes, middleware, error handlers   │
├─────────────────────────────────────────────┤
│  服务层 (services/)                          │
│  业务编排：解析 → 审查 → 报告 → 持久化        │
├──────────┬──────────┬──────────┬────────────┤
│ Agent 层 │ RAG 层    │ 解析层   │ 数据库层    │
│ LangGraph│ Milvus    │ PDF/DOCX │ MySQL       │
├──────────┴──────────┴──────────┴────────────┤
│ 基础设施 (app/core/)                         │
│ 配置管理 / 日志 / 异常处理 / LLM 抽象         │
└─────────────────────────────────────────────┘
```

## 数据流 (POST /api/review)

```
用户上传文件 → 保存到 workspace/
           → 解析器提取纯文本
           → 调度 Agent 判断合同类型
           → 并行: 法律审查 Agent + 商业风险 Agent
                (每个 Agent 先从 Milvus RAG 检索相关法律条文)
           → 报告 Agent 汇总结果
           → 审查记录写入 MySQL
           → 返回 JSON 审查报告
```

## LangGraph 工作流

```
[dispatch] → conditional edge → [legal_review] ┐
                               → [business_risk] ┘
                                          ↓
                                    [report]
```

## 技术选型理由

- **LangGraph**: 支持条件路由和并行节点（Send API），天然适合多 Agent 编排
- **Milvus**: 成熟的中文向量检索方案，支持 ANN + 元数据过滤
- **BGE-Law**: 针对法律中文语料优化的 Embedding 模型
- **pdfplumber**: 原生表格提取能力，优于 pypdf
- **structlog**: 结构化日志，便于审查链路追踪
