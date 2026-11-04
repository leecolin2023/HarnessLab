# Agent Runtime 学习路线：从构建真实 Agent，到理解并优化运行机制

> 学习主线：**先让一个 Agent 真正完成任务，再沿着执行轨迹追问它为什么能够完成、何时会失败、怎样改善。**
>
> 首个实践底座：DeepSeek Harness Python SDK。首个贯穿案例：JD Research Agent（岗位研究智能体），对接后续的 job-rag 能力。  
> 方法：借鉴 Google Cloud Tech《Modern AI Agents: From Theory to Production》的应用教学顺序；用 SenseWright Learning 的机制解释方法回到原理。  
> 本文是**课程与实验设计**，不是已经完成的实验报告。示例和验收标准不代表已运行、已通过或已实现生产部署。

## 一、为什么采用“构建应用 ↔ 解释机制”的学习方式？

我们已经有两类学习材料：

- Google 的 Agent 教程，从博客写作 Agent 开始，逐步加入工作流、MCP、上下文和云端部署。
- HarnessLab 的 Agent Runtime 原理文档，从“模型回答问题”为什么不足以完成工作任务出发，解释 Agent Loop、工具、Context、State、可靠性和结果验证。

如果只跟着框架教程做，很容易知道如何调用 SDK，却无法解释一次任务在内部究竟怎样运行。如果只学习 Runtime 的概念，又可能知道一堆名词，却不能判断真实系统为什么成功或失败。

因此每一课都使用同一个往返过程：

```text
具体业务目标
    ↓
先搭建一个最小可运行功能
    ↓
观察真实输入、工具调用、状态变化与输出
    ↓
发现一个需要解释的问题
    ↓
阅读通用原理和 DeepSeek Harness 对应实现
    ↓
改动一个变量，必要时做对照实验
    ↓
把机制写入 agent-runtime 根目录
    ↓
用新的认识改进同一个 Agent 应用
```

这里的“问题驱动”不是强迫每个术语都先编一个悬念，而是在需要做工程选择时追问：原来怎样做、为什么遇到限制、系统加入了什么机制、机制改变了什么、代价与边界在哪里。

**学习文档必须与现有代码建立双向对应。** 原理文章提出一个能力时，项目解读不能停留在“这个框架很强”，而要回答：①应用源码有无实现？②如果由 SDK/Runtime 提供，实际装配了哪个组件、代码入口在哪里？③是否完成真实运行验证？④没有实现时，是否属于基础循环必需，还是只有复杂任务才需要的增强机制？一旦发现原理文章把可选功能写成了每个 Agent 默认自带的能力，应先修正原理，再继续设计工程实验。例如 [Phase 0 逐行代码解读](./labs/sdk-minimal-phase0/01-code-walkthrough.md) 先对照基本执行循环（模型决策、工具执行、反馈、继续或结束），再对照复杂任务的增强机制（显式规划、计划修订、业务验证、人工审批）。

**本路线的真正交付有两种：**

1. 一个逐步演进、能够真实完成 JD 研究任务的 Agent 应用。
2. 一套与具体 SDK 解耦、可以迁移到其他 Agent/Harness 的原理文章。

每一课完成后，都应该既能展示“这一步做了什么”，也能解释“系统为什么会这样工作”。

---

## 二、仓库职责：HarnessLab 管通用机制与教学实验，job-agent 管业务应用

按代码的实际用途区分：通用 Runtime 的最小教学实验与其逐行解读留在 HarnessLab；真正读写招聘数据、生成岗位报告、实现业务检查的 Agent 放在 job-agent。

```text
HarnessLab/
├── agent-runtime/
│   ├── README.md                         # Agent / Runtime 基础原理
│   ├── LEARNING_PATH.md                  # 原理与实验学习路线
│   ├── 01-agent-loop-execution-mechanism.md
│   ├── 02-workflow-planning-multi-agent.md
│   ├── 03-tool-calling-and-mcp.md
│   ├── 04-context-engineering.md          # 主线 04 文章
│   ├── 05-state-session-checkpoint.md      # 状态、Session 与恢复点
│   ├── labs/
│   │   └── sdk-minimal-phase0/
│   │       ├── README.md                 # Phase 0 实验入口
│   │       ├── 01-code-walkthrough.md    # 与本实验源码同步维护的逐行解读
│   │       ├── src/                      # SDK 执行 + Session 统计
│   │       ├── scripts/                  # Docker 运行入口
│   │       ├── docker/                   # 容器镜像
│   │       ├── config/                   # Profile Patch
│   │       └── tests/                    # FakeHarness 离线测试
│   ├── job-agent/                        # 旧文章的迁移导航
│   └── 01-harness-context-management.md
└── .github/workflows/agent-runtime-phase0-offline.yml

job-agent/
├── README.md                             # 独立 JD Research Agent 项目入口
└── docs/                                 # 历史实验解读的迁移提示
```

分工原则：**HarnessLab** 维护通用机制、可复现的 Agent Runtime 教学实验，以及与教学实验源码同步更新的代码解读；**[job-agent](https://github.com/leecolin2023/job-agent)** 只承载岗位检索、JD 分析、证据与报告等业务实现。后续若新增与业务无关的 Harness 实验，先放在 HarnessLab 的 `labs/` 中，而不是让业务项目背负通用示例。

现有 `materials/agent-runtime/` 仍为外部资料归档，不用于存放实验代码。

### 根目录的目标知识版图

下表是**原理知识版图**，其中 00 的入口为 [README.md](./README.md)，01 为 [Agent Loop 运行机制专题](./01-agent-loop-execution-mechanism.md)，02 为 [Workflow、Planning 与 Multi-Agent 专题](./02-workflow-planning-multi-agent.md)，03 为 [Tool Calling 与 MCP 专题](./03-tool-calling-and-mcp.md)，04 为 [Context Engineering 专题](./04-context-engineering.md)，05 为 [State、Session、Checkpoint 专题](./05-state-session-checkpoint.md)；其他主题仍按学习与实验进度完善。原有 `01-harness-context-management.md` 保留为网关排障扩展案例及旧链接入口，不再作为 04 的主阅读文件。

| 原理主题 | 要回答的核心问题 | 首个对应实践阶段 |
| --- | --- | --- |
| 00 · Agent 与 Runtime | 为什么一次模型回答不等于任务完成？Runtime 执行什么？ | 0、1 |
| [01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md) | 一个 Agent 任务从启动到结束，Runtime 如何处理模型响应、工具结果和循环控制？ | 1、2 |
| [02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md) | 固定步骤与模型动态决策如何组合？何时拆成多个 Agent？ | 3 |
| [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md) | 模型提出调用、工具实际执行、MCP 协议分别负责什么？ | 2、4 |
| [04 · Context Engineering](./04-context-engineering.md) | 每轮调用如何选择、压缩和隔离必要信息？ | 5 |
| [05 · State、Session、Checkpoint](./05-state-session-checkpoint.md) | 任务状态、会话历史和恢复点各自保存什么？ | 6 |
| 06 · 执行控制与故障恢复 | 超时、重试、幂等、取消和补偿怎样协同？ | 7 |
| 07 · 权限、Sandbox 与人工审批 | 如何限制模型对真实系统的行动权限？ | 7 |
| 08 · 任务验证与结束条件 | 文件生成、工具成功与任务成功有什么不同？ | 3、8 |
| 09 · 部署与服务化 | 单个本地 Session 怎样演变为可安全服务多个用户的应用？ | 9 |
| 10 · 端到端评测与优化 | 怎样通过任务结果和轨迹定位问题，而不只评价最终文案？ | 8、9 |

**00 与 01 的内容边界**：00 解释为什么从模型回答扩展到完成工作任务，以及 Agent Loop / Runtime 的总体职责；01 不再重新定义“模型决策 → 工具执行 → 反馈”，而研究 **一次任务实际怎样进入模型调用、按响应分支执行工具、把结果交给下一轮、以及在什么边界结束**。01 应以 [SDK Phase 0 实验](./labs/sdk-minimal-phase0/README.md) 的真实 Session 为验证目标；现有源码只能证明执行路径，尚无真实轨迹时不得宣称实验已完成。

原理文章应按照知识依赖和实际实验安排逐篇完善，**不必先写完 00—10 才开始编码**。

---

## 三、贯穿项目：JD Research Agent

### 3.1 为什么选择这个案例？

首个目标是解决一项真实、可追踪、可逐步增加难度的任务：

> **统计岗位职责或者任职要求中出现 RAG 的岗位，其相关技术要求是什么？区分必备要求与加分项，并提供能够回查的职位证据。**

这个问题具备合适的复杂度：

- 数据有明确载体：job-rag 的职位数据和完整 JD。
- 不能仅用关键词次数直接代替业务答案：需要识别岗位是否真正涉及 RAG、判断技术名称的作用，以及“必备”与“加分”。
- 需要调用工具读取数据，而不是单凭模型记忆回答。
- 容易形成可核查产物：职位 ID、原文摘录、统计口径、计数分母、Markdown 报告。
- 后续可以自然引入检索、规划、状态恢复、权限与评测，不需要每一章换一个虚构业务场景。

### 3.2 我们希望它最终能够完成什么？

初始版本只做一个小任务。逐步扩展后，希望它能够：

1. 理解“RAG 岗位”这一筛选条件，并明确字段与统计口径。
2. 调用工具检索候选岗位，按稳定职位 ID 去重，读取完整 JD。
3. 区分技术要求是岗位必备、优先条件，还是仅在岗位描述中提及。
4. 汇总 Python、Milvus、BM25、Reranker 等具体技术出现的频率，并保留出处。
5. 判断是否需要补充检索、澄清统计范围或修正错误。
6. 输出结构化研究报告，包含样本范围、分母、技术分类、频次、限制和可回查的职位证据。
7. 对结果执行规则检查与证据检查；失败时能明确修复或终止，而不是伪造成功。
8. 能保存任务进度，在适当条件下继续未完成的分析。

**不要一开始就做多个 Agent。** 先让一个 Agent 借助有限工具完成闭环，发现需要独立控制或验证的职责时，再考虑 Planner、Researcher、Writer 和 Checker 的拆分。

### 3.3 数据与成果边界

- 使用从 job-rag 导出的**只读、脱敏、固定快照**开始实验；先选少量完整 JD 用于功能验证，再扩大到已有的数百条岗位。
- 不直接让高权限 Agent 操作 `job-rag` 的生产仓库、私有凭据或正在更新的主数据。
- 统一保留 `job_id`、职位名称、JD 原文、数据来源与采集时间等必要字段；实际字段映射以 job-rag 当前 Schema 为准。
- 规则统计和模型判断应分离：先明确统计口径，再评价模型是否选对数据和理解对内容。
- **有证据的产出**高于“看上去完整的报告”。暂不能确认的判断应标记待核查。

---

## 四、课程设计：每一阶段都经历“实现—观察—解释—改进”

### 阶段 0｜认识 DeepSeek Harness，运行第一个受控任务

**阅读顺序：** 首先阅读 [Phase 0 基本执行循环与复杂任务机制的代码对照](./labs/sdk-minimal-phase0/01-code-walkthrough.md)，分清“已有代码、Runtime 内置、尚未实现”；再在隔离环境执行实验。阶段 0 不要求独立 Planner 或业务 Checker，因为它首先研究的是最小 Tool Calling 循环。

**先要完成的事**

使用 Python SDK 在隔离环境中启动一个最小 Agent，对一份演示文本进行简单回答，得到真实响应。

**教学任务**

- 阅读 [DeepSeek Harness 官方 Python SDK 入门](https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk)。
- 安装 Python 3.10+、SDK 与匹配的 Runtime；准备可用的 DeepSeek 兼容 API。
- 明确设置独立的 `cwd` 工作目录和 `dsh_home`。
- 使用官方 `sdk-minimal` profile，从一个新 Session 发起只读任务。
- 观察返回值和创建的 Session JSONL 日志，不修改正式项目资料。

下面只是官方 SDK 调用方式的**起步示意**，不是已执行测试，也不能替代下面的隔离要求：

```python
from pathlib import Path
from deepseek_harness import DeepSeekHarness

workspace = Path("/absolute/path/to/disposable-workspace").resolve()
home = Path("/absolute/path/to/example-dsh-home").resolve()

with DeepSeekHarness(
    provider="deepseek-official",
    model="deepseek-v4-flash",  # 官方文档示例，需核对实际可用模型
    max_tokens=49_152,
    cwd=str(workspace),
    dsh_home=str(home),
    profile="sdk-minimal",
) as harness:
    result = harness.run(
        "请解释这个演示目录的用途，不要修改任何文件。",
        session_id="lesson-00",
    )
    print(result.final_response)
```

**安全前提（必须先满足）**

官方 `sdk-minimal` 固定使用 `danger-full-access`，其持久 Shell 可能访问运行时可见的全部路径。**单独指定 `cwd` 并不能形成沙箱**。首次实验应在专用容器或隔离虚拟机内运行，只挂载可丢弃的样本，限制可用凭据和网络能力，不提供敏感资料。该 profile 默认还可能随模型请求上传部分 Session 日志；必须了解日志配置与数据边界后再连接实际岗位数据。

**回到原理**

- Python `DeepSeekHarness` 是调用入口，实际执行的 `dsh` 进程是什么？
- 模型、Agent、Runtime、Profile、SDK 分别承担什么职责？
- `run()` 返回最终文本，是否就能说明任务已经真正完成？

**第一轮观察与验收**

记录 Python/SDK 版本、Profile、模型路由、是否出现 Session 日志及实际返回结果。能够在隔离环境复现一次完整调用，才算阶段 0 完成。

**关联原理**：[00 · Agent 与 Runtime](./README.md)；[01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)（阶段 0 先阅读，阶段 1—2 再用真实轨迹验证）。

### 阶段 1｜从“一次回答”升级为“交付一个工作结果”

**先要完成的事**

不连接 job-rag，提供一小批固定的演示 JD，让 Agent 根据明确任务生成 `report.md`，并要求报告引用对应的演示职位 ID。

**教学任务**

- 先保存一份直接调用模型生成答案的 Baseline。
- 再要求 Agent 检查样本文件、读取内容并生成报告。
- 区分“模型在回复中声称生成了文件”和“工作目录中真实存在且内容正确的文件”。
- 从 Session 日志定位模型输出、工具调用和最终响应之间的关系。

**回到原理**

为什么一次文本生成与完成有副作用的工作任务不同？什么叫一次模型调用、一次工具调用、一次 Agent Turn？Agent Loop 的继续条件和停止条件分别是谁决定的？

**最小对照**

同一份任务分别采用“仅给模型粘贴全部内容”与“让 Agent 根据样本文件实际读取”。记录是否读取了文件、报告是否存在、引用是否正确，而不是只评价文案是否流畅。

**验收**

生成的文件真实存在；能指出至少一条输出结论来自哪条 JD；能够描述至少一轮模型决策与执行过程。

**关联原理**：[00 · Agent 与 Runtime](./README.md)；[01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)；08 · 任务验证与结束条件。观察时应区分模型请求、Step、Turn、SDK RunResult 及业务验收。

### 阶段 2｜通过工具读取岗位数据

**先要完成的事**

让 Agent 使用受控的只读工具查询结构化岗位数据，替代在 Prompt 中粘贴完整数据库。

**教学任务**

- 从最简单的“读取一个固定的演示职位文件”开始。
- 定义并验证稳定工具行为：输入参数、返回结构、错误代码、权限边界。
- 逐步支持按职位 ID 读取全文、关键词搜索、结果去重以及分页。
- 用样本数据验证：查不到记录、参数错误、重复职位时，工具分别如何返回。

**回到原理**

- Tool Calling 中，模型只是**提出调用意图**，实际是谁在执行？
- 工具 Schema、权限校验、执行适配器与模型上下文之间是什么关系？
- 调用失败应由模型选择重试，还是由执行层按规则重试？
- 如果命令行 Shell 能直接操作 CSV，为什么后面还需要定义结构化工具？

**关键实现边界**

`sdk-minimal` 默认提供持久 Shell 等工具，**并不自动拥有我们的岗位检索工具、MCP Server 或 ADK 风格的 `FunctionTool`**。初始实验可借助隔离环境中的本地脚本完成只读访问；下一阶段再研究 Harness 的插件与工具注册机制。不得把“计划使用的 MCP 能力”写成“已开箱支持”。

**验收**

每一项统计结果能回查到具体职位；工具错误与“没有岗位匹配”能够区分；对比手工读取和工具调用的执行轨迹。

**关联原理**：[01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)；[03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)。先理解工具定义、模型请求和实际执行的边界，再形成只读岗位数据接口。

### 阶段 3｜增加 Planner、Checker 与结果验证

**先要完成的事**

借鉴 Google ADK 的“生成—检查—必要时修改”，为同一个 JD 研究任务添加可观察的规划和校验环节。

**教学任务**

- 先在**应用层**明确规划、检索、汇总、校验四个阶段，不急于拆成四个 Agent。
- Planner 给出统计计划和需要检索的信息；Researcher 调用工具；Writer 生成报告；Checker 检查结构、计数分母、职位证据。
- 为校验失败设置有限重试次数、错误反馈和最终失败出口。
- 只在需要独立执行环境、并行或不同权限时，才把某个阶段升级为独立子 Agent。

**回到原理**

- Google ADK `LoopAgent` 的固定循环与模型动态 Agent Loop 有什么区别？
- 工作流的下一步由程序决定，还是由模型决定？
- 验证失败是“重新生成全文”，还是“定位错误后局部修改”？不同选择有何成本？
- 多 Agent 相比单 Agent 真正增加了什么，又增加了哪些通信和上下文负担？

**DeepSeek Harness 特别说明**

不能预先假定 DeepSeek Harness 提供和 Google ADK `SequentialAgent`、`LoopAgent` 一一对应的 Python 类。第一版先用 Python 控制器和 SDK 组合步骤；以后根据官方 Workflow、插件与 Session API 的实际能力再实现更原生的编排。

**对照与验收**

在一批故意包含重复职位、缺失字段、可疑技术归类的样本上，比较无 Checker 和有 Checker 的结果。记录修正是否真的减少可复核错误、是否增加不必要的循环与调用成本。

**关联原理**：[02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md)；08 · 任务验证与结束条件。先解释固定阶段与模型自主决策如何分工，再用同一批 JD 验证 Checker、Planning 或 Multi-Agent 是否值得增加。

### 阶段 4｜把岗位能力接到 MCP

**先要完成的事**

把此前的岗位读取与检索能力封装为独立接口，让 Agent 通过规范化的工具接入方式使用它。

**教学任务**

- 在隔离环境中实现或复用一个**只读** job-rag MCP Server：检索职位、读取 JD、读取岗位证据。
- 验证工具枚举、参数约束、调用结果与失败响应。
- 根据 DeepSeek Harness **当前版本的插件/工具接入文档**，选择实际可用的 MCP 接入方式，并记录所使用的版本和配置。
- 保留“本地脚本直连”作为基线，比较切换后变动的部分。

**回到原理**

MCP 与 REST API 分别解决哪一层的问题？MCP Client、Server、工具描述及实际业务 API 的职责如何划分？工具发现与模型决定调用哪个工具，为什么是两件事？认证、审批和实际数据权限为什么不能只依靠 Schema？

**验收**

相同查询能通过受控本地接口与 MCP 路径拿到可核对的相同职位数据，并正确处理工具不可用、超时与不合法参数。暂不实现写回职位库。

**关联原理**：[03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)；07 · 权限、Sandbox 与人工审批。重点比较本地工具与 MCP Server 两条路径的工具发现、调用返回及授权边界。

### 阶段 5｜研究 Context Engineering

**先要完成的事**

让 Agent 处理规模增长的 JD 集合，观察历史和工具输出变长之后的实际表现。

**教学任务**

- 使用可重复的固定样本逐步扩大检索与阅读规模。
- 比较“一次输入完整候选集”和“只把当前需要的 JD 及证据送给模型”。
- 观察何时发生自动压缩；必要时建立外部任务笔记与已检查职位清单。
- 分别实验 Select（选择当前事实）、Compress（压缩旧历史）、Isolate（隔离不同任务或子 Agent 的上下文）。

**回到原理**

Context 与完整 Session 日志有什么区别？什么信息应该保留原文，什么可以压缩？为什么大上下文窗口不代表必须塞入所有数据？压缩之后哪些否定、限定、统计口径和证据 ID 绝不能丢？

**产品差异提醒**

DeepSeek Harness `sdk-minimal` 的官方说明包括自动上下文压缩，但它的具体触发、摘要位置与可观测事件需以当前版本及实际日志验证，不推断其内部策略必然与其他 Coding Agent 一致。

**验收**

在相同任务范围上比较 Token 开销、工具调用次数、证据覆盖、遗漏率与最终统计一致性。能指出至少一种具体的“上下文过多或不当压缩”失败现象及对应调整。

**关联原理**：[04 · Context Engineering](./04-context-engineering.md)；原有 [上下文管理文章](./01-harness-context-management.md) 用作网关排障扩展案例。重点区分模型可见历史、Session 事件与可回查的原始业务证据。

### 阶段 6｜区分 State、Session 与恢复机制

**先要完成的事**

进行跨轮连续研究，并在某个可控步骤后人为中断，验证究竟能恢复什么。

**教学任务**

- 为任务维护显式业务 State，例如筛选条件、职位集合、已完成分析、待核查事项、输出位置。
- 使用不同 Session ID 运行不同研究任务，观察历史隔离。
- 研究 SDK 的 `resume_session(saved_session_id)`：复用相同 Home、Workspace、Session ID 恢复会话历史。
- 在应用层额外设计一个独立的任务进度检查点，以支持从阶段边界继续工作。

**回到原理**

Session 历史、业务 State、Checkpoint、外部数据产物之间的关系是什么？持久化聊天历史，为什么不等于恢复尚未完成的工作流？如果此前成功写入报告却没来得及保存成功状态，重启后该怎样判断？

**必须明确的产品边界**

DeepSeek Harness Python SDK 官方说明，`resume_session` 恢复持久化历史和会话数据，**不会恢复 Shell、浏览器等外部进程**。它不能直接视作任意业务工作流的 Checkpoint。

**验收**

能够示范“新 Session”“继续已有 Session”和“按业务检查点继续任务”的区别；中断后不会因错误恢复机制重复计算或写入。

**关联原理**：[05 · State、Session、Checkpoint](./05-state-session-checkpoint.md)。结合 `resume_session`、Session 持久性屏障与应用层业务 Checkpoint，区分会话恢复和业务安全续跑。

### 阶段 7｜加入执行控制、安全边界与故障恢复

**先要完成的事**

故意注入工具超时、错误数据、不可达服务、重复提交请求与危险指令，观察 Agent 和执行层的行为。

**教学任务**

- 对只读工具设置超时、重试上限和明确错误返回。
- 对未来的写文件动作设置幂等标识或先检查目标产物状态。
- 将写入、删除、发送和其他高风险操作置于独立权限与人工审批之下。
- 验证用户输入、JD 原文与工具响应不能自行提升为系统指令。
- 对所有试验使用权限收紧的真实隔离环境；记录可访问文件和出站网络范围。

**回到原理**

模型的决策能力与执行权限为何应分离？Sandbox 与工具级授权有什么区别？哪些错误可以重试，哪些重试会造成副作用？Retry、Resume 与 Compensation 分别解决什么问题？

**验收**

错误能够被识别、记录并按规则停止或恢复；危险操作不能因为模型建议就直接执行；实验能够指出边界由哪一层强制保障，而不是只靠提示词承诺。

**关联原理**：可靠性、安全、人工审批。

### 阶段 8｜建立端到端评测，而不只评估最后一段回答

**先要完成的事**

使用 job-rag 真实业务问题构建可复核的小型评测集，并对完整执行轨迹和最终报告分别评价。

**教学任务**

- 从现有完整 JD 中固定一个评测快照，标注岗位匹配、技术术语、必备/加分以及原文证据。
- 首先进行人工可核查的少量案例，再扩大评测；切勿直接假设所有历史采集数据都属于正确标签。
- 记录检索候选、去重、模型判断、工具执行、检查反馈和报告产物。
- 比较至少两种可解释的实现方案，例如无/有 Checker、全量 Context/按需选择、关键词/混合检索。

**评测指标按问题分层**

| 层次 | 核心检查 |
| --- | --- |
| 数据层 | 岗位是否漏掉、重复、取错版本或字段 |
| 工具层 | 调用是否成功，结果是否正确、完整且受控 |
| 推理层 | 是否正确理解 RAG 职责、必备技术和加分项 |
| 证据层 | 报告中的职位 ID、引文和数字能否回查 |
| 任务层 | 是否交付满足口径的报告，失败时是否如实说明 |
| 运行层 | 轨迹、延迟、Token、重试次数、成本、恢复行为 |

**回到原理**

为什么“回答正确率”不能直接代表“任务成功率”？如何判断错误来自检索、工具、模型判断、上下文、Workflow 还是评测标准本身？为什么没有固定数据范围与清晰分母的频率比较可能失真？

**验收**

至少能针对一个失败案例给出可追踪的根因和一项有依据的改进；报告不能只给出“模型感觉更好”。样本数量、标签质量和结论适用范围必须如实记录。

**关联原理**：Agent 端到端评测与持续优化。

### 阶段 9｜将本地应用变成可运行的服务

**先要完成的事**

在前面单机任务已经稳定的前提下，为 JD Research Agent 提供可访问的应用入口，并验证多会话隔离。

**教学任务**

- 给 Python 应用增加受控服务入口，例如 HTTP 请求提交任务、查询状态、获取报告。
- 区分请求/响应生命周期与可能跨越较长时间的 Agent 任务生命周期。
- 处理任务 ID、请求鉴权、状态保存、取消、超时与资源限额。
- 设计服务部署、配置和日志采集；优先内部测试环境，不将高权限 Harness Web UI 或 SDK 执行端口无认证暴露在公网。
- 验证两个用户或两个任务不会混用 Session、工作目录、缓存或职位数据权限。

**回到原理**

本地 SDK 运行进程与长期在线服务是什么关系？Session 并发、任务队列、模型调用并发和业务请求并发为何不同？哪些能力归 Runtime，哪些归部署平台？

**验收**

能够提交任务、查询进度、获取报告并确认访问控制；重启和异常停止后的行为可说明；不能把“HTTP 返回 200”当作“研究任务成功”。

**关联原理**：部署与服务化、AgentOps。

### 阶段 10｜同一套原理迁移到其他 Agent 和 Harness

**先要完成的事**

不重写整套基础设施，增加第二个 Agent 案例或选择另一个 SDK 实现一项同类任务。

候选应用可以是制度文件审查、企业知识库问答与报告生成、内部办公文档处理；先使用公开或模拟数据，待权限及数据边界明确后再考虑企业数据。

**教学任务**

- 保留通用运行机制文章，复用必要的工具接口和评测方法。
- 给新应用独立的目录、数据快照、实验记录与结果验证规则。
- 如果改用 AgentScope 等其他 SDK，比较相同任务的 Workflow、工具注册、上下文、Session、错误处理，而不是比较不同提示词导致的最终文案差异。

**回到原理**

哪些判断属于模型能力，哪些属于 Harness 架构？哪些知识可以迁移，哪些必须按具体 SDK 的版本重新确认？引入新 Agent 是否真的需要新的运行机制？

**验收**

能够指出跨框架不变的原理与当前版本特有的实现差异，并解释为什么为某个任务选用某种架构。

---

## 五、课程的实际推进顺序与里程碑

不要按“先把所有 11 个原理主题写完，再开始项目”的模式推进。每跨过一个可观察的工程边界，就回到对应原理：

| 里程碑 | 完成阶段 | 应当拿到的实物 | 能够解释的机制 |
| --- | --- | --- | --- |
| M1 · 第一个可运行 Agent | 0—1 | 隔离环境中的 SDK 调用、样本报告、Session 记录 | 模型调用与任务完成；Runtime 和 Agent Loop |
| M2 · 真正使用工具 | 2—4 | 岗位查询工具、检查反馈、可追溯研究报告、MCP 接入记录 | Tool Calling、Workflow、动态决策、MCP |
| M3 · 长任务仍可控制 | 5—7 | 上下文实验、Session/State 对照、中断与故障测试 | Context、持久化、Checkpoint、权限与恢复 |
| M4 · 结果能被证明 | 8 | 固定评测样本、轨迹及错误分析报告 | 任务级评测、归因与优化 |
| M5 · 应用可以服务他人 | 9 | 有限权限的服务入口、运行日志与多会话测试 | Agent Runtime 与部署平台的职责 |
| M6 · 机制可迁移 | 10 | 第二案例或第二框架的对照实验 | 通用原理与具体实现的边界 |

章节不是打卡表：如果某个阶段的问题已经能依据官方机制讲清，就不强迫增加无意义的实验；如果真实运行暴露关键矛盾，则允许返回前一阶段补齐知识。

---

## 六、每个实践阶段如何留下可复用的证据？

每阶段至少明确五项信息：

1. **任务与版本**：输入、固定样本、模型、SDK、Profile 和代码版本（Phase 0 记录 HarnessLab 提交，JD 业务记录 job-agent 提交）。
2. **实际动作**：工具调用、执行命令、脚本入口及对应实验所在仓库的提交。
3. **观察到的事实**：模型响应、工具结果、文件、Session 日志与真实失败事件。
4. **机制解释**：用通用原理说明因果关系，必要时定位 DeepSeek Harness 对应源码。
5. **效果与边界**：实验说明了什么，尚有哪些未验证的情况。

**Phase 0 的代码和受控实验材料留在 [HarnessLab 教学实验](./labs/sdk-minimal-phase0/README.md)**；**JD 业务实验与可复核证据留在 [job-agent](https://github.com/leecolin2023/job-agent)**，通用机制解释仍放在 HarnessLab 原理文章。不要未经审查向公开仓库提交原始 Session 日志、凭据或内部数据。离线测试通过不能替代真实模型和工具运行验证。

当前阶段 0 的 SDK、Docker、脚本、Session 分析器、测试与 CI 已统一放入 [HarnessLab 的 sdk-minimal-phase0](./labs/sdk-minimal-phase0/README.md)，逐行讲解在 [Phase 0 实验代码解读](./labs/sdk-minimal-phase0/01-code-walkthrough.md)。这些不是 job-agent 的业务功能。

## 七、读源码时应从哪一层进入？

不要一开始阅读 DeepSeek Harness 全部仓库。先从一个实验中实际出现的行为，反向追查代码。

可优先沿官方架构文档标出的模块进行：

| 实际观察 | 优先查阅位置 | 真正要理解的内容 |
| --- | --- | --- |
| 一次 `run()` 如何产生多轮操作 | `core/agent-loop`、`core/agent` | Turn、模型请求、工具调用与终止如何串起来 |
| 工具怎样被发现和执行 | `core/tools` | Registry、Schema、工具执行与权限检查 |
| 模型每轮究竟看到了什么 | `core/system-prompt` | 系统提示词片段、工具 Schema、请求上下文 |
| 旧会话如何被读取与恢复 | `core/session` | 事件日志、Session 重放及状态边界 |
| 模型供应商或 API 更换 | `llm/llm` | 消息结构、流式协议和模型适配器 |
| 一个能力怎样加入或替换 | Cordis Plugin、Profile、Bundle | 依赖装配、生命周期和插件扩展点 |

这些是当前官方文档展示的架构入口，不意味着每个具体文件名或事件都不会变化。DeepSeek Harness 正处于 Developer Preview，重要实验需要记录所用 commit 与版本。

阅读源码的固定顺序是：

**先看真实 Trace → 定位对应模块 → 搞清输入、输出与状态变化 → 修改配置或做小实验 → 再写通用机制。**

避免只看目录名称就推断实现细节，也避免为了“理解得深入”而从头重写已经成熟的组件。

---

## 八、为什么不把本项目直接做成一个“万能 Agent 平台”？

本路线的目标是建立技术理解和可验证的工作能力，而不是一开始搭建所有 Agent 都必须接入的统一平台。

早期故意保留简单设计：

- 单个任务先使用单 Agent，明确需要独立职责时才拆分。
- 工具优先只读，稳定后再逐步引入有副作用的操作。
- 先在本地验证行为，再接入 MCP、队列和部署环境。
- 先用固定数据和可检查的业务规则，再评估真实数据上的泛化。
- 先区分执行引擎与服务平台，再考虑共享的鉴权、审计和运营能力。

这样每次增加复杂度，都能清楚回答：**它解决了上一版的哪个实际问题，代价是什么，证据在哪里。**

---

## 当前阶段 0 的实践入口

先阅读 [SDK Phase 0 最小实验与核心代码](./labs/sdk-minimal-phase0/01-code-walkthrough.md)，理解工程现有的部署脚本、Python SDK 调用、Session 分析器以及它们与 DSH Runtime 的关系。本文解读的是实际代码，不把未执行的模型调用写成实测。

然后进入 [HarnessLab/agent-runtime/labs/sdk-minimal-phase0](./labs/sdk-minimal-phase0/README.md)，运行 `bash scripts/run-docker.sh test` 或在满足隔离条件后执行 `build`、`run`、`inspect`。历史上在 job-agent 的离线 CI 曾通过，但迁移后的实际运行效果仍应以新的工作流和可核查的 Session 事件为准；尚无真实模型轨迹时，不得把阶段 0 标记为完成。

---

## 九、建议从哪里开始？

**第一轮只做 M1（阶段 0 与阶段 1）。** 此时甚至不需要 MCP，也不需要多 Agent。

第一轮计划：

1. 建立隔离实验环境，记录安装与安全配置。
2. 使用 `DeepSeekHarness` 运行官方最小例子。
3. 准备 5～10 条脱敏完整 JD 演示数据。
4. 让 Agent 生成一个真实存在的研究报告文件。
5. 阅读该 Session 的日志，画出“用户请求 → 模型 → 工具 → 输出”的实际执行链。
6. 写出第一份观察记录，并据此完善 Agent Loop 原理文章。

**通过标准**不是“模型说任务完成了”，而是可以同时出示真实报告文件、对应的样本出处、可复核的执行记录，以及对模型调用与工具执行之间关系的准确解释。

随后进入 M2：工具查询 → Agent 决策 → 规划与检查 → MCP。只有真实观察到的困难，才推动下一项工程能力的引入。

---

## 十、资料与版本依据

- [DeepSeek Harness 官方仓库](https://github.com/deepseek-ai/deepseek-harness)（Developer Preview，兼容性可能破坏）
- [DeepSeek Harness Python SDK 入门](https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk)（`sdk-minimal`、隔离路径、工具与权限边界）
- [DeepSeek Harness Python SDK 参考](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)（Session 恢复与 SDK 行为）
- [DeepSeek Harness 架构参考](https://deepseek-harness.github.io/deepseek-harness/reference/)（Cordis、Agent Loop、Tools、Session、Prompt、LLM）
- [Google Cloud Tech：Modern AI Agents 原教程中文整理索引](../materials/agent-runtime/20261030__Modern%20AI%20Agents%20-%20From%20Theory%20to%20Production/README.md)（用于借鉴应用教学顺序）
- [SenseWright System Learning V0.7.0](https://github.com/leecolin2023/SenseWright/blob/main/skills/system-learning-v0.7.0/SKILL.md)

> 维护约定：本路线描述“学什么、为什么、怎样验收”，不替代每个阶段实际代码、运行日志与评测报告。SDK 最小实验代码变更应更新 [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 及其源码解读；岗位研究业务变更应更新 [job-agent](https://github.com/leecolin2023/job-agent)；通用机制的变化则单独更新 HarnessLab 原理文章。
