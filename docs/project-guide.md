# 合约风控审查 Agent 系统 — 项目指南

> 面向新加入项目成员的入门文档。读完本文你将理解：系统做什么、怎么做、代码在哪。

## 目录

1. [一句话概述](#一句话概述)
2. [从用户视角：一次审查请求的全过程](#从用户视角一次审查请求的全过程)
3. [核心流程（配图版）](#核心流程配图版)
4. [多 Agent 工作流详解](#多-agent-工作流详解)
5. [RAG 知识库系统](#rag-知识库系统)
6. [关键数据结构](#关键数据结构)
7. [签署结论体系](#签署结论体系)
8. [项目目录导航](#项目目录导航)
9. [代码阅读路径](#代码阅读路径)
10. [常见问题](#常见问题)

---

## 一句话概述

这是一个 **AI 驱动的合同风险审查系统**。用户上传一份合同（文本或 PDF/DOCX），系统自动完成：**识别合同类型 → 检索相关法律条文 → 法律合规审查 + 商业风险评估（并行）→ 生成带签署建议的结构化审查报告**。

---

## 从用户视角：一次审查请求的全过程

```
用户操作                     系统内部处理                              用户看到
─────────                    ────────────                              ────────
                                                                  
1. 打开浏览器                 FastAPI 返回前端页面                    合同提交界面
   http://localhost:8001      (frontend/index.html)                  （粘贴文本或上传文件）

2. 粘贴合同文本               
   或上传 PDF/DOCX      ──→   POST /api/review                      
                              ├─ 如是文件 → 解析器提取文本
                              ├─ dispatch → 识别合同类型              进度动画：
                              ├─ legal_review ∥ business_risk        "分类→法律→商业→报告"
                              └─ report → 合并生成最终报告

3. 等待 15-60 秒        ──→   （LLM 推理 + RAG 检索）           ──→  审查结果页：
                                                                     ├─ 印章式裁决
                                                                     ├─ 风险统计卡片
                                                                     └─ 法律/商业双栏风险列表
```

### 支持的输入方式

| 方式 | 端点 | 限制 |
|------|------|------|
| 粘贴文本 | `POST /api/review` | 最大 200,000 字符 |
| 上传 PDF | `POST /api/review/upload` | ≤10MB，pdfplumber 解析 |
| 上传 DOCX | `POST /api/review/upload` | ≤10MB，python-docx 解析 |

### 一个真实输出示例（精简版）

```json
{
  "verdict": {
    "final_conclusion": "有条件可签",
    "legal_conclusion": "有条件可签",
    "business_conclusion": "可签",
    "preconditions": ["将违约金比例从 10% 下调至不超过实际损失 30%"]
  },
  "statistics": {
    "total_risks": 4,
    "by_level": { "P0": 1, "P1": 2, "P2": 1 }
  },
  "legal_review": {
    "risks": [
      {
        "risk_name": "违约金超过法定上限",
        "risk_level": "P0",
        "related_clause": "第五条 违约责任",
        "legal_basis": "《民法典》第585条",
        "recommended_wording": "违约金不超过实际损失的30%",
        "layer": "微观层"
      }
    ]
  }
}
```

---

## 核心流程（配图版）

```
                            ┌─────────────────┐
                            │   用户输入合同   │
                            │  (文本 / 文件)   │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │  [dispatch]      │
                            │  合同类型识别     │
                            │  LLM + JSON mode │
                            │  → 12 类分类     │
                            └────────┬────────┘
                                     │
                          ┌──────────┴──────────┐
                          │   Send API 并行扇出  │
                          └──────────┬──────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                                 ▼
          ┌─────────────────┐               ┌─────────────────┐
          │ [legal_review]   │               │ [business_risk]  │
          │ 法律合规审查      │               │ 商业风险评估      │
          │                  │               │                  │
          │ 1. RAG 检索法律  │               │ 1. RAG 检索法律  │
          │ 2. LLM 三层分析  │               │ 2. LLM 三层分析  │
          │ 3. 输出法律风险  │               │ 3. 输出商业风险  │
          └────────┬────────┘               └────────┬────────┘
                   │                                 │
                   └────────────┬────────────────────┘
                                │ 两个节点都完成后汇合
                                ▼
                       ┌─────────────────┐
                       │ [report]         │
                       │ 结果合并          │
                       │                  │
                       │ 1. 合并风险列表   │
                       │ 2. 统计 P0/P1/P2 │
                       │ 3. 综合裁决       │
                       │ 4. 生成最终报告   │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  JSON 响应       │
                       │  + 后台写入 MySQL │
                       └─────────────────┘
```

**关键设计决策：**
- **为什么并行？** legal_review 和 business_risk 互不依赖，并行执行把审查时间减半
- **为什么 dispatch 在前？** 合同类型信息帮助下游节点做精准的 RAG 检索和法律类别预过滤
- **为什么 report 是纯函数？** 不需要 LLM 调用，只是数据合并 + 规则推导，可靠且免费

---

## 多 Agent 工作流详解

### 工作流图结构

```
START → dispatch → [legal_review ∥ business_risk] → report → END
```

基于 **LangGraph** 实现：
- `dispatch` 后通过 `Send` API 并行扇出到两个审查节点
- 两个审查节点都完成后在 `report` 节点汇合（LangGraph 自动等待）
- 所有节点共享 `AgentState`（TypedDict，含 20+ 字段）

### Agent 1: dispatch — 合同分类

**角色**：合同类型分析专家  
**System Prompt**：`config/agents/dispatch.md`  
**LLM 配置**：temperature=0.1（极低温度，确保分类稳定）

**输入**：合同全文  
**输出**：
| 字段 | 说明 | 示例 |
|------|------|------|
| `contract_type` | 12 类之一 | "租赁合同" |
| `sub_type` | 细分子类型 | "房产租赁" |
| `confidence` | 置信度 0-1 | 0.95 |
| `category_id` | 分类编号 1-12 | 2 |
| `key_features` | 关键特征列表 | ["租金条款","租赁期限","交付条件"] |
| `suggested_focus` | 建议审查重点 | "关注租期≤20年、转租限制…" |

**12 类合同分类**：

| 编号 | 类型 | 编号 | 类型 |
|:---:|------|:---:|------|
| 1 | 买卖合同 | 7 | 互联网协议 |
| 2 | 租赁合同 | 8 | 婚姻家事类合同 |
| 3 | 服务类合同 | 9 | 劳动用工类合同 |
| 4 | 知识产权类合同 | 10 | 房地产类合同 |
| 5 | 担保类合同 | 11 | 建设工程类合同 |
| 6 | 借贷与赠与合同 | 12 | 公司投资类合同 |

**分类规则要点**：
1. 按交易实质而非标题归类（标题 "合作协议" 实质买卖 → 归入买卖）
2. 混合交易用 sub_type 标注（如 "借款+担保" → sub_type: "附担保借款"）
3. 无法确定时 confidence=0，contract_type="其他合同"

### Agent 2: legal_review — 法律合规审查

**角色**：资深合同法律审查律师  
**System Prompt**：`config/agents/legal_review.md`  
**LLM 配置**：temperature=0.2

**工作流程**：
1. 构建 RAG 检索查询（合同类型 + 审查重点 + 合同前 800 字）
2. 按合同类型映射法律类别（如 "买卖合同" → "民法-合同编"），在 Milvus 中预过滤
3. 检索 Top-5 相关法律条文 → 拼接为 `legal_context` 注入 LLM prompt
4. LLM 基于 **三层分析法** 审查合同，输出结构化风险列表

**输出关键字段**（每个风险项）：
- `risk_name` / `risk_level`(P0/P1/P2) / `risk_consequence`
- `legal_basis` — **必须**给出具体法条编号和条文原文
- `criteria` — 判别标准（量化阈值）
- `example` — 同类情形的真实判例
- `recommended_wording` — 可直接替换的推荐措辞
- `remediation` — 具体可执行的整改步骤
- `layer` — 所属审查层（宏观层/中观层/微观层）
- `overall_conclusion` — 法律审查结论 + `preconditions` 前置条件

### Agent 3: business_risk — 商业风险评估

**角色**：商业合同风险分析师  
**System Prompt**：`config/agents/business_risk.md`  
**LLM 配置**：temperature=0.3

**与 legal_review 的区别：**

| 维度 | legal_review | business_risk |
|------|-------------|---------------|
| 关注点 | 合不合法 | 划不划算 |
| 依据 | 法律法规条文 | 行业惯例、商业逻辑 |
| 核心问题 | 条款是否违反强制性规定 | 条款是否公平、可持续 |
| 风险命名 | "违约金超过法定上限" | "付款账期超出行业惯例" |
| 特有字段 | `legal_basis`（法条） | `negotiation_priority`（谈判优先级） |
| 输出 | 法律结论 | 商业结论 + 谈判建议 |

### 三层分析法（两个审查 Agent 共用）

所有审查 prompt 遵循三层结构，从粗到细：

```
第一层：宏观层 — 交易结构
  合同类型匹配 | 主体资格 | 标的合法性 | 程序合规 | 交易结构闭环

第二层：中观层 — 文本与形式
  合同形式匹配 | 格式条款 | 文件一致性 | 优先级条款 | 动态适应性

第三层：微观层 — 条款与语言
  核心条款齐全性 | 权利义务可执行性 | 违约救济闭环 | 争议解决 | 语言准确性
```

每个识别的风险都必须标注 `layer` 字段，输出顺序按 宏观→中观→微观。

### Agent 4: report — 报告汇总（纯函数，无 LLM）

**为什么不用 LLM？** report 节点只做数据合并和规则推导——合并两个审查节点的风险列表、按等级和层级统计、套用裁决规则输出最终结论。不需要 AI 判断，纯函数保证每次结果一致且零成本。

**合并逻辑**：
1. 合并法律 + 商业风险列表
2. 统计 P0/P1/P2 分布和三层分布
3. 综合裁决（见下方「签署结论体系」）
4. 合并双方 preconditions
5. 输出结构化 final_report dict

---

## RAG 知识库系统

### 为什么需要 RAG？

LLM 的法律知识有限且可能过时。RAG 在审查前先检索最相关的法律条文注入 prompt，让 LLM 基于真实法条做判断，大幅减少幻觉。

### 数据流

```
法律文本 (JSON/TXT)
    │
    ▼
SemanticChunker (句子边界感知分块, 512/64 窗口)
    │
    ▼
BGE-Law Embedding (1024维向量, passage: 前缀)
    │
    ▼
Milvus Lite (嵌入式向量库, 文件存储)
    │
    ▼  ← 查询时
    │
┌─── 一阶段检索（高召回）─────────────────────────────────┐
│  向量搜索 (Milvus ANN + COSINE)  ┐                     │
│  BM25 关键词 (jieba + rank_bm25) ├─→ RRF 融合 (k=60)  │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─── 二阶段精排（高精度）────────────┐
│  Cross-encoder 重排序              │
│  (bge-reranker-v2-m3 逐对打分)     │
└────────────────────────────────────┘
    │
    ▼
Top-K 法律条文 → 拼接为 context 注入 LLM prompt
```

### 关键组件

| 组件 | 文件 | 说明 |
|------|------|------|
| SemanticChunker | `app/rag/chunker.py` | 句子边界感知分块，窗口 512/64 |
| EmbeddingModel | `app/rag/embedding.py` | BGE-Law，1024维，passage:/query: 前缀 |
| BM25Searcher | `app/rag/bm25.py` | jieba 分词 + rank_bm25 + RRF 融合 |
| Reranker | `app/rag/reranker.py` | bge-reranker-v2-m3 cross-encoder |
| MilvusManager | `app/rag/milvus_client.py` | Milvus Lite 封装，本地文件存储 |
| LegalRetriever | `app/rag/retriever.py` | 统一检索入口，支持混合检索 + 重排序 |

### 元数据预过滤

审查节点检索时会根据合同类型自动缩小法律类别范围：

| 合同类型 | 检索类别 | 合同类型 | 检索类别 |
|----------|----------|----------|----------|
| 买卖/租赁/服务/借贷 | 民法-合同编 | 劳动用工 | 劳动法 |
| 知识产权 | 知识产权法 | 房地产 | 房地产法 |
| 担保 | 民法-担保 | 建设工程 | 建设工程法 |
| 互联网协议 | 电子商务法 | 公司投资 | 公司法 |

### 知识库初始化

```bash
# 创建 Milvus Collection
python scripts/init_milvus.py --drop-existing

# 导入法律文本
python scripts/import_laws.py -i data/sample_laws.json

# 预览分块效果
python scripts/import_laws.py -i data/sample_laws.json --dry-run
```

---

## 关键数据结构

### AgentState（工作流共享状态）

定义在 `app/agents/state.py`，TypedDict 含 20+ 字段，按产出节点分三组：

```python
# ── dispatch 产出 ──
contract_type: str              # "买卖合同"
contract_sub_type: str          # "动产买卖"
contract_category_id: int       # 1
contract_type_confidence: float # 0.92
contract_type_analysis: str     # 分类依据
contract_key_features: List[str]# ["标的物","价款","交付"]
contract_suggested_focus: str   # 审查重点建议

# ── legal_review 产出 ──
legal_risks: List[Dict]         # 风险列表
legal_summary: str              # 审查摘要
legal_overall_conclusion: str   # "有条件可签"
legal_preconditions: List[str]  # 签署前置条件

# ── business_risk 产出 ──
business_risks: List[Dict]
business_assessment: str
business_recommendation: str
business_overall_conclusion: str
business_preconditions: List[str]

# ── report 产出 ──
final_report: Dict[str, Any]    # 完整审查报告
```

### 风险项 Schema（11 个字段）

每个风险项（法律和商业共用结构）：

| 字段 | 类型 | 说明 | 法律特有 | 商业特有 |
|------|------|------|:---:|:---:|
| `risk_name` | str | 风险名称 | ✓ | ✓ |
| `risk_level` | str | P0/P1/P2 | ✓ | ✓ |
| `risk_consequence` | str | 风险后果 | ✓ | ✓ |
| `related_clause` | str | 关联条款位置 | ✓ | ✓ |
| `layer` | str | 宏观/中观/微观层 | ✓ | ✓ |
| `legal_basis` | str | 法律依据（法条+条文） | ✓ | |
| `criteria` | str | 判别标准 | ✓ | |
| `example` | str | 风险示例/判例 | ✓ | |
| `recommended_wording` | str | 推荐措辞 | ✓ | |
| `remediation` | str | 整改建议 | ✓ | |
| `negotiation_priority` | str | 谈判优先级 | | ✓ |
| `detail` | str | 详细分析 | | ✓ |

### 风险等级定义

| 等级 | 含义 | 处理要求 |
|:----:|------|----------|
| **P0** | 可能影响合同效力、导致重大损失 | 签署前**必须**处理 |
| **P1** | 显著增加争议或履约成本 | 建议**优先**谈判修改 |
| **P2** | 表述或流程优化项 | 可结合时间窗口处理 |

---

## 签署结论体系

系统采用**三层结论体系**，从两个独立维度分别判断，最终由 report 节点综合裁决。

### 三个结论的来源

```
legal_review.overall_conclusion     business_risk.overall_conclusion
        │                                      │
        └────────────┬─────────────────────────┘
                     │
                     ▼
            report.final_conclusion
```

### 裁决规则

```
任一"不建议签"  ──→  最终"不建议签"
任一"有条件可签" ──→  最终"有条件可签"  （前提是无"不建议签"）
两者均为"可签"  ──→  最终"可签"
```

### 各结论的判定标准

| 结论 | 法律审查条件 | 商业审查条件 |
|------|------------|------------|
| **可签** | 无 P0，P1 ≤ 2 个 | 无 P0，条款总体公允 |
| **有条件可签** | 存在 P0 但可修改解决 | 存在 P0 但可谈判解决 |
| **不建议签** | 存在无法修改的根本性障碍 | 存在根本性商业不对等 |

### 前端呈现

前端以**印章样式**呈现最终裁决：
- 🟢 可签 → 红框实线印章
- 🟡 有条件可签 → 琥珀色虚线印章
- 🔴 不建议签 → 红底警示印章

---

## 项目目录导航

```
agent项目/
│
├── app/                            # 应用核心代码
│   ├── main.py                     # FastAPI 入口，注册路由和中间件
│   │
│   ├── agents/                     # LangGraph 多 Agent 工作流
│   │   ├── state.py                # AgentState 类型定义 ★
│   │   ├── graph.py                # 工作流图构建 + create_review_workflow()
│   │   └── nodes/                  # 四个工作流节点 ★
│   │       ├── dispatch.py         #   Agent 1: 合同分类
│   │       ├── legal_review.py     #   Agent 2: 法律审查
│   │       ├── business_risk.py    #   Agent 3: 商业风险评估
│   │       └── report.py           #   Agent 4: 报告汇总（纯函数）
│   │
│   ├── rag/                        # RAG 知识库
│   │   ├── retriever.py            # 统一检索入口 ★
│   │   ├── chunker.py              # 语义分块
│   │   ├── embedding.py            # BGE-Law Embedding
│   │   ├── bm25.py                 # BM25 + RRF 融合
│   │   ├── reranker.py             # Cross-encoder 重排序
│   │   └── milvus_client.py        # Milvus 连接管理
│   │
│   ├── api/                        # FastAPI 路由层
│   │   ├── deps.py                 # 依赖注入（workflow + settings）
│   │   └── routes/
│   │       ├── health.py           # GET /health
│   │       └── review.py           # POST /api/review ★
│   │
│   ├── llm/
│   │   └── client.py               # LLM 客户端（OpenAI SDK）★
│   │
│   ├── parsers/                    # 文档解析
│   │   ├── base.py                 # BaseParser 抽象类
│   │   ├── docling_parser.py       # Docling（优先）
│   │   ├── pdf_parser.py           # pdfplumber（回退）
│   │   └── docx_parser.py          # python-docx（回退）
│   │
│   ├── schemas/                    # Pydantic API Schema
│   │   ├── common.py               # APIResponse[T]
│   │   └── review.py               # ReviewRequest/Response ★
│   │
│   ├── db/                         # MySQL 数据库层（可选）
│   │   ├── base.py                 # ORM 基类
│   │   └── session.py              # 异步会话管理
│   │
│   ├── models/                     # ORM 数据模型
│   │   ├── contract.py             # ContractRecord
│   │   └── review.py               # ReviewRecord + RiskRecord
│   │
│   └── core/                       # 基础设施
│       ├── config.py               # Pydantic Settings ★
│       └── logging.py              # structlog 日志
│
├── config/                         # 用户配置区
│   ├── settings.yaml               # 运行参数
│   └── agents/                     # Agent System Prompts ★
│       ├── dispatch.md
│       ├── legal_review.md
│       └── business_risk.md
│
├── frontend/
│   └── index.html                  # 单文件 SPA 前端
│
├── scripts/                        # 运维脚本
│   ├── init_milvus.py              # 初始化向量库
│   ├── import_laws.py              # 导入法律文本
│   └── import_all.py               # 批量导入
│
├── tests/                          # 测试
├── data/                           # 法律文本数据
├── alembic/                        # 数据库迁移
│
├── .env.example                    # 环境变量模板
├── requirements.txt                # Pip 依赖
├── pyproject.toml                  # 项目元数据 + 工具配置
├── run.py                          # 开发服务器启动
├── Dockerfile
└── docker-compose.yml
```

★ 标记的是**首次阅读最关键的 8 个文件**。

---

## 代码阅读路径

### 路径 A：理解业务流程（推荐新人）

按一次请求的调用链路阅读：

```
1. app/api/routes/review.py    ← POST /api/review 入口
       │
2. app/api/deps.py             ← get_workflow() 懒加载工作流
       │
3. app/agents/graph.py         ← create_review_workflow() 构建图
       │
4. app/agents/nodes/dispatch.py    ← 合同分类
5. app/agents/nodes/legal_review.py ← 法律审查
6. app/agents/nodes/business_risk.py ← 商业评估
7. app/agents/nodes/report.py      ← 合并报告
       │
8. app/schemas/review.py       ← 响应 Schema（数据变形）
```

### 路径 B：理解 RAG 系统

```
1. app/rag/retriever.py        ← 检索入口，retrieve_hybrid()
2. app/rag/embedding.py        ← BGE-Law 向量化
3. app/rag/bm25.py             ← BM25 关键词 + RRF
4. app/rag/reranker.py         ← Cross-encoder 精排
5. app/rag/chunker.py          ← 入库前的分块
6. app/rag/milvus_client.py    ← Milvus 底层 API
```

### 路径 C：理解基础设施

```
1. app/core/config.py          ← Settings 和子配置
2. app/llm/client.py           ← LLM 客户端（retry/streaming/JSON）
3. app/core/logging.py         ← structlog 结构化日志
4. app/main.py                 ← FastAPI 应用创建
```

---

## 常见问题

### Q: 为什么用 LangGraph 而不是 LangChain Agent？

LangGraph 提供了更细粒度的控制：显式的图结构、条件边、Send API 并行扇出。对于"分类→并行审查→汇总"这个确定性流程，图结构比自主 Agent 更可控、更可调试。

### Q: 为什么 Milvus Lite 而不是完整的 Milvus 服务？

开发阶段零依赖。Milvus Lite 是一个文件（`milvus_data.db/`），无需 Docker 或独立服务。生产环境只需改 `MILVUS_DB_URI` 为服务器地址即可切换。

### Q: 审查为什么不一次 LLM 调用完成，要拆成 4 个 Agent？

1. **并行加速**：法律审查和商业评估互不依赖，并行执行
2. **职责分离**：法律审查和商业评估需要不同的 System Prompt 和思考框架
3. **分类先行**：先知道合同类型，才能在 RAG 检索时做精准的法律类别预过滤
4. **报告可靠**：report 节点不用 LLM，纯函数合并，结果确定且零成本

### Q: 如何处理 LLM 返回格式不稳定？

`app/llm/client.py` 的 `chat_json()` 做了三层容错：
1. 优先使用 OpenAI 的 `response_format={"type": "json_object"}`（原生 JSON mode）
2. 失败回退到标准模式 + 正则提取 `{...}` 块
3. 多个 JSON 候选块时，选包含审查关键字段（"risks"、"contract_type" 等）的那个

### Q: MySQL 不配置系统能工作吗？

能。MySQL 仅用于审查历史持久化。不配置时，审查功能完全正常，只是不会保存审查记录。

### Q: 怎么修改 Agent 的审查逻辑？

编辑 `config/agents/*.md` 中的 System Prompt，无需改代码。重启服务即生效。

---

## 快速上手

```bash
# 1. 环境
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 编辑 .env，填写 LLM_API_KEY

# 3. 初始化知识库
python scripts/init_milvus.py --drop-existing
python scripts/import_laws.py -i data/sample_laws.json

# 4. 启动
python run.py
# 访问 http://localhost:8001
```

下一步：打开 `config/agents/dispatch.md`，了解 Agent 的 System Prompt 怎么写。然后跟着「路径 A」阅读一次完整的请求调用链。
