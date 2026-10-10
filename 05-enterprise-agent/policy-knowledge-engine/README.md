# 企业制度知识引擎 · 设计讨论 Draft 0.1

> 状态：**Discussion / 未批准** · 2026-10-10  
> 目标产品：[`dsh-intramate`](https://github.com/leecolin2023/dsh-intramate/tree/dsh-intramate-dev)  
> 研究归属：HarnessLab / 05-enterprise-agent  
> 边界：本文件是问题澄清与候选架构，不是已批准 SRS、选型结论或完成的实现。正式 SRS 放在 [specifications](../specifications/)，DSH 专属设计放在 [implementation-profiles/deepseek-harness](../implementation-profiles/deepseek-harness/)；代码仅放产品仓库。

## 0. 核心判断

**建设的是可验证的“企业制度证据与分析能力”，不是再造一个通用 RAG 或 Agent Harness。**

目标：面向数百份企业制度，支持条款级查询、跨制度职责/流程/控制要求关联分析、全库级主题归纳；回答能定位原文件中的具体制度版本与条款，展示检索覆盖、证据不足、冲突与不确定性。采用离线内网运行，安全过滤先于检索与聚合。

候选技术：Agentic Retrieval + Hierarchical Retrieval + GraphRAG；**三者是需要对照实验的候选检索策略，而非一开始都必须自建/启用的架构前提**。


## 第一轮技术选型审计

- [Build vs Reuse 审计（2026-10-10）](./build-vs-reuse-audit-2026-10.md)：已核实上游源码/API/版本与许可；推荐 RAGFlow 为第一候选；银行制度语料实测尚未执行。

## 1. 用户问题和查询类型

| 类型 | 例子（均为虚构示例，非真实制度结论） | 必须有的证据 | 候选路径 |
| --- | --- | --- | --- |
| Q1 精确条款 | “授信批复查询权限由哪条制度约束？” | 制度名称、版本、条号、原文定位 | 标题/编号/关键词 + 向量 Hybrid → Rerank → 原文核验 |
| Q2 条件与例外 | “A 业务在何种条件下需要复核？有哪些例外？” | 条件、例外、适用范围及原文 | 条款检索 → 父级/相邻条款补全 → 条件对照 |
| Q3 跨制度职责 | “某事项的发起、审批、执行、监督分别由谁负责？” | 每条职责及其制度出处、关系路径 | 角色/流程实体检索 + 可选 Graph Traversal → 多证据聚合 |
| Q4 制度冲突与沿革 | “新旧规定是否一致？现在哪版有效？” | 发布/生效/废止/修订日期及冲突条款 | 版本过滤 + 双向查找 + 并列举证；有歧义时不擅断 |
| Q5 全库归纳 | “全库中关于权限和留痕的控制要求有哪些？” | 库范围、扫描覆盖率、各分类来源条款 | 枚举可访问制度全集 → 分批抽取/归并 → 缺口审查；图社区报告可作辅助 |
| Q6 证据不足 | “没有明确约定的事项能否视为允许？” | 已检索范围、缺失证据和不确定性 | 明示不可据此推断；建议人工确认 |

**讨论焦点：** Q1/Q2 依赖严格的条款定位，Q3/Q4 依赖可追踪的关系和版本，Q5 依赖明确的全集扫描计划；单一“相似度 Top-K → 生成答案”无法承诺完整性。

## 2. 知识对象先于检索算法

### 2.1 原始制度结构（必须保真）

`Document → DocumentVersion → Chapter → Section → Article → Paragraph → Attachment`。

保留：制度编号/名称、发布机构、适用对象、业务领域、密级、发布日期、生效日期、失效日期、修订/替代链、目录层级、条款号、附表、原始文件哈希、文件页码/标题路径/字符区间等。区分“本版有效”“历史有效”和“有效性未确认”。

- 通过文档解析与规则识别保留显式“第×章/第×条”等法条结构；对于 PDF 扫描件/OCR、非标准编号和表格，标记可信度及人工复核需求。
- **不可只存摘要或扁平 chunk。** 检索命中条款后能回到父条款、相邻条款、定义和附件；必要时返回原文局部上下文。
- 一段原文可以有若干索引表示，但必须指向同一个不可变 `EvidenceLocator`；模型摘要不得代替制度原文。
- 版本更新不直接覆盖历史；同步变更全文索引、关系索引、摘要和权限缓存，并记录索引版本/构建状态。

### 2.2 领域事实与关系（候选增强）

建议从可核验的制度原文抽取下列概念：
- `Actor/Role`：机构、部门、岗位、责任主体；
- `Action/Process`：发起、审核、审批、执行、监督、记录、报告；
- `ControlRequirement`：权限、双人复核、限额、时间要求、留痕、例外；
- `BusinessObject`：客户、额度、合同、押品、授信事项等；
- `Applicability`：适用范围、业务类型、前提条件、例外条件、有效期间；
- `NormativeRelation`：引用、补充、替代、废止、细化、可能冲突。

**每条关系必须保存 `source_clause_id`、原文引用、抽取器/模型版本、置信度和复核状态。** 区分文本“明确规定”与模型“语义推断”。未核实的关系不能作为确定性的审批/合规结论。

### 2.3 建议最小内部数据契约（非数据库选型）

- `DocumentVersion`：文档标识、版次、来源、时间有效区间、密级/ACL、源文件校验值；
- `Clause`：稳定条款 ID、父子层级、规范化文本、原文位置、所属版本；
- `EvidenceRef`：`document_version_id + clause_id + locator + quoted_span`；
- `RelationClaim`：主语、关系、宾语、适用条件、证据条款、核验状态；
- `RetrievalRun`：查询、身份权限范围、检索分支、候选数、耗时、索引版本、拒答/缺口原因；
- `CoverageManifest`：全库扫描分母、已扫描文件/条款、失败/权限不可访问集合、时间截面。

## 3. 候选的分层检索路径

```text
用户问题（身份、权限、指定日期/制度范围）
            |
      查询理解 + 意图路由
            |
   +--------+--------+-------------------+
   |                 |                   |
精确条款路径       跨制度关联路径      全库归纳路径
   |                 |                   |
元数据/编号匹配    Query Decomposition  枚举授权范围全集
Hybrid (BM25+Dense)   Hybrid Seeds       分片提取控制事实
   |               Graph Traversal*      主题归并/缺口复检
父子层级上下文     多跳证据扩展*          Community Reports*
   |                 |                   |
   +-----------------+-------------------+
                     |
        去重 / Rerank / 权限复核
                     |
        Evidence Pack（原文+版本+位置）
                     |
     证据充分性/矛盾/覆盖门禁 → 模型答复
                     |
       引用明细 + 检索覆盖 + 不确定性
```

`*` 只有经增益实验后才启用；Graph Traversal 与社区归纳不要求从首日就采用专用图数据库。

### 3.1 三种概念不要混淆

1. **制度的原生层级**：章、节、条、款、附件，是必须保留的确定性事实结构。
2. **Hierarchical Retrieval**：先定位制度/章节，后定位条款；或按条款展开父级定义、相邻上下文，防止“有条文没前提”。
3. **RAPTOR/GraphRAG 衍生层级**：依模型聚类和摘要构造的语义树或社区层级，用于跨文档主题归纳；不是原版制度目录，更不能覆盖它。

### 3.2 Agentic 何时介入

- 简单问题默认使用有限步骤的确定性检索，不强制每次都让 Agent 多轮分解。
- 复杂问题允许 Agent 将问题拆成子问题（例如发起职责/审批职责/复核要求）并依据结果决定补检。
- 对“所有/全部/有哪些”这类全库完整性任务，**必须有可审计的范围枚举、分批扫描与覆盖清单**；仅靠 Agent 自主反复 Search 或 GraphRAG 社区摘要，不得宣称穷尽全库。
- 设置最大检索轮数、超时和预算；无法满足目标时输出已覆盖范围与遗漏，不伪造完整性。

## 4. 与 DSH 的边界：薄集成、可换引擎

参照 [DSH 架构文档](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/docs/architecture.md)：DSH 是 Cordis 插件组成的 Agent Harness，具备工具注册与受控执行、会话、MCP 等扩展入口。初步建议：

```text
dsh-intramate Desktop / Agent
    ├── DSH 原生 Agent Loop、Session、Tool Policy（尽量不 fork 改内核）
    ├── Institution Knowledge Skill（任务策略、追问、证据输出规范）
    └── Knowledge Tools Adapter（薄插件 / MCP 适配，待源码 Probe）
           ↕ 稳定 Tool/Service Contract
       Policy Knowledge Service（独立离线进程或可嵌入服务，待评测）
           ├── Ingestion & provenance / ACL / versioning
           ├── Parser + Hierarchy-preserving clause store
           ├── Search adapters: metadata / lexical / dense / rerank
           ├── Optional relation index / graph / corpus summaries
           └── Evidence verification & audit
```

候选工具能力：
- `search_policy_clauses(question, date_scope?, policy_scope?, top_k?)`：查条款，返回可复核证据；
- `get_policy_evidence(evidence_ids)`：读取版本化原文及父级上下文；
- `trace_policy_relations(topic, relation_types?, depth?)`：跨制度关系探索；
- `analyze_policy_corpus(topic, scope, as_of?)`：全库扫描/归纳，返回 Coverage Manifest。

安全注意：**身份、ACL、权限范围从可信宿主上下文提供，不应由模型自主传入或扩大。** 所有检索分支、关系跳转、缓存、摘要生成与结果聚合都实行同一权限约束；不得仅在最终输出阶段过滤。注入文档是数据，不能把制度文本中的命令执行成 Agent 工具指令。

当前仅验证了 DSH 存在通用工具、插件与 MCP 扩展机制；具体适配接口、插件位置、生命周期与安全钩子须通过源码定位和运行实验确认，不在此假设某个代码模块已经可直接复用。

## 5. Build vs Reuse：候选引擎，非预先定案

| 能力 | 可研究的成熟方案 | 倾向 | 需实测的风险 |
| --- | --- | --- | --- |
| 版式解析/制度层级 | 现有 Office/文档工具、Docling、RAGFlow 解析链 | 复用解析，薄加条款结构化 | 表格/扫描件、中文法条、条号回填与位置保真 |
| Hybrid / Rerank | Qdrant 等检索设施及本地 embedding/reranker | 复用 | 中文长标题、制度编号、细粒度 ACL、离线依赖 |
| 语义树/父子检索 | 条款层级索引；RAPTOR 等作为对照 | 先做原生层级，再比较 | 语义摘要漂移、检索覆盖 |
| 图索引/图检索 | LightRAG、Microsoft GraphRAG（或简单关系表） | 先对照，再决定 | 抽取误差、成本、增量同步、版本化和权限 |
| 全库聚合 | 分区 Map/Reduce、GraphRAG Global / DRIFT | 基于覆盖指标评测 | 全库 completeness、摘要漏项与推断性关系 |
| Agent 决策 | DSH 原生 Tool Calling / Session / Policy | 保留上游，薄接插件 | 误路由、循环检索、模型差异、工具调用成本 |

**特别提醒：** Microsoft GraphRAG 的 Global Search 有助于“全库主题”类问题，但它基于社区报告，不天然保证“全部制度条款”都已逐项核对。GraphRAG fast 模式的官方文档指出其默认英文相关 NLP 配置，中文制度需单独验证；不能据英文表现直接认定适配内网中文制度。

## 6. 安全、治理、证据规则（从首版纳入）

- **制度权威性**：内部正式生效版本优先；草案、废止版本、外部规范分开标记，具体效力顺位须按企业提供的正式规则判断。
- **时间语义**：所有结果具备 `as_of` 时间视角；同一条款不同版本不可混作一个当前事实。
- **引用链**：每个可执行结论都附 `制度名 / 编号 / 版本 / 条款号 / 定位`；支持打开原件核对。
- **冲突检测**：矛盾条款并列报告；不能仅凭“发布日期较新”自动覆盖不同层级或适用范围的规范。
- **权限隔离**：最小权限，含分片、向量检索、关系边、摘要缓存、索引构建和审计日志。
- **缺证拒答**：没有证据或未覆盖全库时，明确不确定性与已检索范围；不将“未检索到”转成“制度没有规定”。
- **可信执行**：检索文档视为不可信输入，防提示注入；工具访问与索引管理保留审计。
- **公共仓库安全**：HarnessLab 中只保存合成样例、脱敏示例和代码设计，**不上传真实企业制度、敏感条文或内网路径**。

## 7. 验证优先：先基线再升级

在同一个离线硬件、同一组中文制度、同一个问答模型与预算下，设置可复跑实验：

| 实验 | 查询方式 | 要证伪的假设 |
| --- | --- | --- |
| E0 | 元数据 + BM25 / Dense Hybrid + Rerank | 基线是否已足够解决条款检索 |
| E1 | E0 + 原生制度层级/父子上下文 | 是否显著减少“截断前提、遗漏例外” |
| E2 | E1 + Query Decomposition | 复杂职责分析是否真正受益 |
| E3 | E2 + 图关系增强（关系表 / LightRAG / GraphRAG 对照） | 跨制度多跳召回提升是否抵消抽取错误/成本 |
| E4 | 枚举全集 + 分片聚合，对照 GraphRAG Global/DRIFT | 全库覆盖、主题发现与核验成本如何取舍 |

建议优先制作 **60–100 道人工核验金标题**，按 Q1–Q6 分层，包含同名制度、修订覆盖、跨章节前提、反例、冲突、ACL、全文未规定等难例。若真实制度不可用于公共实验，用合成制度样本验证工程正确性，真实业务评测留在隔离内网执行。

指标（阈值尚待基线测量后确定）：
- 索引：制度/条款结构保真率、文档版本识别率、位置定位成功率、增量索引正确率。
- 检索：条款 Recall@K、关系边 Recall、跨文档来源覆盖、失败样本与重复证据率。
- 回答：引用精确率、事实忠实度、条件/例外完整性、冲突识别率、应拒答时拒答率。
- 全库：授权范围覆盖率（分母明示）、遗漏率、扫描失败与不可访问集合。
- 运行：P50/P95 时延、Token/索引成本、内存/GPU、纯离线可部署、模型替换后的性能变化。
- 安全：越权访问与信息泄露用例必须通过，发现即阻断发布。

先证明 E0/E1 可靠，再决定 E2–E4 是否值得投入；**不要让“用了 GraphRAG”取代“比简单方案强多少”这一工程证据**。

## 8. 本轮要确定的开放问题

1. 数据边界：仅银行内部管理制度，还是同时包含操作规程、监管法规、业务手册、通知和 FAQ？不同文种是否有不同权威等级？
2. 数据形态：源文件是 Word、可复制 PDF、扫描 PDF，还是 OA/制度管理系统导出？是否有可靠的制度台账、修订/废止标识？
3. 查询范围：“全库”是当前用户可见的有效制度集合，还是含历史版本的全量制度？是否要求指定时间点追溯？
4. 权限来源：可否取得组织/部门/用户级制度查阅 ACL？本地桌面知识库与共享知识服务的权限边界如何区分？
5. 知识维护：增量制度发布和修改频率多高；关联抽取允许多少人工审核？
6. 场景优先级：首版更侧重精确条款、跨制度职责，还是全库级穷举清单？这决定首个对照实验。
7. 内网约束：模型/embedding/reranker 可用清单、GPU/CPU、操作系统、是否允许容器以及软件审批边界。
8. 治理标准：是否存在正式制度效力顺序与冲突裁定规则？没有规则时系统只负责呈现差异，不裁定。

## 9. 下一步（建议，不代表已完成）

- A. 用 10–20 份**可公开或合成**制度构建最小原生层级索引与条款引用链；核对文本抽取保真。
- B. 建一份含 Q1–Q6 的金标样例与覆盖清单，先运行 E0/E1 基线。
- C. 并行进行 DSH 源码 Probe：找清 Tool/MCP 的装载、参数校验、policy、结果记录与 Desktop 打包边界。
- D. 比较至少两种成熟知识服务在内网环境的依赖、更新、权限、中文检索和图能力。
- E. 讨论收敛后转入 `SRS-...` 和 DSH Implementation Profile；再在 `dsh-intramate-dev` 产品分支实现。

## 10. 官方资料与验证线索

- [DSH architecture](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/docs/architecture.md)
- [Microsoft GraphRAG query modes](https://microsoft.github.io/graphrag/query/overview/) / [Global search](https://microsoft.github.io/graphrag/query/global_search/) / [indexing methods](https://microsoft.github.io/graphrag/index/methods/)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [RAPTOR](https://github.com/latentsp/raptor-rag)
- [Qdrant hybrid + reranking](https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/)
- [RAGFlow](https://github.com/infiniflow/ragflow)

以上方案只是“可调研选项”，各自的离线依赖、许可证组合、中文效果与升级维护风险尚未按项目环境核验。
