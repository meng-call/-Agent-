# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

合约风控审查 Agent 系统 — AI Agent + RAG 架构，技术栈：Python 3.11+ / FastAPI / LangGraph / Milvus Lite / MySQL / BGE-Law。

## 常用命令

```bash
# 启动开发服务器（自动清理端口占用，默认 8001）
python run.py

# 也可指定端口
PORT=8000 python run.py

# Milvus 知识库初始化（首次使用或重建）
python scripts/init_milvus.py --drop-existing

# 导入法律文本
python scripts/import_laws.py -i data/sample_laws.json
python scripts/import_laws.py -i data/ --category 民法       # 批量导入目录

# 预览分块效果（不写入）
python scripts/import_laws.py -i data/sample_laws.json --dry-run

# 运行测试
pytest tests/ -v

# 语法验证（依赖未安装时）
python -m py_compile <file>.py
```

## 服务访问

| URL | 说明 |
|-----|------|
| `http://localhost:8001` | 前端界面（合同提交 + 审查结果） |
| `http://localhost:8001/docs` | API 文档（Scalar，中文界面） |
| `http://localhost:8001/health` | 健康检查 |
| `http://localhost:8001/api/review/health` | 审查模块就绪检查 |

## 架构要点

**分层设计** — `app/` 下按职责物理隔离：

| 目录 | 职责 | 状态 |
|------|------|------|
| `app/llm/` | LLM 客户端封装（OpenAI SDK，retry + streaming + JSON mode） | **已完成** |
| `app/agents/` | LangGraph 多 Agent 工作流（graph + 5 个 nodes） | **已完成** |
| `app/rag/` | RAG 知识库（chunker / embedding / bm25 / reranker / milvus / retriever） | **已完成** |
| `app/api/routes/` | FastAPI 路由（thin handler） | **已完成** |
| `app/parsers/` | 文档解析（Docling 优先，pdfplumber/docx 回退） | **已完成** |
| `app/schemas/` | API Request/Response Schema（Pydantic） | **已完成** |
| `app/core/` | 配置管理 + 依赖注入 + 结构化日志 | **已完成** |
| `app/db/` | MySQL 数据库层（SQLAlchemy ORM） | 骨架 |
| `frontend/` | 前端界面（单文件 HTML/CSS/JS，FastAPI 路由 `/` 直接服务） | **已完成** |

**配置管理** — `app/core/config.py` 使用 pydantic-settings v2。

- 配置从 `.env` 加载，启动时校验 `LLM_API_KEY` 必填
- **关键**：子配置（`LLMSettings`、`MilvusSettings` 等）必须各自声明 `model_config = SettingsConfigDict(env_prefix="...", env_file=".env", ...)`，否则嵌套 BaseSettings 模型不会读取 `.env` 中的环境变量
- 环境变量前缀：`LLM_` / `EMBEDDING_` / `MILVUS_` / `MYSQL_`
- LLM 默认供应商 DeepSeek，base_url 可覆盖为任意 OpenAI 兼容 API

**Milvus Lite（嵌入式）** — 无需 Docker 或外部服务。

- `MILVUS_URI=./milvus_data.db`（本地文件，自动创建）
- 切回服务端只需将 URI 改为 `http://host:19530`
- `MilvusManager` 封装在 `app/rag/milvus_client.py`，通过 `pymilvus.MilvusClient` 统一 API

**结构化日志** — `app/core/logging.py` 基于 structlog，提供 `setup_logging(level, json_format)` 和 `get_logger(name, **bindings)`。生产模式输出 JSON 键值对，开发模式输出彩色控制台。所有 Agent 节点和 API 路由已迁移为键值对日志（如 `logger.info("dispatch.completed", contract_type=t)`），而非字符串拼接。

## 多 Agent 工作流（第三阶段）

工作流图：`START → dispatch → [legal_review ∥ business_risk] → report → END`

并行扇出通过 LangGraph `Send` API 实现，两个审查节点完成后在 report 汇合。

### AgentState

定义在 `app/agents/state.py`，TypedDict 含 20+ 字段，按产出节点分三组：
- Dispatch：contract_type / sub_type / category_id / confidence / key_features / suggested_focus
- Review：legal_risks / legal_summary / legal_overall_conclusion / legal_preconditions / business_risks / business_assessment / business_recommendation / business_overall_conclusion / business_preconditions
- Report：final_report

### 节点工厂模式

dispatch / legal_review / business_risk 三节点使用闭包工厂函数（`create_*_node(llm, retriever)`），依赖通过工厂注入，节点内部不创建连接。report 为纯函数。

### 审查框架：三层分析法

所有审查 prompt 遵循：
1. **宏观层** — 交易结构、主体资格、程序合规
2. **中观层** — 文本形式、格式条款、文件一致性
3. **微观层** — 核心条款、违约救济、语言准确性

每个 risk 输出标注 `layer` 字段（宏观层/中观层/微观层）。

### 合同分类

固定 12 类：买卖合同、租赁合同、服务类合同、知识产权类合同、担保类合同、借贷与赠与合同、互联网协议、婚姻家事类合同、劳动用工类合同、房地产类合同、建设工程类合同、公司投资类合同。分类路由规则见 `config/agents/dispatch.md`。

### 风险输出 Schema

每个风险项 11 个字段：risk_name / risk_level(P0/P1/P2) / risk_consequence / related_clause / legal_basis / criteria(判别标准) / example(风险示例) / recommended_wording / remediation / layer / negotiation_priority(仅商业)

### 签署结论

三层结论体系：
- legal_review → `legal_overall_conclusion` + `legal_preconditions`
- business_risk → `business_overall_conclusion` + `business_preconditions`
- report → `final_conclusion`（综合裁决：可签/有条件可签/不建议签）

裁决规则：任一"不建议签"→最终不建议签；任一"有条件可签"→最终有条件可签。

### Agent System Prompts

三个 Agent 的角色提示词放在 `config/agents/*.md`，不在代码中硬编码。

### 一键创建

```python
from app.core.config import load_settings
from app.agents import create_review_workflow

workflow = create_review_workflow(load_settings())
report = workflow.invoke({"contract_text": "..."})
```

## LLM 客户端（`app/llm/client.py`）

基于 OpenAI SDK，兼容 DeepSeek。Professional 规模特性：
- **指数退避重试**：429/5xx/网络异常自动重试 3 次（1s, 2s, 4s）
- **JSON mode 优先**：先尝试 `response_format={"type": "json_object"}`，失败回退标准模式+正则提取
- **多 JSON 候选解析**：响应含多个 `{...}` 块时，选包含审查关键字段的那个
- **流式输出**：`chat_stream()` 同步生成器 + `chat_stream_async()` 异步生成器，支持 SSE 场景

关键 API：`llm.chat(messages)` → `str`、`llm.chat_json(messages)` → `Dict[str, Any]`、`llm.chat_stream_async(messages)` → `AsyncIterator[str]`

## RAG 检索管道

完整的二阶段检索 + 元数据过滤管道：

### 数据入库

原始文本 → `SemanticChunker`（句子边界感知，512/64 窗口）→ `EmbeddingModel`（BGE-Law 1024维，passage:/query: 前缀）→ `MilvusManager.insert()`

- **Milvus Schema**：`id`(INT64自增) / `text`(VARCHAR 4096) / `embedding`(FLOAT_VECTOR 1024) / `source`(VARCHAR) / `law_category`(VARCHAR) / `article_number`(VARCHAR)
- **索引**：`AUTOINDEX` + `COSINE`

### 检索阶段

**一阶段（初检 · 高召回）**：混合搜索

1. 向量语义搜索（Milvus ANN + COSINE）→ Top-K×2
2. BM25 关键词搜索（jieba 分词 + rank_bm25）→ Top-K×2
3. RRF（Reciprocal Rank Fusion, k=60）融合两条结果列表

实现于 `app/rag/bm25.py`（`BM25Searcher` + `reciprocal_rank_fusion()`）和 `LegalRetriever.retrieve_hybrid()`。BM25 索引从 Milvus 全量文档懒加载构建。

**二阶段（精排 · 高精度）**：Cross-encoder 重排序

融合结果 → `Reranker`（FlagEmbedding bge-reranker-v2-m3）逐对打分 → 按新分数截断 Top-K

实现于 `app/rag/reranker.py`，通过 `RetrievalConfig.enable_rerank` 开关控制，集成在 `retrieve_hybrid()` 末端。

### 元数据预过滤

review 节点检索时自动按合同类型映射法律类别并传入 `filter_category`：
- 买卖合同/租赁合同/服务类合同 → `民法-合同编`
- 劳动用工类合同 → `劳动法`
- 知识产权类合同 → `知识产权法`
- 等 7 个映射（`legal_review.py` / `business_risk.py` 中的 `_get_law_category_for_contract_type()`）

### 关键 API

- `retriever.retrieve(query)` → `List[SearchResult]`（纯向量）
- `retriever.retrieve_hybrid(query)` → `List[SearchResult]`（BM25+向量+RRF+Rerank）
- `retriever.retrieve_context(query, use_hybrid=True)` → 拼接好的 prompt 字符串

## API 端点（第四阶段）

### 路由注册

`app/main.py` 注册两个 router：`health_router`（`GET /health`）+ `review_router`（prefix="/api"）。Swagger 已替换为 Scalar（`/docs`），前端首页在 `/`。

### 依赖注入（`app/api/deps.py`）

- `get_settings(request: Request)` — 优先 `request.app.state.settings`，回退 `_cached_settings()`（进程级 lru_cache）
- `get_workflow()` — 懒加载全局单例，首次调用初始化 LLM + Embedding + Milvus + Retriever + Graph

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 前端界面（合同提交 + 审查结果展示） |
| `GET` | `/docs` | Scalar API 文档（中文界面） |
| `POST` | `/api/review` | JSON body `{"contract_text": "..."}` → 工作流 → `ReviewResponse` |
| `POST` | `/api/review/upload` | multipart 上传 PDF/DOCX（≤10MB）→ 解析 → 审查 |
| `GET` | `/api/review/health` | 检查工作流/LLM 就绪状态 |

### 文档解析（`app/parsers/`）

基类 `BaseParser` 定义 `async def parse(file_path: Path) -> str`。

解析器优先级：**Docling → pdfplumber / python-docx（回退）**

- `DoclingParser`（`app/parsers/docling_parser.py`）— 统一解析 PDF/DOCX/PPTX，深度学习表格识别（TableFormer），输出 Markdown 保留文档结构。`_pick_parser()` 自动尝试 Docling，不可用时回退。
- `PDFParser` — 轻量回退，pdfplumber 逐页提取纯文本
- `DocxParser` — 轻量回退，python-docx 提取段落+表格

上传文件写入临时文件 → 解析 → 立即删除临时文件。

### API Schema（`app/schemas/`）

- `common.py` — `APIResponse[T]` 泛型响应包装
- `review.py` — `ReviewRequest` / `ReviewResponse` / `ReviewData` / `ReviewVerdict` / `ReviewStatistics` / `ReviewSection` / `RiskItem`

`_transform_report()` 将工作流 raw dict 转换为 Pydantic `ReviewData`，容错处理字段缺失。

## 前端（`frontend/index.html`）

单文件 SPA，FastAPI 路由 `/` 直接服务。设计要点：
- **印章裁决**：综合结论以传统印章样式呈现（可签→红框实线 / 有条件可签→琥珀虚线 / 不建议签→红底）
- **双 Tab 输入**：粘贴文本 + 文件上传（支持拖拽），`Ctrl+Enter` 提交
- **加载态**：脉动印章动画 + 四步进度（分类→法律→商业→报告）
- **结果页**：判决横幅 + 风险统计卡片 + 法律/商业双栏风险列表
- 右上角健康状态灯，30s 轮询 `/health`
