# 01 · Agent Loop 的运行机制：一项任务怎样从启动走到结束？

> **学习定位**：本篇承接 [00 · Agent 与 Runtime](./README.md)。00 已经解释“模型决策 → 工具执行 → 反馈 → 继续或结束”；本篇不再重复定义，而是深入：**Runtime 实际怎样构造请求、处理模型的不同响应、交接工具结果，并控制任务结束？**
>
> **贯穿工程**：[job-agent](https://github.com/leecolin2023/job-agent)，采用 DeepSeek Harness Python SDK；业务方向是后续的 JD Research Agent。本文先用当前已实现的最小任务（在隔离环境读取工作目录）观察循环，再说明怎样扩展到 JD 研究。
>
> **证据边界**：下文区分 **源码确认**、**机制示例**、**尚待真实运行验证**。截至本次编写，从公开仓库能够核查应用代码与 DeepSeek Harness Runtime 源码，但**尚没有可公开核验的真实模型调用及完整 Session 轨迹**。示例事件序列不能当作已完成实验。

## 一、一次 `harness.run()` 究竟包含多少次“运行”？

先看 job-agent 的应用入口。它给 SDK 传入一个任务，得到最终结果：

~~~python
with DeepSeekHarness(
    provider="deepseek-official",
    model=args.model,
    cwd=str(workspace),
    dsh_home=str(home),
    profile="sdk-minimal",
    patches=(str(patch),),
    max_tokens=4096,
) as harness:
    result = harness.run(args.prompt, session_id=args.session_id)
~~~

这段代码里只写了一次 `run()`，但它没有告诉我们内部实际调用了几次模型、执行了几个工具。

为避免把不同层次混在一起，先区分几个概念。

| 层次 | 它表示什么 | 是否必然一一对应？ |
| --- | --- | --- |
| **工作任务** | 用户要求完成的结果，例如生成一份带证据的岗位报告 | 可能跨多次调用和会话 |
| **SDK 的 `run()`** | 应用向 Harness 发起一次运行并等待返回 | 不等于单次模型请求 |
| **Session** | 关联一段持久化交互历史及运行事件的身份 | 不等于一次 `run()` |
| **Turn** | Runtime 处理一轮已接收输入的边界 | 一个 Turn 可以包含多个 Step |
| **Step** | Runtime 中一次内部执行步骤的边界 | 可能因请求重试包含多次模型尝试 |
| **模型请求** | 向模型服务发送的一次推理请求 | 不一定产生工具调用 |
| **工具调用** | 模型提出的某次工具操作及对应执行 | 一次模型响应可以包含多个调用 |

这个区别不是术语游戏。

例如，模型第一次请求执行 `pwd`，工具返回目录；第二次模型请求执行 `ls -la .`；工具返回文件列表；第三次模型给出最终回答。应用端仍可能只看到一次 `harness.run()`。

**一个 SDK 调用不等于一次模型推理；一个 Step 也不能机械等同于一次模型请求。**

### DeepSeek Harness 怎样组织 Turn 和 Step？

在本次核查的源码中，[ReactLoopAgent](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts) 的 `turn()` 先写入 `turn/start`，再通过内部循环创建 `step/start` 和 `step/end`，最后写入带结束原因的 `turn/end`。

它还会根据是否存在下一步输入，判断是否需要开始新的 Turn。

因此，理解运行轨迹时应先问：

1. 这是哪个 Session？
2. 发生在第几个 Turn？
3. 这是该 Turn 的第几个 Step？
4. 这一步实际发出了多少次模型请求、产生了哪些工具调用？
5. 这个 Turn 怎样结束？之后是否又出现新的 Turn？

这些问题比单纯统计“Agent 调用了多少次工具”更能解释运行过程。

---

## 二、模型第一次被调用之前，Runtime 需要准备什么？

### 1. 应用提供了什么？

以目前的 job-agent 为例，[src/run_phase0.py](https://github.com/leecolin2023/job-agent/blob/e96a30892d3c202df3f270f81324cb8e7ad23482/src/run_phase0.py) 主要提供：

- 用户任务或演示 Prompt；
- 模型、Profile 和请求参数；
- `workspace`、`dsh_home`、`session_id`；
- 执行环境和配置补丁。

它没有自己实现模型—工具循环，而是把工作交给 DeepSeek Harness。

当前默认演示任务要求在隔离目录执行 `pwd` 和 `ls -la .`，**尚未实现读取完整 JD、分析技术要求和生成业务报告**。

### 2. Runtime 在发送模型请求前准备什么？

对照 `ReactLoopAgent` 的 `preStep()`、`step()` 和 `buildRequest()` 可以看到几个关键环节：

1. **确定模型选择**：当前使用哪个 provider、model。
2. **解析可用工具**：为当前 Step 准备工具集及其说明。
3. **组织系统与运行上下文**：装配模型可见的指令及本轮新增信息。
4. **从 Session 推导消息历史**：形成即将发送给模型的消息列表。
5. **构造实际模型请求**：携带模型配置、消息和工具声明，再进入推理调用。

简化理解：

~~~text
应用：harness.run(prompt, session_id)
              ↓
Runtime：确定当前 Turn / Step
              ↓
解析当前允许使用的工具
              ↓
组织指令、历史和本轮输入
              ↓
构造模型请求
              ↓
模型服务执行推理
~~~

为什么要专门区分“准备请求”和“调用模型”？

因为模型不会自动知道本地有哪些可执行工具，也不会自动获得前一轮工具的实际结果。**它只能根据 Runtime 本次提供的消息和工具定义作出判断。**

这里暂时只解释数据如何进入模型请求；信息选择、压缩、隔离的具体策略留给 **04 · Context Engineering**。

### 3. 怎样证明模型实际上看到了什么？

不能仅凭最终回答倒推 Prompt 的完整内容。

如果要核查一次真实运行，至少需要区分：

- 应用传入的原始 Prompt；
- Runtime 装配的系统信息与工具说明；
- 实际形成的模型请求；
- 模型返回的响应。

**源码能证明存在这条装配路径；只有对应版本、配置与真实轨迹，才能证明某次运行究竟发送了哪些信息。**

---

## 三、模型返回以后，Runtime 根据什么选择执行分支？

这是 Agent Loop 的核心控制点。

模型每次推理返回后，Runtime 并不是无条件继续下一轮，而是先检查本次响应与执行状态。

### 1. 模型返回了普通回答，没有工具调用

在本次核查的 DSH `step()` 源码中，Runtime 从 Assistant 消息中筛选类型为 `tool-call` 的内容块。

若没有工具调用，当前 Step 返回 `completed`。

这表示**当前模型—工具执行步骤不再需要追加工具操作**；之后是否还有新的输入、Turn 或业务验收，仍由更外层机制决定。

不能把“模型没有继续调用工具”直接理解为“工作成果正确”。

### 2. 模型返回了工具调用

如果 Assistant 消息包含工具调用内容块，Runtime 将它们传给工具执行体系。

代码中的关键分支可以简化为以下伪代码（并非逐字复制源码）：

~~~python
response = await model_request()
tool_calls = extract_tool_calls(response)

if not tool_calls:
    return "step_completed"

tool_result = await tool_executor.execute(tool_calls)

if tool_result.concluded:
    return "step_completed"

return "continue_to_next_step"
~~~

这里最重要的区别是：

**模型产生的是工具调用请求，实际工具执行发生在 Runtime 调用 Tool Executor 之后。**

另外，一次 Assistant 响应可能包含多个 `tool-call`。执行器可以按自身能力和配置组织工具批次；不能默认每次只调用一个工具，也不能默认所有调用必然并行。

### 3. 模型请求失败或被中断

正常回答和工具调用不是唯二的结果。

源码还存在模型流异常、请求错误处理、取消以及 `max-tokens` 等分支。

例如，在某些模型请求错误场景，DSH 会经过请求错误处理钩子判断是否重试；没有得到重试决定时，则进入错误路径。

这里要区分：

- **模型请求重试**：同一个内部 Step 中，可能重新发起模型请求。
- **工具执行失败后的补救**：可能由执行层处理，也可能将信息反馈后让模型决定新行动。
- **整个 Agent 被取消**：不能把它记成任务正常完成。

因此，理解运行次数时，仅凭 Step 数推算模型 API 请求次数可能产生误差。

### 4. 模型返回了正文，同时包含工具调用，怎么处理？

不要假设“响应里出现文字”就意味着任务结束。

在当前 DSH `step()` 中，是否进入工具路径取决于 Assistant 消息中是否存在 `tool-call` 内容块，而不只是是否包含文字。

这也是为什么**解析模型响应的结构**，比仅仅阅读模型生成的最终文本更重要。

---

## 四、工具执行之后，反馈怎样使下一次模型决策成为可能？

### 1. 模型发出调用请求，与工具真正执行有什么区别？

当前 job-agent 的演示任务想执行 `pwd`。

在抽象层面，至少存在三个不同事实：

~~~text
模型提出：调用 Bash 执行 pwd
           ↓
执行器实际运行：pwd
           ↓
工具返回：退出状态、标准输出或错误信息
~~~

第一个只是模型意图；第二个才是真实动作；第三个才是 Agent 可以继续利用的观察结果。

DSH 的 `sdk-minimal` Profile 使用 Runtime 的工具体系；job-agent 的 Python 包装层没有自行实现 Bash 执行器。

### 2. 工具结果怎样关联到原来的调用？

Runtime 必须让后续模型请求能够读到工具返回的信息，并能够知道它对应哪个行动。

在本次核查的 DSH 源码中，Assistant 响应写入 Session；工具执行体系处理调用和结果；后续模型请求通过 Session 派生可见消息。

源码中还存在 `ToolCallRecovery`：当某个 Step 异常退出时，尝试补记可恢复的待处理工具结果，避免工具调用与结果的记录失配。

因此，反馈至少承担两个职责：

- **提供新信息**：例如 `pwd` 实际返回哪个路径；
- **维持调用因果关系**：这段结果来自哪个已经发出的工具调用。

这并不意味着任何工具执行错误都会自动修复。Runtime 保留错误信息、模型选择替代行动和应用完成错误恢复，是不同层次的事情。

### 3. 下一轮模型怎样看到工具结果？

关键不是应用程序手工重新拼接上一轮的所有文字，而是由 Runtime 的会话与消息装配机制，把已经记录的工具结果纳入后续模型可见的信息。

抽象过程如下：

~~~text
第 1 次模型请求
    ↓
Assistant：请求工具 A
    ↓
Runtime 执行 A
    ↓
写入对应的工具结果
    ↓
构造后续模型请求
    ↓
Assistant：根据 A 的真实结果决定是否调用 B
~~~

如果工具 A 返回错误，下一轮模型只有在看到了对应错误信息，才有机会据此调整策略。

**反馈是否真实传入，与模型是否真的据此改变行动，是两个必须分别判断的问题。**

例如模型先调用 A、后调用 B，并不能自动证明它“根据 A 的结果重新规划”。要证明这一点，需要看 A 的返回内容是否对 B 的选择构成了实际影响。

---

## 五、Agent Loop 怎样继续、暂停或结束？如何从真实轨迹验证？

### 1. 结束一次 Step、一次 Turn、一次任务，有什么区别？

对照 DSH 的 `turn()` 和 `step()` 可以看到：

- 一个 **Step** 可以因为没有工具调用、工具批次要求结束或触发限制而退出。
- 一个 **Turn** 会记录自己的结束原因，例如完成、限制、阻塞、中止或错误。
- 一个 **Session** 可以积累多个 Turn，不会因为一次 Turn 结束就必然消失。
- 一个**业务任务**是否合格，还需要检查用户要求的真实产物和证据。

这些是不同层次的结束。

| 情况 | 对循环意味着什么 | 能否证明业务任务完成？ |
| --- | --- | --- |
| 模型没有再提出工具调用 | 当前 Step 可以结束 | 不能 |
| 工具执行成功 | 一个实际操作完成 | 不能 |
| Turn 以 `completed` 结束 | 当前运行边界正常完成 | 不能 |
| 触发 `max-tokens` | 达到输出限制，需按相应原因处理 | 不能 |
| 模型或工具报错 | 转入错误处理或终止 | 不能 |
| 用户取消 / 执行被阻塞 | 中止或暂停进一步行动 | 不能 |
| 最终文件存在且内容通过业务核查 | 有支持任务成功的独立证据 | 仍应按验收范围判断 |

当前 job-agent 的 [src/run_phase0.py](https://github.com/leecolin2023/job-agent/blob/e96a30892d3c202df3f270f81324cb8e7ad23482/src/run_phase0.py) 检查 `result.finish_reason` 是否属于 `None` 或 `completed`。即使脚本返回码为 0，这也**不证明**指定工具执行成功，更不证明后续 JD 统计业务结果正确。

### 2. 一次最小任务的轨迹应该怎样读？

先使用 job-agent 已有的最小 Prompt：

> 在隔离工作区执行 `pwd`，再执行 `ls -la .`，根据实际返回结果说明看到了什么。

下面是一条**教学用的预期逻辑轨迹，尚非真实 Session 记录**：

~~~text
SDK：run(prompt, session_id)
  └─ Turn 1 开始
      ├─ Step 1：准备请求 → 模型请求执行 pwd
      │           → Tool Executor 执行 pwd → 记录工具结果
      ├─ Step 2：根据已记录结果准备请求
      │           → 模型请求执行 ls -la .
      │           → Tool Executor 执行 → 记录工具结果
      ├─ Step 3：模型根据结果给出最终说明
      │           → 无进一步工具调用
      └─ Turn 1 结束
SDK：返回 RunResult
~~~

真实情况可能不同：模型可能一次请求提出多个工具调用，可能只调用一部分，可能因错误中止，也可能产生更多 Step。因此**不能先画好三步流程，再把日志强行解释成三步**。

### 3. 应该核查哪些 Session 证据？

DSH 源码中可以定位 `turn/start`、`step/start`、`assistant/message`、`step/end`、`turn/end`，以及在部分恢复路径记录的 `tool/result` 等事件。具体 Session 事件类型和数据结构应以实际运行版本为准。

建议按以下顺序阅读轨迹：

1. 找到同一 Session 的一次 Turn 边界；
2. 找到该 Turn 下各 Step 的开始和结束；
3. 在相应 Assistant 消息中识别工具调用内容块；
4. 找到执行器记录的实际工具结果，核对调用与结果的关系；
5. 确认结果如何进入后续模型判断；
6. 查清 Turn 的最终结束原因；
7. 另行检查最终产物，而不是只相信模型自述。

**注意当前工具的能力边界**：job-agent 的 `src/session_report.py` 只汇总 JSONL 事件类型与数量，不输出完整事件内容。它能说明“出现了哪些事件”，却不能单独证明“某个工具调用及其返回如何改变了后续行动”。要完成因果追踪，还需要在安全隔离环境中对本地原始事件做有权限、脱敏的定向检查。

### 4. 怎样完成第一轮真正的实验？

本篇对应学习路线的阶段 1、2，建议依次完成：

**第一步：运行现有最小实验。** 按 [job-agent README](https://github.com/leecolin2023/job-agent) 的指引，在隔离 Docker 环境内运行阶段 0。记录 SDK、Runtime、Profile、模型版本及 Session ID。当前 `sdk-minimal` 存在高权限 Shell 风险，**单独设置 `cwd` 不是沙箱**；不可挂载真实银行数据、敏感凭据或正式代码工作区。

**第二步：读取实际 Session。** 将模型响应、工具请求、工具结果、后续 Step、最终结束原因按时间顺序对齐。区分源码能证明的路径与这次真实发生的事件。

**第三步：构造一个可控变化。** 在固定的脱敏样本中分别让工具“正常返回内容”和“返回找不到记录”，观察后续行动是否真的发生变化。只有对照结果支持时，才能声称 Agent 对反馈作出了调整。

**第四步：进入 JD 报告任务。** 在有限的演示 JD 上读取文件并生成 `report.md`，独立核对文件真实存在、职位 ID 可回查。这里的验收是业务证据，不是 Loop 事件本身。

**第五步：对照源码定位原因。** 如果轨迹与预期不符，先判断是应用 Prompt/配置、Runtime 调度、工具执行，还是结果验收出了问题，再决定下一步研究哪一层。

截至撰写本篇，公开仓库里的代码与文档能够支撑上述**研究设计**，但不代表这些运行实验已执行或已经得到预期结论。

---

## 六、学完 Agent Loop，应该真正理解什么？

00 已经告诉我们：模型、工具和反馈可以形成持续执行的循环。

01 进一步回答的是：

1. **任务与模型请求不是一回事。** 一次 SDK 运行可能涉及多个 Turn、Step、模型请求和工具调用。
2. **模型响应决定进入哪条执行分支。** Runtime 根据工具调用、完成信号、错误和限制选择后续处理路径。
3. **工具请求不等于工具执行。** 实际动作由执行器完成，结果必须被记录并提供给后续决策。
4. **循环结束不等于业务完成。** Step、Turn、Session 和最终业务验收具有不同边界。
5. **源码路径与真实运行是两种证据。** 源码用于解释机制，Session 轨迹用于确认某次执行是否真的经过对应分支。

所以，本篇的价值不是再画一次 Agent Loop，而是让我们能回答：

> **给定一次 Agent 运行记录，我能否指出每次模型调用为何发生、工具实际做了什么、反馈如何影响后续步骤，以及 Runtime 为什么在这里结束？**

如果还做不到，就应该继续沿源码和实际 Session 回查，而不是追加更多抽象概念。

## 与后续专题的边界

- **02 · Workflow、Planning 与 Multi-Agent**：研究如何组织多个固定或动态步骤，以及何时需要显式计划或多 Agent。
- **03 · Tool Calling 与 MCP**：研究工具 Schema、协议、注册和执行适配，而不是重复基本分支。
- **04 · Context Engineering**：研究每次模型请求具体应保留、压缩和隔离哪些信息。
- **05 · State、Session、Checkpoint**：研究状态怎样持久化、恢复及与执行历史关联。
- **06 · 执行控制与故障恢复**：深入超时、幂等、取消、重试与补偿。
- **08 · 任务验证与结束条件**：研究可核查的任务成功标准和反馈驱动的修正。

## 资料与源码入口

- [00 · Agent 与 Runtime](./README.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [HarnessLab：job-agent 工程架构与核心代码解读](./job-agent/01-project-architecture-and-code.md)
- [job-agent：Python SDK 最小运行入口（固定提交）](https://github.com/leecolin2023/job-agent/blob/e96a30892d3c202df3f270f81324cb8e7ad23482/src/run_phase0.py)
- [job-agent：Session 事件分类脚本（固定提交）](https://github.com/leecolin2023/job-agent/blob/e96a30892d3c202df3f270f81324cb8e7ad23482/src/session_report.py)
- [DeepSeek Harness：ReactLoopAgent 源码（固定提交）](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts)
- [DeepSeek Harness 官方 Python SDK 入门](https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk)
