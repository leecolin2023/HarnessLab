# 04 · Context Engineering：每轮模型调用到底应该看到什么？

> **学习目标**：理解 Agent 如何选择、保留、压缩和隔离信息，让每一次模型决策获得足够的上下文，而不是单纯追求更长的上下文窗口。
>
> **贯穿任务**：在固定的脱敏 JD 快照中，统计岗位职责或任职要求出现 RAG 的岗位技术要求，区分 required、preferred 和 unspecified，保留职位 ID、原文证据与统计分母。本文的职位内容、结果和伪代码均为教学示例。
>
> **学习位置**：[01 · Agent Loop](./01-agent-loop-execution-mechanism.md) 解释模型如何根据工具反馈继续行动；[02 · Workflow 与 Planning](./02-workflow-planning-multi-agent.md) 研究谁控制任务阶段；[03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md) 解释业务工具怎样把资料交给 Agent。本篇追问：**工具读取了大量资料，下一次模型调用究竟该收到什么？**
>
> **实现边界**：[HarnessLab SDK Minimal Phase 0](./labs/sdk-minimal-phase0/README.md) 已有 SDK 入口、Session 记录、工具调用配置和自动上下文压缩插件；它还没有实现大批 JD 的上下文对照实验，也没有可核验的真实压缩轨迹。

## 一、已经读取了几百份 JD，为什么不能每轮都交给模型？

假设我们让 Agent 完成一句任务：

> 找出职责或任职要求包含 RAG 的岗位，统计 Python、Milvus、BM25、Reranker 等技术要求，并区分“必须掌握”和“优先考虑”。

Agent 通过工具读取 20 条候选 JD，再扩大到 100 条，最终接触完整的固定快照。每一条 JD 的原始内容都有可能对统计有用；但当模型已经开始分析第 200 条时，第 1 条的完整正文还有必要出现在当前模型请求里吗？

如果每轮都重新携带全部历史，模型会反复看到旧工具输出、先前讨论、已经排除的解释和大量不相关的正文。这不仅增加输入量，也可能让过时结论重新干扰当前判断。

但是，如果直接只保留最近几轮，模型可能忘记用户最初规定：

> 只统计岗位职责和任职要求；“Milvus 经验优先”不能算作必备。

这条规则无论多早出现，都应在统计期间持续生效。

因此，我们要做的不是机械地“保留最近 N 轮”，而是回答：

**本轮要做什么判断？为作出这个判断，模型必须掌握哪些事实、约束、工具与证据？**

这就是 Context Engineering。它不只是改善系统提示词的措辞，而是决定信息**从哪里来、哪些进入本轮模型请求、怎样保持更新、什么时候不再携带**。

## 二、一次模型请求中的 Context 究竟来自哪里？

先看一个具体动作：模型正要判断职位 JD-001 中的 Milvus 属于必备还是加分要求。

它可能需要看到：

~~~text
任务口径：只分析岗位职责和任职要求
分类定义：required / preferred / unspecified
当前记录：JD-001
原文证据：有 Milvus 使用经验者优先
输出要求：技术、性质、job_id、原文证据及来源字段
可用工具：按职位 ID 重新读取完整 JD
~~~

这只是教学用的模型可见信息示意，并不是已经从当前 Phase 0 截获的实际请求体。

这里先区分三种不同的信息位置。

| 位置 | 保存什么 | 本轮模型会自动全部看到吗？ |
| --- | --- | --- |
| **外部数据源** | 完整 JD、数据快照、原始证据、结果表 | 不会，需工具读取或由应用装配 |
| **Session 与事件历史** | 用户输入、模型响应、工具调用和结果等运行记录 | 不一定，历史可被压缩、替换或投影 |
| **当前模型可见 Context** | 本轮实际收到的指令、消息、工具 Schema 和有关资料 | 这是模型本轮能直接使用的依据 |

这解释了两个看似矛盾的现象：

一份 JD 即使不再出现在模型请求中，也可以保存在数据层并在需要时重新读取；同样，Session 存有完整运行日志，也不意味着模型每次都重新接收所有日志。

### Context Engineering 和 Prompt Engineering 有什么关系？

Prompt Engineering 主要优化如何表达“请按什么规则做事”；Context Engineering 还要确定：什么时候提供具体 JD、工具返回几条记录、历史哪些结论仍然有效、从哪里补读原文。

Context 既可能包含固定的系统约束，也可能包含当前的工具定义、用户目标、工具结果、历史决策和动态检索内容。不同框架的装配方式可能不同。

在 [DeepSeek Harness Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md) 中，Runtime 每步派生模型可见的 Session 历史与工具声明；但它不会自动知道我们针对 job-rag 约定的 required / preferred 统计口径。这部分仍然需要应用明确提供。

## 三、最先应该优化的，为什么不是压缩，而是 Select？

在 500 条 JD 中找技术要求，第一步未必需要模型把所有 JD 一次读完。

假设工作流程先做确定性筛选和去重，然后逐批分析：

~~~text
固定、脱敏的 JD 快照
          ↓
程序：按指定字段选择候选
          ↓
程序：按稳定 job_id 去重
          ↓
当前批次的 JD + 明确统计口径
          ↓
模型：识别技术要求及限定条件
          ↓
保存结构化结果、原文证据及待核查项
          ↓
处理下一批
~~~

这里的 **Select（选择）** 是把当前子任务真正需要的信息送入模型，而不是在上下文满了之后才补救。

### 1. 模型需要看到多少原文？

分析 JD-001 时，模型可能只需要其职责、要求、职位 ID 与来源字段；计算所有岗位的技术频率时，模型不必再看到每一份原始 JD，而可以让程序统计已经校验过的结构化记录。

但是**结论的精简不能替代证据的保存**。

例如，仅给后续模型一条：

~~~json
{"job_id":"JD-001","technology":"Milvus","requirement":"required"}
~~~

存在风险：如果原文其实是“Milvus 经验优先”，这个结果已经错了，后续再怎么压缩都无法自动纠正。

更合适的是：

~~~json
{
  "job_id": "JD-001",
  "technology": "Milvus",
  "requirement": "preferred",
  "evidence": "有 Milvus 使用经验者优先",
  "source_field": "任职要求",
  "source_ref": "JD-001#requirements"
}
~~~

这组字段是教学设计，不代表 job-rag 当前数据库已采用完全相同的 Schema。

**当前模型拿到必要内容，完整原文保留在可回查数据源中**，才能在后续发现问题时重新核对。

### 2. 不在 Context 中的信息，怎样再次取回？

通过工具按 job_id、证据位置或搜索条件读取。这叫 Just-in-Time Retrieval（按需检索）。

例如，工具搜索可以只返回 ID、匹配字段、简短摘录和分页标记；模型真正要判断 Milvus 条件时，再读取 JD-001 的完整要求。

但不要把按需检索绝对化。每次读取也有延迟与失败风险；短小且每轮都必需的约束，直接放入上下文通常更简单。

## 四、工具一次返回上千行文字，怎样避免后面每轮重复携带？

想象一个接口：

~~~text
search_jobs("RAG") → 返回 500 份完整 JD
~~~

即使这次调用成功，工具返回内容也可能占用大量模型上下文。后续每轮继续携带这份长输出，就会不断增加输入负担。

最先值得改变的是**工具返回约定**：使用分页、限制数量、简短匹配信息、稳定 ID 和按需读取详情。

例如先返回：

~~~json
{
  "items": [
    {"job_id":"JD-001","matched_field":"任职要求"},
    {"job_id":"JD-002","matched_field":"岗位职责"}
  ],
  "next_cursor": "page-2"
}
~~~

这里的游标只是接口示例。它帮助模型知道下一步该查哪些职位，而不是直接把整个数据库塞给它。

### 已进入历史的超长工具结果怎么办？

还可以使用 Tool Result Pruning/Clearing（工具结果修剪或清理），让旧结果不再全部出现在下一轮模型上下文。

但是简单保留头尾存在明显风险：如果“Milvus 经验优先”位于长文中间，机械修剪可能恰好丢掉关键证据。

因此，应先让业务工具输出有界、结构清晰、可回查；修剪只是处理已有历史的辅助措施。

**当前 DeepSeek Harness 的具体情况**：框架有 [`dsh-compaction-tool-result-pruner`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-tool-result-pruner/README.zh.md) 插件，会在达到压缩压力条件后对超长工具文本执行有界头尾修剪，原始数据仍保留于 Session 日志。它并非在每次工具执行后立即修剪。

但核对当前 [`sdk-minimal/cordis.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)，**Profile 默认没有装配这款工具结果修剪插件**。因此 Phase 0 不应被描述为“已自动修剪每个超长工具输出”。

## 五、历史继续增长时，Compaction 到底怎样工作？

即使工具输出控制得很好，长任务仍会产生很多消息：用户目标、工具调用、失败重试、已确认的结论和下一步计划。

这时可以使用 Compaction（上下文压缩）：把较旧的模型可见历史转为更短的表示，同时保留近期必要消息。

### 1. 压缩改变的是什么？

例如，原始历史是：

~~~text
读取 JD-001 → Milvus 为 preferred，证据已保存
读取 JD-002 → Python 为 required，证据已保存
读取 JD-003 → 缺失完整任职要求，不能判断
……
~~~

一个理想化的压缩摘要可能是：

~~~text
统计范围：固定 JD 快照，仅岗位职责与任职要求
已处理：JD-001、JD-002、JD-003
已确认：JD-001/Milvus/preferred；JD-002/Python/required
待核查：JD-003 缺失完整任职要求
证据来源：可按 job_id 与 source_ref 回查
下一步：分析未处理的候选 JD
~~~

压缩后的模型可以依据摘要继续工作，而不必每轮重新读取已处理职位的全部原文。

但注意：**摘要不是完整原始证据，更不是业务 State 的唯一可信来源。**

### 2. 什么样的摘要会直接改变业务结论？

原文是：

> 由于 JD-003 缺少任职要求，目前无法判断其是否要求 Milvus。

如果压缩后变成：

> JD-003 要求 Milvus。

模型就会把一个未确认事实当成确定结论，最终统计也可能被污染。

对于 JD 研究任务，压缩尤其不能丢失：统计口径、否定和排除条件、required/preferred/unspecified 的区分、已处理职位 ID、证据引用、未解决疑点及当前进度。

这不是在要求模型生成漂亮的阶段总结，而是在确保后续推理仍然拥有**足以避免错误行动的状态信息**。

### 3. DeepSeek Harness 什么时候会自动压缩？

根据 [`dsh-compaction-basic` 官方文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-basic/README.zh.md)，它会结合路由模型的上下文容量、有效输出预留以及额外余量计算压力阈值。达到压力条件后，将较早的可压缩历史替换为摘要，保留近期历史；也支持对已确认上下文溢出的恢复性压缩。

当前官方默认阈值的计算可以概括为：

~~~text
W = 当前路由声明的上下文窗口
O = 该请求有效输出 token 预留
B = 额外余量，默认 65,536 tokens

触发阈值 T = floor(min(W × 0.8, W − O − B))
近期逐字保留预算默认约为 (W − O) × 0.16
~~~

这不是所有模型通用的“使用到 80% 才压缩”规则。

**对 32K、50K 等较小上下文模型，默认的 65,536 token 余量不适用。** 需要按具体模型配置 `headroomTokens`、输出上限等，确保策略与路由容量一致，不能仅凭 Profile 已启用插件就假定压缩一定正常触发。

压缩本身通常还要发起一次额外的模型摘要请求，因此它并不是零成本操作，也可能引入信息损失。

### 4. 现有 Phase 0 已经验证过压缩吗？

当前 [Phase 0 配置](./labs/sdk-minimal-phase0/README.md) 使用的 `sdk-minimal` 确实加载了 `dsh-compaction-basic`、token meter 和 Session JSONL 持久化。

但是一项执行 `pwd`、`ls` 的短任务通常不足以证明压缩发生。仓库也没有可核验的完整模型—工具—压缩轨迹。

若要验证，必须检查对应路由容量、真实输入 token、压缩相关事件和后续模型可见历史。当前 [`session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py) 只统计事件类型及数量，无法单独证明压缩没有改变必备/优先等业务语义。

## 六、旧历史不再输入模型，为什么仍要保留原始证据？

Compaction 是有损压缩。即使摘要质量很高，也不能保证所有细节都被保留下来。

当模型后来发现“JD-001 的 Milvus 到底是必备还是优先”有争议时，它应该可以重新取回完整原文，而不是只能从压缩摘要中猜测。

因此，更稳定的结构是：

~~~text
固定脱敏 JD 原始快照（完整、只读）
           │
           ▼
结构化结果表（技术、条件、job_id、source_ref）
           │
           ▼
当前模型 Context（目标、口径、进度、当前证据）
           │
      ┌────┴────┐
      ▼         ▼
 压缩旧历史   按需取回原始 JD
~~~

这也有助于区分两个问题：

- **Context 管理**：本次模型推理应该看到什么？
- **业务数据保存**：即使模型上下文改变，原始证据和分析结果能不能回查？

Session 持久化是运行日志方面的能力，不能代替业务方建立可靠的职位快照和统计结果表。

## 七、为什么还需要 Isolate：不同任务要不要共享上下文？

考虑同时进行两个工作：

- 分析一批 RAG 岗位的技术要求；
- 排查某个模型服务的网关故障。

如果它们共享同一条持续增长的模型历史，大量无关的网关日志可能干扰 JD 分析，数百条职位内容也会挤占故障排查上下文。

Isolate（隔离）的核心不是“必须使用 Multi-Agent”，而是让模型每次只看到当前职责需要的信息。

### 1. 不创建子 Agent，也能隔离吗？

可以。应用可分别组织每条 JD 的分析输入，在汇总阶段只提供已经校验过的结果：

~~~text
JD-001 分析：统计口径 + JD-001 原文
JD-002 分析：统计口径 + JD-002 原文
……
汇总阶段：统计口径 + 已校验结构化结果
~~~

这样每次模型请求更聚焦，模型也不必把其他职位的长文本同时保留。

### 2. 什么时候需要独立 Session 或子 Agent？

当子任务需要长时间探索、不同工具或权限、独立历史时，可以考虑使用独立 Session 或子 Agent。但这会增加通信、汇总和核查的成本。

DeepSeek Harness 框架有 Subagent 插件家族，**`sdk-minimal` 并未默认加载 Subagent**。不能因为理论上可以隔离，就写成当前 Phase 0 已经实现了子 Agent 上下文隔离。

另外，上下文隔离不等于数据权限隔离：即使模型看不到另一个任务的聊天记录，只要工具仍有权限读取对应文件，就不意味着数据安全。权限问题属于后续 07 专题。

## 八、Prompt Caching 是不是另一种压缩？

不是。

**Compaction** 用更短的表示替换旧历史，减少后续模型输入的内容。

**Prompt Caching** 尽可能复用相同输入前缀先前已经完成的计算，降低重复处理的成本和延迟。缓存并不负责判断哪些职位证据值得保留，也不会自动让无关信息从 Context 消失。

例如，连续请求若共享稳定的统计规则和工具 Schema，模型服务可能复用这段不变前缀。

但是如果中途压缩或重排了较早历史，前缀发生变化，缓存复用可能下降。

因此，不应单看“压缩后请求变短”，还需比较压缩触发的额外模型请求、可能减少的重复输入、缓存变化以及业务准确性。

[OpenAI Prompt Caching 官方说明](https://developers.openai.com/api/docs/guides/prompt-caching)可以帮助理解这一权衡。但具体缓存门槛、计费、保留时间和是否支持缓存，必须依据实际模型提供方确定，不能直接套用到所有 DeepSeek 服务。

**缓存优化的是重复计算；Context Engineering 优先解决的是模型拿到的信息是否恰当。**

## 九、怎样判断 Select、Compress、Isolate 真的改善了任务？

按 [学习路线阶段 5](./LEARNING_PATH.md)，需要用同一份固定的脱敏 JD 快照比较不同输入方式。

| 对照方案 | 主要变化 | 要观察什么 |
| --- | --- | --- |
| A：完整历史 | 尽量反复携带全部原文与旧工具结果 | 输入增长、遗漏及混淆 |
| B：Select | 当前 JD + 统一口径 + 可回查 ID | 是否减少无关输入而不损失证据 |
| C：Select + Compress | B 加上历史压力下的摘要 | 压缩后是否仍保留否定、条件和进度 |
| D：Select + Isolate | 按职位或阶段组织独立上下文 | 是否减少干扰、增加多少协调成本 |

这是建议的实验设计，不是已经运行的数据报告。

### 1. 先看业务正确性

比如“有 Milvus 使用经验者优先”有没有错误归类为 required；职位 ID、原文证据和计数分母能否回查；缺失字段是否被误当成否定或必备。

如果 Token 用量下降，却增加了这些错误，就不能说设计更好。

### 2. 再看真实成本

记录输入 token、模型调用次数、工具查询次数、压缩摘要请求数、缓存指标（如果服务提供）及端到端延迟。

压缩器自己发出的请求也有成本，不能只统计最终生成报告的调用。

### 3. 最后看能否定位错误来源

理想情况下，能够从一条错误统计追溯到：

~~~text
错误的 required / preferred 结果
              ↓
当时模型看到了什么原文与规则
              ↓
工具实际返回了哪条 JD
              ↓
是否发生了压缩、修剪或上下文隔离
              ↓
原始快照和证据引用是否仍在
~~~

只看到最终模型回答，即使看上去很合理，也不能确定错误发生在数据选择、工具输出、模型判断还是历史压缩阶段。

## 十、DeepSeek Harness 做了什么，新 Agent 还要负责什么？

| 机制 | DeepSeek Harness / sdk-minimal | 新 Agent / 业务应用 |
| --- | --- | --- |
| 每轮历史与工具 Schema 装配 | Runtime 已提供基础机制 | 明确任务口径、提供当前 JD 及必要规则 |
| 自动压缩 | 已装配 `dsh-compaction-basic` 和 token meter | 核对模型容量、阈值与真实触发情况 |
| 超大工具结果修剪 | 框架有可选插件，Profile 未默认加载 | 评估是否需要启用，以及修剪会否丢失证据 |
| Session 记录 | JSONL 持久化 | 脱敏检查实际工具输出和请求行为 |
| Select / 按需检索 | 能运行模型—工具调用 | 实现分页、只读查询、ID 及证据定位 |
| Isolate | 可以由应用分隔请求；框架有可选子 Agent | 明确隔离单元、权限与汇总契约 |
| 业务数据与验证 | 不自动提供职位库和统计口径 | 保存固定快照、校验条件性质、分母和引用 |

最容易混淆的是：**框架支持自动摘要，和应用具有可靠的业务上下文管理，并不是同一回事。**

即使 DSH 能把长历史压缩为摘要，是否保留了 “preferred 而非 required”、是否还能够定位原 JD，仍要由业务数据设计与结果验证保证。

## 十一、整篇文章最终要说明什么？

从几百份 JD 的分析开始，我们看到了三个相互配合的办法：

**Select**：每轮只提供当前任务必需的资料，把大量原始证据留在可回查的数据源中。

**Compress**：历史增长后用摘要替换较旧内容，保留有效规则、关键结论、证据入口和未决问题。

**Isolate**：为不同职位、工作阶段或子任务准备合适的独立上下文，减少无关信息互相干扰。

它们不是必须按顺序启用的三个插件，也不是“越多越先进”。从这个 JD 案例来看，先设计有限而可回查的业务工具返回，再考虑压缩和隔离，通常更符合任务本身的需要。

最后还要记住三件不同的事：

**Context 是当前模型判断的依据；Session 是系统保留的交互与事件记录；业务 State 和原始数据决定工作能否持续、复核和恢复。**

接下来的 05 · State、Session、Checkpoint 将重点研究中断之后如何继续工作。保存摘要或历史，并不自动等于恢复了完整业务任务。

## 参考阅读

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)
- [02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md)
- [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)
- [学习路线](./LEARNING_PATH.md)
- [HarnessLab Phase 0 实验](./labs/sdk-minimal-phase0/README.md)
- [上下文管理旧文：网关排障扩展案例](./01-harness-context-management.md)
- [DeepSeek Harness · sdk-minimal Profile](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/README.zh.md)
- [DeepSeek Harness · sdk-minimal 组合配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)
- [DeepSeek Harness · 自动压缩](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-basic/README.zh.md)
- [DeepSeek Harness · 工具输出修剪](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/compaction/compaction-tool-result-pruner/README.zh.md)
- [Anthropic · Effective context engineering for AI agents](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
- [OpenAI · Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching)
