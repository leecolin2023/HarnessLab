# 企业制度知识引擎 · Build vs Reuse 审计（2026-10-10）

> 状态：**Source-verified / Benchmark pending**。非 SRS，非框架采购批准，**没有声称在真实银行制度集上取得了任何分数**。本文审计基于上游文档、源码入口和许可证；内网版本锁定后还须重新验证实际行为。

## 结论（可撤销假设）

- **首要候选**：RAGFlow v0.27.2（而非不加验证地升级 v1.0.0-rc1），把它当作**独立知识检索服务**，不替换 dsh-intramate Agent Harness。
- **第二对照**：Dify（传统知识检索/父子分块/混合召回对照）、LightRAG（图/混合检索对照）。Microsoft GraphRAG 更适合作为全局主题发现的算法实验候选，不作为首选企业管理平台。
- **暂不自建**：OCR/文档解析引擎、分块器、Embedding/Rerank、向量数据库、全文检索、图存储、通用图抽取、通用 Agentic Retrieval/任务规划、知识库管理后台。先核实现有能力和性能，确认缺口后再评估。
- **企业特有且应由 IntraMate 长期拥有的薄层/控制层**：制度台账与效力视角映射（优先从企业已有系统同步）；可复核条款证据合同；基于可信身份的授权范围与审计；条件/例外/冲突证据审查与穷举覆盖清单；框架替换的一致性测试。
- 当前尚未用真实银行制度比较 E0–E4；**不量化“成熟框架已解决百分之多少”，不宣称某个框架能够完整满足银行权限与溯源要求。**

## 1. 上游已核实能力、源码定位与边界

| 方案 | 核实到的能力 | 可核查入口 | 对本项目的约束/待测 |
| --- | --- | --- | --- |
| **RAGFlow v0.27.2** | 解析、Hybrid、Rerank、元数据过滤、父子分块、知识编译 Graph/Tree/PageIndex、Agentic RAG；原 GraphRAG/RAPTOR UI 被新编译方式替代 | [版本说明](https://github.com/infiniflow/ragflow/blob/main/docs/release_notes.md)、[Graph/Tree/PageIndex 配置](https://github.com/infiniflow/ragflow/blob/main/docs/guides/knowledge_compilation/built_in_templates_and_dedicated_configuration.md)、[HTTP Retrieve Chunks](https://github.com/infiniflow/ragflow/blob/main/docs/references/http_api_reference.md)、[检索测试](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/notes_and_faqs.md) | Graph/Tree 是模型生成的语义结构，**不能等同法定章节/制度条款的原生结构**；检索片段是否准确附带原文件版本、条号及父款需抽样测。知识图可自定义 Entity/Relation type，不意味着制度职责关系已验证正确 |
| **RAGFlow v1.0.0-rc1** | Go 重构与新部署栈 | [Release Notes](https://github.com/infiniflow/ragflow/blob/main/docs/release_notes.md) | 官方声明 0.27.2→1.0 自动数据升级**不可逆**、预发布、Team/Me 权限未支持，不能直接投入多权限银行服务；需另起隔离部署测试 |
| **Dify** | 知识检索节点支持多知识库、元数据过滤、重排；源码中有已授权 dataset 过滤，父子索引有处理器/测试 | [官方知识检索节点](https://github.com/langgenius/dify-docs/blob/main/en/cloud/use-dify/nodes/knowledge-retrieval.mdx)、[dataset_retrieval.py](https://github.com/langgenius/dify/blob/main/api/core/rag/retrieval/dataset_retrieval.py)、[parent-child 测试](https://github.com/langgenius/dify/blob/main/api/tests/unit_tests/core/rag/indexing/processor/test_parent_child_index_processor.py) | 工作流完整但偏 Agent 应用平台，对 DSH 有重复；尚未证实银行条款效力和跨制度穷举。许可证是**带附加条件**的 Dify Open Source License：[LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE) |
| **LightRAG** | local/global/hybrid/naive/mix；结构化 data 查询、references、重排与文档删除；图检索可作为独立服务比较 | [QueryParam 定义](https://github.com/HKUDS/LightRAG/blob/main/lightrag/base.py)、[query routes](https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/query_routes.py)、[数据查询源码](https://github.com/HKUDS/LightRAG/blob/main/lightrag/lightrag.py)、[LICENSE (MIT)](https://github.com/HKUDS/LightRAG/blob/main/LICENSE) | Graph 边的来源/多版本切换/权限过滤无法仅靠有 references 的 API 保证，须作全链路验证；图抽取强依赖本地 LLM |
| **Microsoft GraphRAG** | Local / Global / DRIFT；社区报告 Map-Reduce 全局主题分析 | [Global 源码设计/说明](https://github.com/microsoft/graphrag/blob/main/docs/query/global_search.md)、[query overview](https://github.com/microsoft/graphrag/blob/main/docs/query/overview.md)、[MIT License](https://github.com/microsoft/graphrag/blob/main/LICENSE) | Global 是**主题/社区摘要**，不是逐条全库核验；索引成本、增量更新与中文本地模型需量化 |
| **FastGPT / MaxKB** | 国内语言与部署生态较友好，适合作为低门槛功能对照 | [FastGPT](https://github.com/labring/FastGPT)、[MaxKB](https://github.com/1Panel-dev/MaxKB) | 与 DSH 编排/UI 重复度较高；FastGPT 采用附条件开源许可，[LICENSE](https://github.com/labring/FastGPT/blob/main/LICENSE)，MaxKB 为 GPLv3，需法务评估组合/分发场景 |

### v0.27.2 源码中的具体风险与测试

源码：[rag/nlp/search.py@v0.27.2](https://github.com/infiniflow/ragflow/blob/v0.27.2/rag/nlp/search.py) 中：
- `build_fusion_expr()` 实际组合 lexical 与 dense 权重，证实不是仅提供界面上的 Hybrid 开关。
- `Dealer._prune_deleted_chunks()` 通过数据库检查文档是否存在以剔除删除后残留的搜索 chunk；但 `_existing_doc_ids()` 采用 **120 秒 TTL** 的文档存在性缓存（仅基于源码观察，**不据此断言已存在可利用越权漏洞**）。
- 因此加入实验：**先查询使文档存在性缓存升温 → 删除/禁用文件或撤销用户授权 → 在 0/1/30/121 秒反复检索**，验证正文/引用/Graph/摘要/缓存均不泄露；区分“删除文档残留缓存”和“真正的用户 ACL 决策缓存”，两者不是一个测试。

### RAGFlow 具体可复用接口

官方检索 API：`POST /api/v1/retrieval`；参数包含 `question`、`dataset_ids`、`document_ids`、`metadata_condition`、`rerank_id`、`keyword`、`use_kg`、`include_knowledge_compilation` 等。

这证明 **DSH 工具完全可以薄封装外部现成检索服务**，而不是为了调用 RAG 重建一个 agent loop。API 具体字段、返回定位与权限语义随版本锁定测试。

## 2. 真正的所有权与可复用边界

| 需求 | 优先使用 | IntraMate 是否应拥有 | 没有通过验证时的处理 |
| --- | --- | --- | --- |
| DOCX/PDF/OCR/表格解析 | RAGFlow DeepDoc / 既有解析 provider | **不拥有底层引擎** | 替换 Parser Provider；仅增加结构化适配 |
| Text Chunk / Embedding / BM25 / Vector / Rerank | 成熟产品和服务 | **不拥有算法/索引** | 调参数或更换服务；不另起自研全文/向量平台 |
| 原生章/节/条/款、附件和原文位置 | RAGFlow PageIndex/Parent-Child + 原件保真抽检 | **拥有映射/证据规范，不重造解析器** | 需精确 `ClauseLocator` 的时候加边车解析/校验 |
| 关系实体、职责链、GraphRAG | RAGFlow Graph/LightRAG | **拥有领域 Schema / 验证策略，不拥有通用图引擎** | 先基于带证据的关系表；是否需要图库由 E3 决定 |
| Agentic Query Decomposition | DSH 原生 Agent Loop + 可用检索工具；必要时可用 RAGFlow 原生 Agentic | **不拥有第二套 Loop** | 基线若无提升就不增加多轮 Agentic 开销 |
| 制度版次、生效/失效、废止、适用范围 | 既有 OA/制度管理台账为权威源 | **拥有可信台账同步与有效性过滤合同** | 权威源缺失则标注未知，不由 LLM 判定法律效力 |
| 用户/部门/文件 ACL | 上游已有 ACL 能力 + 企业 IAM/制度平台 | **拥有入口身份与下游一致执行的安全边界** | 无可信预过滤或跨图/缓存隔离则阻断生产使用 |
| 证据回指与审计 | 服务返回 chunk/source + DSH tools/session | **拥有可审计 Evidence Contract / Validator** | 无法回到原文确定条号/版本的答案降级或拒答 |
| 条件、例外、冲突识别 | 现成图/检索 + LLM | **拥有领域审阅/测试策略** | 输出并列证据和冲突，不擅断效力 |
| 全库“全部”归纳 | 批量遍历引擎+ Map/Reduce/可选 GraphRAG Global | **拥有枚举 Manifest / 全量覆盖证明** | 未遍历全量集合不得声称穷尽 |
| Desktop / Agent 运行、Tool Calling、Session | DSH/Cordis 原生 | **只做独立工具插件 + 编排 Skill** | 不修改 DSH core |

**切忌**从 RAGFlow 输出“条款编号 123”就直接信任：要用可检验的 `DocumentVersion + ClauseLocator + SourceSpan` 和原文件核对。RAGFlow 图的 Relationship 若未绑定到证据条款，不可单独给出银行合规结论。

## 3. 初始集成路径：插件而非 Fork

```text
IntraMate Desktop + DSH Agent Loop/Session
  └── policy-knowledge skill (可选；只负责银行任务策略)
       └── policy-knowledge tool plugin (thin adapter)
            ├── trusted identity / ACL + as_of + scope
            ├── search_policy_clauses()
            ├── get_policy_evidence()
            ├── analyze_policy_corpus()  # 显式范围枚举
            └── provider: RAGFlow REST / Dify / LightRAG / mock
                           ↕
            Policy authority & evidence mapping store
            (可从企业制度平台同步元数据)
```

DSH 具体依据：[ToolDefinition/受控执行](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/docs/subsystems/tools.md) 与 [Cordis Profile/Bundle/Tool pipeline](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/docs/architecture.md)。返回**结构化证据对象**让 DSH 组织回答，避免“RAGFlow Chat Agent 回答 → IntraMate 再回答”的双重生成与不可审计性。

工具契约一开始保持 engine-neutral：
```json
{
  "query": "示例查询",
  "as_of": "2026-10-10",
  "scope": {"document_type": "policy"},
  "results": [
    {
      "doc_version_id": "DOC-001:V2",
      "clause_id": "DOC-001:V2:ARTICLE-05",
      "locator": {"article_no": "第五条", "page": 3},
      "quote": "仅用于结构说明的示例原文",
      "is_authoritative": true,
      "evidence_status": "source_verified"
    }
  ],
  "coverage": {"enumerated": false},
  "retrieval_trace_id": "run-id"
}
```

> 此 JSON 是**目标返回语义**，不是现有 RAGFlow 的原样输出；适配器能否满足字段，需要实验验证。身份 ACL 不作为模型可控制参数下发；上面的 `scope` 是受控的查询缩小条件而非权限扩大。

## 4. 真实检索实验设计（未运行）

**不能拿宣传功能、静态单元测试或模型自动打分冒充“银行制度实测”**。本轮没有获得真实且可授权使用的银行制度样本，也没有接入运行中的目标版本 RAG 服务与离线模型，因此 E0–E4 均为 `NOT_RUN`。

### 数据与环境门槛

- 选择至少 100–300 份**有权限使用**的内网制度，覆盖通知/细则/办法/指引、重名制度、历史版本、跨部门职责、附件和扫描件。真实文件和内部条款不得进入公共 GitHub；仅保存匿名统计。
- 采集 `manifest`：制度数、文件/页数、识别出的条款数、版本数、重复/扫描/权限类别分布。
- 两条实验轨道，不能混淆：**A. End-to-End 从原始文件入库**检验解析/结构/索引；**B. 统一条款切分后导入**控制原始解析差异，比较检索算法本身。
- 固定 hardware、LLM、Embedding、Reranker、时间窗口/数据范围、向量维度、Top-K、Token 上限、温度与查询，且记录框架 tag/commit、容器 digest、配置与模型标识。
- 人工金标 Q1–Q6 合计 120–200 题，至少涵盖：明确编号、别名、上下文前提、例外、双制度引用、历史版本、互相矛盾、授权/未授权、真正全库穷举、确实无答案。
- 两名复核者标记至少一部分高风险题的 gold `doc_version_id + clause_id + required_evidence_set`，冲突由第三方仲裁，保留判定记录。

### 对照组（分阶段，避免实验爆炸）

| 实验组 | 检索路径 | 用途 |
| --- | --- | --- |
| E0 | RAGFlow v0.27.2 Hybrid + Rerank | 正式 baseline |
| E1 | E0 + Parent-Child / PageIndex | 验证条款边界与上下文 |
| E2 | E1 + Query decomposition（DSH Tool Loop，与 RAGFlow Agentic 对照） | 验证 Agentic 增益是否重复 |
| E3A | E1/E2 + RAGFlow Graph compilation | 上游内建 Graph 的收益 |
| E3B | E1/E2 + LightRAG mix | 是否有必要第二个图服务 |
| E4 | 枚举授权制度全集 → 按条款扫描/归并 vs GraphRAG Global summaries | 测“穷尽率”及主题发现能力差异 |
| C1 | Dify Hybrid / parent-child | 跨产品对照，观察部署/证据/权限差异 |

### 必须同时测检索、回答、权限、维护

| 指标 | 判定方式 |
| --- | --- |
| Clause Recall@5 / Recall@20 | 黄金条款是否位于召回集合，双版本不能互相顶替 |
| Evidence Set Coverage | 多证据问题所需条款是否被全部召回；不能用“命中任意一条”计正确 |
| Exact Citation & Provenance | 引用的制度编号、版本、条号/页码能否被原件证实 |
| Condition/Exception Recall | 生效条件、否定限定词、豁免条款是否覆盖 |
| As-of Version Accuracy | 按问询日期是否采用正确有效版本，不得混用历史条款 |
| Global Coverage | `eligible_document_count` 为分母，成功处理文件/条款，未处理和 ACL 排除项逐项报告 |
| Unauthorized Disclosure | 受限文件的任何正文、派生摘要、关系边或缓存信息被未授权用户取到，计致命失败 |
| Incremental Update Correctness | 新版上线、旧版撤销、关系/embedding/cache 是否一致刷新 |
| Operation | P50/P95、存储、GPU/CPU、单份/全量索引时长、模型 Token、失败恢复 |

### 决策 Gate（先定义原则，阈值在先导样本上锁定，不能倒过来迎合结果）

1. **G0**：未通过越权/泄漏和制度版本引用正确性门槛，禁止生产使用，不以平均问答分数抵消。
2. **G1**：若 E0/E1 已满足 Q1/Q2，则**不建设自研 Hierarchical Retrieval**；只有 ClauseLocator 证据映射确有缺口才薄补。
3. **G2**：若 E3A 对多跳 Evidence-Set Recall 的增益不足以抵消抽取、更新和安全成本，则**不引入 LightRAG/独立图数据库**。
4. **G3**：全库“所有”类任务无法提供完整枚举与漏项清单，则不得在产品上承诺穷尽。
5. **G4**：每一层新增技术必须可禁用、可回退，并有可重复实验报告；禁用后不得破坏基本条款检索。

## 5. 优先要做的源码/部署 Probe

1. **RAGFlow 输出契约**：在锁定版本上用 `POST /api/v1/retrieval` 看 `chunk_id/document_id/page/metadata/quote`；测试 PDF 章条定位与 PageIndex 的实际绑定；不要假定生成的 Tree 就是法定条号。
2. **权限闭环**：沿 `authenticated principal → dataset/doc permission → retrieval → graph expansion → rerank → answer/cache → audit` 做正负权限用例。1.0 rc1 已有已知权限限制，须隔离评测。
3. **制度变更**：删除/修订时搜索结果、图边、摘要和缓存的旧信息是否全部被版本标记/排除。
4. **DSH Tool 接口**：基于原生 `ToolDefinition` 注册读工具，返回结构化 JSON/证据；实测超时、撤销、权限、Session Replay，不 fork 核心逻辑。
5. **离线依赖**：完整列出 parser/embedding/reranker 的首次下载、模型镜像、Docker/CPU/GPU 要求、License 与企业网络边界。
6. **许可审查**：RAGFlow Apache-2.0；LightRAG/GraphRAG MIT；Dify/FastGPT 有附加使用条款；MaxKB GPLv3（不同用途、修改/分发及集成方式须单独合规审查）。

## 6. 本轮实证边界与决策

**已验证**：各仓库声明并公开实现了相应的基础检索/分块/图/Agentic 入口；RAGFlow 检索 REST API、DSH Tool/Cordis 扩展接口有正式文档与代码；RAGFlow 1.0 权限模型和升级风险有明确官方警告。

**尚未验证**：真实银行制度集的 clause recall、权限穿透、图关系真值、全库覆盖与模型/硬件成本；因此只建议候选架构，不批准上线和不采购大型图服务。

**下一份应产出的工件**：`04-experiments/benchmarks/policy-knowledge-engine/` 下的语料 Manifest、金标题目定义、Provider 运行清单、结果表和失败样本（不含真实保密内容）。
