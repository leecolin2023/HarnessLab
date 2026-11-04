# 10 · 端到端评测与优化：报告出了问题，怎样知道是哪一环出了错？

> **学习目标**：从真实业务目标出发，建立贯穿数据、工具、模型、Agent Runtime、验证与交付的评测方法；学会依据实际产物和执行轨迹定位失败，并通过受控对照判断一次改造是否真正有效。
>
> **贯穿任务**：统计岗位职责或任职要求中出现 RAG 的职位，提取技术要求，区分必备、优先、混合及未明确条件，生成可回查职位 ID 和原文证据的报告。
>
> **承接关系**：[08 · 任务验证与结束条件](./08-task-verification-and-completion.md) 研究单次任务是否允许交付；[09 · 部署与服务化](./09-deployment-and-serving.md) 研究任务怎样稳定运行。本篇追问：**系统反复运行这项任务，为什么有时正确、有时漏检、误判或成本过高？是哪一环导致的？**
>
> **事实边界**：本文结合 [job-rag 的 RAG 技术要求实验](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/README.md) 和 [2026-11-01 真实模型报告](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/results/2026-11-01/models/report.md) 讨论已有事实。该实验已真实调用 Embedding、重排与生成，但人工复核栏尚未完成，**目前没有经人工 Gold 支持的完整准确率**。[HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 仍是独立 SDK 教学实验，未实现 JD Research Agent 的完整端到端任务。新增指标、例子及实验方案是教学设计，不冒充已运行结果。

## 一、报告写得很完整，为什么仍可能没有回答用户的问题？

用户最初的问题是：

> 岗位职责或任职要求出现 RAG 的职位有哪些？它们的相关技术要求是什么，哪些是必备、哪些只是经验优先？

Agent 可能先调用检索工具，找到八份相似 JD；随后调用模型生成一份报告，列出 Python、Milvus、LangChain、Reranker 等技术，也附上引用。

但如果候选主样本实际上有几百条，生成模型只看到了八份重排后的证据，这份报告能说明什么？

**它可以说明八份来源中有哪些技术要求，却不能直接说明全库一共有多少符合条件的职位。**

特别是，当模型把“本轮检索证据共八份”写成“本次统计了八个 RAG 岗位”，读者会以为它完成了全库枚举。

这时，模型可能没有编造任何 JD 内容。错误更可能发生在**数据范围、工具能力与最终业务目标之间的映射**：检索工具提供的是有限 Top-K 样本，用户需要的却是基于完整候选集合的频次统计。

因此，一项任务存在几种不同的“成功”：

~~~text
检索成功：获取了一批相关 JD
         ↓
生成成功：模型根据这些 JD 写了回答
         ↓
业务成功：在指定范围内完整统计，分类正确，证据可回查
~~~

前两种成功不足以推出第三种。

要真正优化 Agent，不能只问“模型最后回答得好不好”，还要看**它被要求解决的是什么问题，执行中究竟接触了哪些数据**。

## 二、08 已经设计了 Checker，为什么还要再做 Evaluation？

[08](./08-task-verification-and-completion.md) 研究的是某一次任务的交付判断。比如报告将“Milvus 经验优先”标成 required，Checker 应拒绝通过。

但我们还有一组新的问题：

- 这种错误出现在哪类 JD 中，偶然发生还是重复发生？
- 模型是否真正看到了“经验优先”原文？
- 换成混合检索后，是否找回了以前漏掉的岗位？
- 增加 Checker 能修复多少真实错误，又会误改多少正确记录？
- 两个版本都能生成报告，哪个在同样的任务集上更稳定、成本更合理？

这些是**系统级评测**问题。与单次验收的区别在于：

| | Checker：单项验收 | Evaluation：端到端评测 |
| --- | --- | --- |
| 核心问题 | 这一次任务可否交付？ | 这套实现在哪些任务上可靠，在哪些任务上失败？ |
| 依据 | 当前任务契约、产物及证据 | 固定样本、独立判断、真实运行与轨迹 |
| 结果 | 通过、失败、待复核、需要局部修正 | 错误分布、指标、故障归因、版本差异 |
| 目的 | 阻止错误交付 | 找到真正值得修改的环节 |

Checker 可以是系统的一部分，却不能因为 Checker 宣布通过，就把它自己的输出当作全部标准答案。

**评测必须保留独立于被测模型的判断依据。**

## 三、已有 job-rag 实验实际上验证了什么？

我们不必为这篇文章虚构一个数据集。[job-rag 的现有实验目录](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/README.md) 已经固定了 `jobs-20261023.csv`，包含 **593 条职位记录**。

按照 [已归档报告](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/results/2026-11-01/models/report.md) 的不同筛选范围：

- 全描述扩展匹配约 **426 条**；
- 按职责/任职要求章节规则确定的主样本为 **384 条**；
- 未知章节与加分字段等仍存在需要人工复核的边界；
- 已经执行真实文档 Embedding、混合召回、完整 JD 重排与模型生成；
- 已保存逐职位、逐证据及生成输出的人工审核表。

这些数字是**不同规则下的统计对象**，不是几种模型的准确率，也不能把 426 减去 384 的差额直接解释成“系统漏掉了 42 个真实 RAG 岗位”。

现有模型生成还只解释其有限检索来源，不能用 Top-K 推算全库频次。全库的规则统计是另一条执行路径。

### 已经具备哪些观察能力？

实验保存了 `manifest`、模型响应与请求哈希、生成结果、MCP 调用轨迹以及待复核的 `review_jobs.csv`、`review_evidence.csv`、`review_generation.csv`。

这足以证明某些**执行事实**：模型是否调用、检索是否执行、有哪些输入范围、生成使用了哪些来源、失败续跑记录是否存在。

### 还不能得出什么结论？

由于人工结论尚未完成，不能计算可信的总体语义准确率，也不能把规则命中量当成经过人工确认的 required 或 preferred 数量。

更不能把 job-rag 的 RAG 模型链路成绩，直接当成 **HarnessLab 中完整 Agent Loop + Workflow + Checker + 故障恢复** 的端到端成绩。这两个项目当前验证的对象仍然不同。

**能证明执行过，不等于能证明业务判断正确；能统计规则命中，不等于已得到人工 Gold。**

## 四、Gold 应该怎样做，才不会把系统自己的答案当成真值？

假设我们评测“Milvus 是否是职位的必备技术”。

如果直接用规则匹配“Milvus”生成 `gold.jsonl`，那么规则的错误也被写进 Gold；模型修正了规则的错误，反而可能在评测中被扣分。

因此，Gold（经确认的参考判断）要有独立审核流程，不能由待测方案自己生产。

### 一条职位和一条技术要求不是同一个判断单位

**职位层**判断当前 JD 是否属于指定 RAG 候选范围：

~~~json
{
  "job_id": "JD-001",
  "rag_candidate": true,
  "evidence": "负责 RAG 知识检索系统",
  "review_status": "adjudicated"
}
~~~

**技术要求层**判断该职位提到了什么技术、条件性质是什么：

~~~json
{
  "job_id": "JD-001",
  "technology": "Milvus",
  "requirement": "preferred",
  "evidence": "有 Milvus 使用经验者优先",
  "source_field": "任职要求",
  "review_status": "adjudicated"
}
~~~

这是教学 Schema，不是现有 job-rag 数据表的已确认字段契约。真实评测要映射现有 `job_id` 与原文格式。

一条职位可能有多项技术要求，也可能是 RAG 候选但没有明确技术要求。不能因为没有抽取记录，就直接推断职位没有处理。

### 为什么要保留不确定样本？

“必须掌握 Python”和“Milvus 经验优先”比较明确；但“了解向量数据库，包含 Milvus、FAISS”等表达可能需要结合完整上下文和事先确定的分类口径。

对混合条件、否定、加分字段、章节缺失，标注者应保留争议和裁决记录。没有一致依据时不要为了形成唯一 Gold 而强判。

### 怎样选择样本？

首轮可按问题类型选择可人工核对的困难案例：明确必备、明确优先、混合条件、否定、长 JD、多技术共现、重复职位、无明确技术与章节缺失。

这种样本适合发现失败模式，**不必然代表全部 593 条职位的总体错误率**。如果后续目标是估计全库水平，还要加入按已知抽样机制获得的代表性样本，必要时按分层比例加权。

开发集用于修复问题；保留测试集用于最终评价；历史失败案例形成回归集。不能一边不断针对同一批测试数据调 Prompt，一边宣称它仍然是独立盲测。


## 五、用户只要一份报告，为什么评测还要分这么多层？

最终关注的是完整的业务成果。但如果只给每份报告打一个“通过或不通过”，我们仍无法判断失败来自哪里。

因此指标应沿真实执行路径展开：

| 执行层 | 需要回答的事 | 典型评测方式 |
| --- | --- | --- |
| 输入与候选 | 是否找对职位、取对字段、去对重复？ | 候选 Precision / Recall、重复率、漏检数 |
| 检索与工具 | 正确原文是否被成功读取并进入候选？ | 工具成功率、证据 Recall@K、数据版本一致性 |
| 语义提取 | 技术名称和条件性质是否理解正确？ | 技术提取 F1、required/preferred 混淆矩阵 |
| 证据 | 引用是否来自正确 JD，是否真的支持结论？ | 定位成功率、证据支持度 |
| 任务结果 | 报告是否满足约定的全部要求？ | 任务通过率、待复核率、严重错误数 |
| 运行 | 有多少模型调用、工具调用、重试与额外成本？ | 延迟、Token、成本、失败恢复情况 |

这里没有一个指标天然凌驾于其他指标。不同业务问题需要不同评测对象。

### 1. 候选集合为什么要有 Precision 和 Recall？

以是否应纳入指定 RAG 候选集为例：

- TP：应该纳入且确实纳入的职位；
- FP：不该纳入却被纳入的职位；
- FN：应该纳入却被漏掉的职位。

定义：

\[
P=\frac{TP}{TP+FP},\qquad
R=\frac{TP}{TP+FN},\qquad
F_1=\frac{2PR}{P+R}
\]

其中 Precision 关注纳入集合是否准确；Recall 关注有没有漏掉本来应该纳入的 JD。

但如果 Gold 只标了少量正例，那么“没标过的 JD”不能自动当负例，计算出的指标也不能冒充全库真实召回率。

### 2. 为什么技术识别和要求性质要分开评测？

模型可能正确发现“Milvus”这项技术，但把 `preferred` 错判成 `required`。

如果只评“技术有没有被提取”，这种模型可能得到高分；对求职者真正关心的“必备还是优先”，却回答错误。

所以先匹配职位和技术项，再评价对应的条件性质；对多技术 JD，技术提取通常是多标签问题。不能把不同职位中相同技术的标签互相匹配来充当正确结果。

### 3. 为什么证据定位成功也可能得出错误结论？

假设报告引用：

> 有 Milvus 使用经验者优先。

原句存在，职位 ID 也正确；但报告写“Milvus 是必备”。**引用存在不代表引用支持结论。**

因此至少要区分两个层次：

- 证据定位：这句话是否真实位于对应 JD 和字段；
- 证据支持：它是否足以支持所写的 required/preferred 判断。

前者容易用程序检查；后者需要明确的语义标准和必要时的人工判断。

### 4. 为什么最终任务成功率更严格？

一次任务可能已找到大部分职位、提取结果整体不错，但因为把八条检索来源误写成全库分母，最终仍不应通过验收。

任务成功率是**针对事先约定的完整交付条件**计算的。它不能通过平均几个局部指标自动推导，也不能用 Runtime 的 `finish_reason="completed"` 代替。

## 六、报告出错后，怎样沿真实执行轨迹找原因？

假设某条 JD-081 实际应该被纳入候选，却没有出现在最终报告。

一种常见但没有依据的判断是：“模型漏掉了它，换更大模型吧。”

但错误可能早在模型看到原文之前就已经发生。

我们可以从头检查：

~~~text
固定快照里有 JD-081 吗？
       ↓
字段解析后是否保留完整职责与要求？
       ↓
筛选和去重时是否正确保留 JD-081？
       ↓
检索或业务工具是否返回它？
       ↓
模型本轮 Context 是否实际包含其关键原文？
       ↓
模型是否正确识别技术与限制条件？
       ↓
结构化记录是否正确汇总到报告？
       ↓
Checker 是否发现遗漏？
~~~

每一步都可能是第一个偏离点。

比如快照里根本没有这条 JD，问题属于数据采集；检索没有返回，可能是召回问题；检索返回了，但长工具输出被截断，可能是 Context 问题；原文完整提供，模型仍误判“优先”为“必备”，才重点研究语义理解与提示词。

**评测不仅要给错误命名，还要确定错误第一次在哪一环出现。**

### 怎样把不同层次的证据连起来？

建议为每次实验保存这样的关联：

~~~text
evaluation_case_id
  └── task_id / run_id
       └── snapshot_hash + rule_version
            └── session_id
                 ├── step / model_request_id
                 ├── tool_call_id
                 ├── job_id / source_ref
                 └── artifact_id / validation_result
~~~

这是一份建议的追踪模型，不是 DeepSeek Harness 当前自动提供的全部字段。

其价值在于：发现“JD-081 漏报”时，可以跳回具体一次工具调用、模型输入与报告记录，而不是在几十万字的日志里搜索“看起来可能有关”的句子。

## 七、DeepSeek Harness 的 Session 已经有日志，还需要业务追踪吗？

有需要，因为两者保存的信息并不相同。

[HarnessLab Phase 0](./labs/sdk-minimal-phase0/src/run_phase0.py) 已记录 Session ID、模型名、结束原因、总耗时、事件数量和事件类型；[`session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py) 负责统计 JSONL Session 文件中的事件种类。

这足以作为运行观察入口，但**事件类型计数并不能告诉我们哪个职位被误判、模型当时收到哪条 JD 原文、报告为何引用了错误分母**。

### 1. Runtime 原生事件能够证明什么？

DeepSeek Harness 的 [Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md) 会形成模型请求、工具调用、执行结果、Turn/Step 及结束原因等历史；[JSONL 持久化](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-persistence-jsonl/README.zh.md) 可以保留事件流。

但不能仅凭“文件存在”就宣称已保存**每次模型请求完整的原始 HTTP 请求体**。要根据对应模型适配器和实际事件字段核实记录粒度。

### 2. SDK 的 `RunResult` 能做什么？

`RunResult` 包含 `session_id`、`events`、`notifications`、`final_response` 与 `finish_reason`。这可以确定一次运行的会话与结束情况，并用于进一步找到原生 Session。

业务侧仍要把 `task_id`、快照、职位 ID、结果表、Checker 结果和报告产物跟它关联。

### 3. 框架是否提供更丰富的统计组件？

有。[`dsh-session-stats`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-stats/README.zh.md) 可以从完整 Session 事件折叠出 Turn/Step 次数、模型和工具耗时、首 Token 时间等统计。

但当前 [`sdk-minimal` 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) **没有默认装配 Session Stats 投影插件**，不能因为框架支持就声称 Phase 0 已有完整指标面板。

即使装配成功，这些执行统计也不会自动产生 JD 的候选 Recall 或技术要求分类 F1。

### 4. 是否要把 Session 原样全部传到外部平台？

不要默认这么做。

DeepSeek Harness 的 [Session Telemetry](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-telemetry/README.zh.md) 支持从会话历史产生外发副本，但文档明确提醒：**没有部署脱敏规则时，内容可能原样离开进程**；投递也采用尽力而为方式，不能替代权威日志。

Phase 0 已设置关闭额外 Session 日志上传，正常模型请求仍然会发出。

所以更适合的思路是：**默认轻量结构追踪，必要时经授权导出完整诊断**。敏感 JD 原文、凭据、用户信息和模型请求内容应按用途、权限和留存期约束，不应为评测而无差别收集。

## 八、真实案例：为什么 Top-K 的八份来源不能变成全库频率？

在 [job-rag 的归档报告](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/results/2026-11-01/models/report.md) 中，规则路径和模型生成路径承担不同职责：

~~~text
全库规则路径：
固定 CSV → 全量筛选 → 去重 → 词表与章节统计
                      ↓
                  全库规则频次

检索生成路径：
用户问题 → 混合召回 → 模型重排 → 少量 JD 来源
                                      ↓
                                  模型解释
~~~

如果把模型检索来源数量当成整个数据集的分母，就产生了严重的范围错误。

例如“Milvus 在八份来源中出现三次”不能推导出“384 条主样本中 Milvus 出现比例为 37.5%”：两者分母不同，Top-K 也不是对 384 条随机抽样所得。

### 这属于检索问题还是生成问题？

需要先看系统本来要求模型做什么。

如果工具接口只向模型传入八份来源、却要求它回答全库频率，那么 Workflow 或工具契约就没有提供完成任务所需的事实。

如果工具已经传入了全库统计结果，并明确给出了分母，模型仍然选择八份来源替代统计，那才进一步研究生成与结果验证问题。

对这种场景，合理的最小修正可能是：

1. 将规则统计或经全库审核的聚合结果明确传入报告阶段；
2. 把 Top-K 标记成示例证据，而非全量统计集合；
3. 最终 Checker 交叉核对分母、来源类型和数字；
4. 若语义标签尚未审核，则明确称为“规则提及频次”，而非“必备技术占比”。

这个例子展示的是一个更通用的原则：

**根因若是数据范围和结果契约错误，直接更换更强模型通常不是最有依据的第一步。**

## 九、一次优化到底改善了什么？为什么要控制变量？

假设我们一次做了三件事：

- 将 BM25 改成混合检索；
- 将全文 Context 改成摘要；
- 再增加一个语义 Checker。

报告通过率提高了，我们却无法知道究竟是哪一项起主要作用。

因此优化要从**可以被证据支持的失败假设**出发。

### 方案 A：验证“漏检是检索造成的”

固定同一份 JD、同一问题、同一去重口径、同一 Gold，仅比较检索方式：

~~~text
检索 A：BM25 候选
检索 B：混合检索候选

先比较：真正相关岗位能否进入候选集
再比较：固定下游分析流程后的最终业务结果
~~~

如果 B 找回更多职位，但最终报告依然错分 required/preferred，那么新增问题可能在语义提取或汇总阶段。

### 方案 B：验证“Checker 是否真能减少错分”

固定同一批已取得原文的职位和基础模型输出：

~~~text
不加 Checker：基础提取 → 汇总
加入 Checker：基础提取 → 校验 → 有界局部修正 → 汇总
~~~

必须同时记录：

- 原本的真实错误数；
- 被 Checker 正确发现的错误；
- Checker 正确修复了多少；
- Checker 是否把原本正确的结果改错；
- 额外增加多少模型调用与时间。

如果两种方案连输入都不一致，很容易把“额外读到了更多 JD”的收益误判为 Checker 的能力。

有时多项变化确实必须一起部署。可以做整体 A/B 比较，但应将结论限定为“新组合整体改善”，不能声称已经证明每个组件的独立贡献。


## 十、模型输出本来就会变化，怎样证明一次优化是真的？

同一份 JD、同样的 Prompt，模型重新执行一次也可能给出不同表述；服务端模型别名、路由、工具和检索索引也可能变化。

所以“今天 B 比 A 好一次”不足以得出普遍结论。

### 1. 先冻结能冻结的条件

至少记录：

- JD CSV 的内容哈希与数据快照；
- `job_id` 映射、筛选和去重规则版本；
- Prompt、工具 Schema、检索配置、索引版本；
- 代码提交与运行环境；
- 模型路由名、已知的模型版本与输出参数；
- 生成时实际使用的来源集合；
- 成功、失败与重试的真实调用记录。

现有 [job-rag 实验](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/README.md) 已保存源 CSV 哈希、`manifest`、模型调用记录与结果归档，这些可以直接复用。

但是，**记录模型别名不一定能锁定提供商内部的具体模型版本**，不能把“可记录配置”误写成“完全确定性复现”。

### 2. 在相同案例上做配对比较

例如对四条教学 JD，记录 A、B 是否达到对应标准：

| 案例 | 方案 A | 方案 B | 观察 |
| --- | --- | --- | --- |
| JD-001：优先条件 | 错 | 对 | B 修复错误 |
| JD-002：必备条件 | 对 | 对 | 结果一致 |
| JD-003：否定表述 | 对 | 错 | B 引入退化 |
| JD-004：混合条件 | 错 | 错 | 两者都需要改进 |

这张表纯属说明，不是已有的四条真实运行结论。

它能让我们看到**改善了什么、破坏了什么**，而不是被总体平均分掩盖。

### 3. 何时需要重复运行和估计不确定性？

当方案涉及模型自由生成、工具调用路径不固定或外部服务波动时，关键方案应在固定案例上重复执行，观察结果波动。

对足够多的独立案例，可以按职位或完整任务做配对统计、区间估计或分层分析。**不能把同一职位切出来的十个 Chunk 误当成十个独立岗位样本**。

困难案例集很适合暴露错误，但即使指标精确到小数点后两位，也不能把它自动外推成全部市场招聘 JD 的准确率。

## 十一、质量更好但成本翻倍，算不算优化成功？

假设增加 Checker 后，错分明显减少，但每条 JD 又调用模型三次，最终报告的耗时也增长。

能不能接受，取决于业务要求：必须满足的质量和安全约束是什么？减少错误带来的收益是否超过额外开销？

因此建议分两步评价：

**第一步，先看质量底线。** 对不能接受的统计分母错误、无证据结论或越权访问，不能因为更便宜就放行。

**第二步，在合格方案之间比较成本和速度。**

比“每次模型调用消耗多少 Token”更有业务意义的，是：

- 每份**经验证合格**的报告的端到端成本；
- 合格任务的 P50 / P95 完成时间；
- 每条已正确处理的 JD 的模型与工具开销；
- 失败重试、摘要与 Checker 额外调用的比例；
- 仍需人工复核或返工的工作量。

一个方案模型调用更少，但漏掉的 JD 更多、需要大量人工补救，它的总成本可能反而更高。

此外，Token 使用量不等于供应商实际扣费。若没有可信账单数据，就要把估算和实际费用分开；提供方没有返回的用量也不能凭猜测补造。

**优化的目标不是让所有指标都越低越好，而是在任务合格的前提下，让资源投入有明确回报。**

## 十二、把前九篇串起来：发现故障后先看哪一层？

前面学过的 Agent Loop、Workflow、Tools、Context、State、权限、Checker 和服务化，不应该变成各自孤立的名词。

遇到一项具体失败，可以从实际症状找到优先排查范围：

| 发现的问题 | 先定位到哪里 | 可能的最小改进 |
| --- | --- | --- |
| 应纳入职位没进入候选 | 数据、字段解析、检索 | 修正候选规则或召回方式 |
| 同一职位被计算两次 | 数据归并与 `job_id` | 稳定去重键和快照版本 |
| 工具取得了原文，模型没看到 | Context、裁剪与工具结果 | 有界返回、按需回查 |
| “经验优先”被写成必备 | 模型判断、规则口径与 Checker | 明确标签、针对性复核 |
| 原文确实存在却不支持结论 | 证据验证 | 增加语义支持度检查 |
| Top-K 被当作全部岗位 | 统计口径、Workflow、汇总 | 分离全量事实与局部例证 |
| 工具写成功，结果没保存 | State、Checkpoint、幂等 | 持久结果与恢复核查 |
| Runtime `completed`，报告却不合格 | 验收契约和 Checker | 业务完成状态与运行结束分离 |
| 两个用户看到相同产物 | 权限、Session 归属、隔离 | 服务端鉴权、独立工作区 |
| P95 延迟很高 | Worker、模型、工具与重试 | 先分阶段定位耗时，再优化容量 |

表中的“先定位”不是说其他层绝无问题，而是提醒我们不要从最终失败直接跳到“换模型”或“拆多 Agent”。

如果最先偏离的是候选集合不完整，往模型里加入更多复杂推理未必有用；如果模型已经获得正确原文却仍持续错分，检索改造也未必是主要方向。

## 十三、下一步最小实验应该实际产生什么成果？

当前真实业务实验已有固定 CSV、规则路径、模型调用、`review_*.csv`、`manifest` 和归档报告。下一步不需要先把这些全部推倒重来。

更合理的是在已有证据上补齐**人工 Gold、任务级关联与受控对照**。

| 建议的逻辑产物 | 作用 | 是否已有可复用基础 |
| --- | --- | --- |
| 评测案例集 | 固定问题、输入范围、候选 JD 与难例类型 | 已有固定 CSV 与基准问题 |
| 人工裁决 Gold | 判断候选、技术关系、要求标签与原文证据 | 已有空白 `review_*.csv`，需完成裁决 |
| 运行清单 | 记录数据、代码、规则、模型与 Prompt 版本 | 已有 `manifest` 和哈希 |
| Agent 运行轨迹 | 关联 Task、Session、请求、工具与职位证据 | 现有 RAG 轨迹可复用，Agent 追踪尚需建设 |
| 预测结果 | 每条职位或每项任务的实际结构化输出 | 已有部分统计和生成产物 |
| 验收结果 | 明确通过、失败、待复核及失败原因 | 需要接入独立业务 Checker |
| 对照报告 | 相同输入下 A/B 的错误、成本与回归变化 | 需要针对具体假设组织 |
| 回归案例 | 历史明确失败及其最小可复现输入 | 可从本轮人工复核中逐步沉淀 |

这是一组**逻辑职责**，不是要求把现有 job-rag 目录强制改名成新的文件结构。真正用到的原始 JD 与逐次运行记录也应按脱敏和版本要求保存。

### 先做哪一步价值最大？

以一条能找到原文的失败案例开始：

1. 从现有 `review_jobs.csv`、`review_evidence.csv` 或 `review_generation.csv` 中完成一条人工复核。
2. 找到对应固定 JD 原文、模型输出、检索来源与统计口径。
3. 写清楚“期望结果是什么，现有系统在哪一步首次偏离”。
4. 只针对该原因设计一个最小修正，并保留旧实现对照。
5. 在相同案例上比较，随后观察其他回归案例是否退化。
6. 真实改善可复核后，再扩大到更有代表性的样本。

例如，第一次确定的问题若是“检索来源被当作全库分母”，优先修改统计来源与验收，而不是先重新跑全部 Embedding。

### 这些工作现在完成了吗？

尚未。

[job-rag 的现有实验](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/README.md) 已运行模型链路，提供了复核入口，但人工 Gold 尚未完成；[HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 仅提供 SDK 最小实验与结构化运行观察。

所以本篇可以确认“已有足够的工程材料开展下一步评测”，但**不能宣称 Agent 的端到端准确率、通过率或优化提升已经得到验证**。

## 十四、哪些是 DeepSeek Harness 提供的，哪些需要新 Agent 自己完成？

| 能力 | DeepSeek Harness / 现有工程 | 新 Agent 与评测工程的责任 |
| --- | --- | --- |
| 模型与工具循环 | Harness 已有 Agent Loop 和执行器 | 无须重新开发通用 Runtime |
| Session 执行历史 | 有事件流及 JSONL 持久化 | 将 Task、职位、模型请求、证据与报告关联 |
| 基础运行信息 | SDK 有 `RunResult`；框架有可选 `session-stats` | 检查实际插件配置和指标口径 |
| 遥测与诊断导出 | 框架有可选 Session Telemetry | 定义授权、脱敏、必要字段和留存 |
| 规则/检索/生成实验 | job-rag 已有实际执行与归档 | 明确全量计数与有限来源生成的不同用途 |
| 可信 Gold | 现有人工审核表是入口，不是已裁决标签 | 逐条核实、保留争议、完成裁决 |
| 语义与任务质量指标 | Runtime 不会自动产生 JD 语义正确率 | 定义分母、匹配关系、证据标准与业务验收 |
| A/B 对照及回归 | 可利用既有数据快照与运行记录 | 控制变量、复核改善与退化 |
| 长期优化 | 框架负责通用执行机制 | 用真实失败推动最小且有效的改造 |

这里继续遵守贯穿全系列的职责边界：

**使用成熟 Harness，重点不是自己重写模型循环或底层评测框架，而是围绕真实任务建立可信数据、可核查证据、可解释决策与持续改进机制。**

## 十五、整个 Agent Runtime 学习体系最终建立了什么能力？

从 00 到 09，我们分别理解了：

- 为什么模型要依靠 Agent Runtime 才能持续调用工具和推进工作；
- Workflow、Planning、工具与 MCP 怎样决定任务的控制权和能力边界；
- Context、State、Session、Checkpoint 怎样保存与组织信息；
- Retry、Sandbox 与审批怎样约束实际行动；
- Checker 怎样决定业务成果是否能交付；
- 服务怎样让多个用户持续、安全地管理任务。

这套知识如果只形成技术名词清单，其实还不够。

面对一份错误的 JD 分析报告，我们最终应能够回答：

**从数据到工具、模型、Context、Workflow、Checker 与报告，究竟是哪里第一次出现偏差？证据是什么？应该改动哪一个最小环节？怎样在相同案例上证明改造有效，同时没有引入更大成本或新错误？**

这样才形成完整的学习闭环：

~~~text
定义真实业务问题与完成条件
           ↓
运行 Agent，保留真实产物与执行轨迹
           ↓
独立检查候选、语义、证据、运行和任务成果
           ↓
定位第一次偏离的环节
           ↓
提出最小且可验证的改造假设
           ↓
固定样本，对照运行，检查回归和成本
           ↓
保留有效修改，再回到真实任务继续观察
~~~

**优秀的 Agent 工程判断，不是把每个技术组件都做得复杂，而是知道当前问题到底发生在哪里，选择合适的机制，并有证据证明这次修改确实值得保留。**

这正是“端到端评测与优化”要补上的最后一环。

## 参考阅读

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop](./01-agent-loop-execution-mechanism.md)
- [02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md)
- [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)
- [04 · Context Engineering](./04-context-engineering.md)
- [05 · State、Session、Checkpoint](./05-state-session-checkpoint.md)
- [06 · 执行控制与故障恢复](./06-execution-control-and-failure-recovery.md)
- [07 · 权限、Sandbox 与人工审批](./07-permissions-sandbox-human-approval.md)
- [08 · 任务验证与结束条件](./08-task-verification-and-completion.md)
- [09 · 部署与服务化](./09-deployment-and-serving.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md)
- [job-rag：RAG 技术要求实验](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/README.md)
- [job-rag：2026-11-01 完整模型链路报告](https://github.com/leecolin2023/job-rag/blob/main/experiments/rag_tech_requirements/results/2026-11-01/models/report.md)
- [job-rag：历史检索排名实验](https://github.com/leecolin2023/job-rag/blob/main/experiments/README.md)
- [DeepSeek Harness · Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)
- [DeepSeek Harness · Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md)
- [DeepSeek Harness · Session Stats](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-stats/README.zh.md)
- [DeepSeek Harness · Session Telemetry](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-telemetry/README.zh.md)
- [DeepSeek Harness · sdk-minimal 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)
