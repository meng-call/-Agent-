# 合约风控审查 Agent 系统

AI-powered contract risk control review system with multi-agent workflow and RAG knowledge base.

## 技术栈

| 层级 | 技术 |
|------|------|
| API 框架 | FastAPI |
| Agent 编排 | LangGraph（Send API 并行扇出） |
| LLM 客户端 | OpenAI SDK（兼容 DeepSeek 等，retry + streaming + JSON mode） |
| Embedding | BGE-Law（BAAI/bge-large-zh-v1.5，1024维） |
| 向量数据库 | Milvus Lite（嵌入式，无需 Docker） |
| 关键词检索 | BM25（jieba 分词 + rank_bm25） |
| 重排序 | bge-reranker-v2-m3（Cross-encoder） |
| 文档分块 | SemanticChunker（句子边界感知，512/64 窗口） |
| 文档解析 | Docling（优先）→ pdfplumber / python-docx（回退） |
| 关系数据库 | MySQL（SQLAlchemy ORM + aiomysql） |
| 结构化日志 | structlog（开发彩色 / 生产 JSON） |
| 前端 | 单文件 SPA（HTML/CSS/JS，FastAPI 直接服务） |

## 系统要求

- Python 3.11+
- MySQL 8.0+（可选，db 层为骨架）
- 无 GPU 亦可运行（Embedding 支持 CPU 推理）

## 快速开始

### 1. 环境准备

```bash
git clone <repo-url>
cd agent项目

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，**必填** `LLM_API_KEY`，其余可按需调整。

### 3. 初始化知识库（首次使用）

```bash
# 创建 Milvus Collection
python scripts/init_milvus.py --drop-existing

# 导入法律文本
python scripts/import_laws.py -i data/sample_laws.json

# 预览分块效果（不写入）
python scripts/import_laws.py -i data/sample_laws.json --dry-run
```

### 4. 启动

```bash
python run.py                # 默认 8001 端口，自动清理端口占用
# 或
PORT=8000 python run.py      # 指定端口
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 验证

```bash
curl http://localhost:8001/health
# → {"status": "ok"}

curl http://localhost:8001/api/review/health
# → {"status": "ok", "workflow_ready": true, "llm_model": "deepseek-chat", ...}
```

## 服务访问

| URL | 说明 |
|-----|------|
| `http://localhost:8001` | 前端界面（合同提交 + 审查结果） |
| `http://localhost:8001/docs` | API 文档（Scalar，中文界面） |
| `http://localhost:8001/health` | 健康检查 |
| `http://localhost:8001/api/review/health` | 审查模块就绪检查 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 前端界面 |
| `GET` | `/docs` | Scalar API 文档 |
| `GET` | `/health` | 服务健康检查 |
| `POST` | `/api/review` | 合同文本审查 `{"contract_text": "..."}` |
| `POST` | `/api/review/upload` | 文件上传审查（PDF/DOCX，≤10MB） |
| `GET` | `/api/review/health` | 审查模块就绪检查 |

## 项目结构

```
├── app/
│   ├── main.py                 # FastAPI 应用入口
│   ├── core/
│   │   ├── config.py           # Pydantic Settings（嵌套子配置，env 前缀分层）
│   │   ├── logging.py          # structlog 结构化日志
│   │   └── dependencies.py     # 跨模块依赖注入
│   ├── api/
│   │   ├── deps.py             # FastAPI Depends（工作流懒加载 + 配置注入）
│   │   └── routes/
│   │       ├── health.py       # GET /health
│   │       └── review.py       # POST /api/review + /api/review/upload
│   ├── agents/
│   │   ├── state.py            # AgentState TypedDict（20+ 字段）
│   │   ├── graph.py            # create_review_workflow() 工厂函数
│   │   └── nodes/
│   │       ├── dispatch.py     # 合同分类节点
│   │       ├── legal_review.py # 法律审查节点
│   │       ├── business_risk.py# 商业风险审查节点
│   │       └── report.py       # 报告汇总节点
│   ├── rag/
│   │   ├── chunker.py          # SemanticChunker
│   │   ├── embedding.py        # BGE-Law Embedding 模型
│   │   ├── bm25.py             # BM25 + RRF 融合
│   │   ├── reranker.py         # Cross-encoder 精排
│   │   ├── milvus_client.py    # Milvus 连接管理
│   │   └── retriever.py        # 统一检索入口（向量/混合）
│   ├── parsers/
│   │   ├── base.py             # BaseParser 抽象类
│   │   ├── docling_parser.py   # Docling 统一解析（优先）
│   │   ├── pdf_parser.py       # pdfplumber 回退
│   │   └── docx_parser.py      # python-docx 回退
│   ├── schemas/
│   │   ├── common.py           # APIResponse[T] 泛型包装
│   │   └── review.py           # ReviewRequest/Response 及子模型
│   ├── llm/
│   │   └── client.py           # OpenAI SDK 封装（retry/streaming/JSON mode）
│   ├── db/                     # MySQL 层（骨架）
│   └── models/                 # 内部数据模型（骨架）
├── config/
│   ├── settings.yaml           # 运行参数配置
│   └── agents/                 # Agent System Prompts（Markdown）
│       ├── dispatch.md
│       ├── legal_review.md
│       └── business_risk.md
├── frontend/
│   └── index.html              # 单文件 SPA 前端
├── data/
│   └── sample_laws.json        # 示例法律文本
├── scripts/
│   ├── init_milvus.py          # Milvus Collection 初始化
│   ├── import_laws.py          # 法律文本导入（JSON/TXT）
│   └── import_all.py           # 批量导入（LawRefBook + ChatLaw）
├── tests/
│   ├── conftest.py             # 共享 fixtures
│   ├── test_agents/
│   │   └── test_report.py      # 报告节点测试
│   ├── test_api/               # API 端点测试（待补充）
│   ├── test_llm/
│   │   └── test_client.py      # LLM 客户端测试
│   ├── test_rag/
│   │   ├── test_bm25.py        # BM25 检索测试
│   │   └── test_retriever.py   # 检索管道测试
│   └── test_schemas/
│       └── test_review.py      # Schema 转换测试
├── docs/
│   └── architecture.md         # 架构说明
├── .env.example                # 环境变量模板
├── pyproject.toml              # 项目元数据 + 工具配置
├── requirements.txt            # Pip 依赖
└── run.py                      # 开发服务器启动脚本
```

## 架构概览

### 多 Agent 工作流

```
START → dispatch → [legal_review ∥ business_risk] → report → END
```

- **dispatch** — 识别合同类型（12类），提取关键特征，建议审查重点
- **legal_review** — 法律合规审查，三层分析法（宏观/中观/微观），检索相关法律条文
- **business_risk** — 商业风险评估，付款条款、违约责任、谈判优先级
- **report** — 汇总结果，输出最终签署结论（可签/有条件可签/不建议签）

### 三层审查框架

所有审查 prompt 遵循三层分析法：

1. **宏观层** — 交易结构、主体资格、程序合规
2. **中观层** — 文本形式、格式条款、文件一致性
3. **微观层** — 核心条款、违约救济、语言准确性

每个风险输出标注 `layer` 字段。

### RAG 检索管道

```
Query → 向量搜索(Milvus ANN) + BM25关键词检索(jieba)
     → RRF 融合(Reciprocal Rank Fusion, k=60)
     → Cross-encoder 重排序(bge-reranker-v2-m3)
     → Top-K 结果 + 元数据预过滤
```

检索时自动按合同类型过滤法律类别（如买卖合同 → 民法-合同编）。

### 签署结论体系

三层结论：
- `legal_review` → `legal_overall_conclusion` + `legal_preconditions`
- `business_risk` → `business_overall_conclusion` + `business_preconditions`
- `report` → `final_conclusion`（综合裁决）

裁决规则：任一"不建议签"→最终不建议签；任一"有条件可签"→最终有条件可签。

## 配置项说明

完整配置见 `.env.example`，关键项：

| 环境变量 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `LLM_PROVIDER` | str | deepseek | LLM 供应商 |
| `LLM_API_KEY` | str | — | API Key（**必需**） |
| `LLM_BASE_URL` | str | — | 自定义 API 地址（留空用默认） |
| `LLM_MODEL` | str | deepseek-chat | 模型名称 |
| `LLM_TEMPERATURE` | float | 0.3 | 生成温度 |
| `LLM_MAX_TOKENS` | int | 4096 | 最大输出 token 数 |
| `EMBEDDING_MODEL` | str | BAAI/bge-large-zh-v1.5 | Embedding 模型 |
| `EMBEDDING_DEVICE` | str | cpu | 推理设备（cpu/cuda） |
| `MILVUS_HOST` | str | localhost | Milvus 地址 |
| `MILVUS_PORT` | int | 19530 | Milvus 端口 |
| `MILVUS_DB_NAME` | str | contract_review | 数据库名 |
| `MILVUS_COLLECTION_NAME` | str | legal_knowledge | Collection 名 |
| `MYSQL_HOST` | str | localhost | MySQL 地址（db 层就绪前可选） |
| `MYSQL_PASSWORD` | str | — | MySQL 密码（db 层就绪前可选） |
| `ENV` | str | development | 运行环境 |
| `LOG_LEVEL` | str | INFO | 日志级别 |

## 运维脚本

| 脚本 | 用途 |
|------|------|
| `python scripts/init_milvus.py --drop-existing` | 初始化/重建 Milvus Collection |
| `python scripts/import_laws.py -i <file>` | 导入单个 JSON/TXT 法律文件 |
| `python scripts/import_laws.py -i <dir>/ --category 民法` | 批量导入目录 |
| `python scripts/import_all.py` | 从 LawRefBook + ChatLaw 批量导入 |
| `python scripts/import_all.py --dry-run` | 预览分块效果 |
| `python run.py` | 启动开发服务器 |

## 运行测试

```bash
pytest tests/ -v

# 仅 RAG 模块
pytest tests/test_rag/ -v

# 覆盖率
pytest tests/ -v --cov=app --cov-report=html
```

## 已知限制 / 待完善

| 项目 | 状态 | 说明 |
|------|------|------|
| MySQL 数据库层 | 骨架 | `app/db/` 和 `app/models/` 为空壳，Alembic 迁移未初始化 |
| Docker 容器化 | 未实现 | 无 Dockerfile / docker-compose |
| CI/CD | 未配置 | 无 GitHub Actions 等 CI 流水线 |
| pre-commit 钩子 | 未配置 | 依赖已声明但无 `.pre-commit-config.yaml` |
| 测试覆盖 | 部分 | 缺少 dispatch/legal_review/business_risk/parsers/chunker/reranker 等测试 |
| 运行脚本 | 仅 Windows | `run.py` 的端口清理仅支持 Windows |
| 前端独立部署 | 内嵌 | 前端为单文件内嵌在 FastAPI 中，无独立构建流程 |
