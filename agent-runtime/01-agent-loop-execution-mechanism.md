# 01 · Agent Loop 的运行机制：一句任务如何变成连续行动？

> **学习目标**：理解一次 `harness.run()` 如何让模型与工具多次交互，直到本轮执行结束。
>
> **实践对象**：[HarnessLab · SDK Minimal Phase 0](./labs/sdk-minimal-phase0/README.md)。本文讲 Agent Loop 的通用机制，并用该实验和 DeepSeek Harness 源码解释每个关键环节；具体 Python、Docker、配置与测试的逐行分析见 [Phase 0 代码解读](./labs/sdk-minimal-phase0/01-code-walkthrough.md)。
>
> **证据范围**：项目中已存在调用入口、隔离运行脚本和 Session 日志统计代码；目前公开仓库未提供可核验的真实模型—工具完整执行轨迹。下文出现的目录路径、工具返回值及事件顺序如标注为“示例”，只用于解释原理，不代表实验实测结果。

## 一、只发送一句任务，Agent 怎样开始工作？

假设我们想知道一个隔离工作目录里有什么文件。与其让模型猜测，不如直接交给 Agent 一项任务：

> 请使用 Bash 执行 `pwd` 和 `ls -la .`，根据命令的实际输出说明当前目录及文件。不能执行时请如实说明。

这是普通的自然语言指令。它描述要做什么、如何获取证据，却没有要求我们在应用中手写调用 Bash 的业务流程。

### 1. 这句话如何交给 Harness？

在 [Phase 0 的 Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py) 中，任务由 `args.prompt` 传入：

~~~python
with DeepSeekHarness(
    provider="deepseek-official",
    model=args.model,
    max_tokens=4096,
    cwd=str(workspace),
    dsh_home=str(home),
    profile="sdk-minimal",
    patches=(str(patch),),
) as harness:
    result = harness.run(args.prompt, session_id=args.session_id)
~~~

代码的意思并不复杂：

- `DeepSeekHarness(...)` 配置运行环境：使用哪个模型、哪个 Profile、哪个工作目录和 Session 存储目录。
- `harness.run(args.prompt, ...)` 把一句任务描述交给 Runtime，等待这次运行返回。
- `result.final_response` 是 SDK 最终交给应用的文字结果，不是工具实际执行过的证据。

当前实验的 `DEFAULT_PROMPT` 就要求模型先使用 Bash 执行 `pwd`，再执行 `ls -la .`；还规定只查看当前目录、不要编造工具记录。

在 Linux 上，可以使用仓库现有的 [运行脚本](./labs/sdk-minimal-phase0/scripts/run-docker.sh) 启动这一实验。脚本会准备隔离工作区、启动 Docker 容器，再调用上述 Python 入口。具体操作条件参见 [实验 README](./labs/sdk-minimal-phase0/README.md)。

### 2. 为什么 `run()` 不等于一次模型请求？

假设模型先要求执行 `pwd`。如果 Runtime 在这个工具执行完毕后就结束，任务只完成了一半：文件列表还没有读取，也没有生成基于结果的说明。

要完成这项任务，程序必须能够在工具返回后再次询问模型，直到模型不再需要工具，或者触发执行终止条件。

例如，一条**可能的**运行轨迹是：

~~~text
用户任务
   ↓
模型请求执行 pwd
   ↓
Bash 返回当前路径
   ↓
模型请求执行 ls -la .
   ↓
Bash 返回文件列表
   ↓
模型根据结果生成说明
   ↓
本轮执行结束
~~~

真实执行未必恰好是三个模型请求：模型可能一次提出多个工具调用，也可能执行失败或提前停止。这里要研究的关键不是调用了几次，而是：

**第一次模型响应之后，究竟是什么机制让执行能够继续？**

答案要从模型在第一次请求中能够使用哪些工具说起。

## 二、模型为什么知道自己能使用 Bash？

如果只有一个普通文本生成接口，模型可以回答“我准备执行 `pwd`”，但这不会让操作系统真的运行命令。

想让模型提出可执行的行动，Runtime 必须为它提供工具说明，同时保留与这些说明相对应的实际工具实现。

### 1. 当前实验从哪里获得 `bash` 工具？

留意前面初始化代码中的 `profile="sdk-minimal"`。

这里没有单独定义 Bash 工具，是因为 DeepSeek Harness 的 `sdk-minimal` Profile 已经装配了相应组件。

从 [官方 Profile 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) 可以找到几项关键插件：

~~~yaml
# 以下是配置中的相关条目摘录，并非可单独运行的完整 Profile
- id: tools
  name: '@deepseek-ai/dsh-tools'

- id: tool-executor-native
  name: '@deepseek-ai/dsh-tool-executor-native'

- id: terminal-bash
  name: '@deepseek-ai/dsh-terminal-bash'

- id: persistent-bash
  name: '@deepseek-ai/dsh-tool-bash-persistent'

- id: agent-loop
  name: '@deepseek-ai/dsh-agent-loop'
~~~

它们之间的关系是：

- **Bash 工具插件**注册一个名为 `bash` 的工具，声明参数及执行逻辑。
- **工具注册表**管理已注册的工具，确定当前 Agent 可以看到哪些工具。
- **原生执行器**接收模型的调用请求，找到对应工具并调度执行。
- **终端后端**负责真正运行 Bash 命令。
- **Agent Loop**在模型响应与工具执行之间推进循环。

在当前 Profile 中，Linux/macOS 使用持久 Bash，Windows 使用 PowerShell。我们使用 Linux 容器作为实验环境，因此后面讨论的是 `bash`。

### 2. 注册了工具，模型就能直接调用吗？

还需要让模型知道工具的名称、用途和输入格式。

以 `bash` 为例，面向模型的说明至少要表达：

~~~text
工具名称：bash
用途：运行 Bash 命令
输入参数：command（要执行的命令文本）
~~~

这里展示的是**概念化的工具说明**，不是 SDK 的完整 JSON Schema。

在 DeepSeek Harness 中，工具插件把定义注册到 `dsh-tools`，Runtime 再解析本轮可用的工具集合，并将获准使用的工具 Schema 放进模型请求。

于是形成一条完整关系：

~~~text
Python 选择 sdk-minimal
         ↓
Profile 加载 Bash 工具插件
         ↓
插件注册工具的名称、参数和执行实现
         ↓
Runtime 解析本轮可用工具
         ↓
模型请求包含 bash 的工具说明
         ↓
模型可以提出 bash 调用请求
~~~

**工具的注册，解决“系统能做什么”；工具 Schema 进入模型请求，解决“模型知道可以请求什么”。**

这两件事都没有赋予模型直接操作操作系统的权限。真实动作仍要由执行器实施，并受到运行环境的权限约束。

### 3. 如果需要读取 JD，工具也这样提供吗？

原理相同。未来的岗位研究 Agent 可以增加 `read_job(job_id)` 等业务工具，通过注册插件或 MCP 接入，让模型按受限接口读取数据。

但 **Phase 0 没有实现 `read_job`，也没有接入 JD 检索 MCP Server**。它只用现成的 Shell 工具帮助理解最小运行过程。

工具的自定义实现、Schema 设计、注册及 MCP 接入细节属于后续 **03 · Tool Calling 与 MCP**。这里需要掌握的是：**模型的工具请求有真实的、事先装配的执行能力与之对应。**

## 三、模型提出“执行 `pwd`”后，谁真正运行了命令？

模型收到了任务和可用工具说明，可能返回一段包含工具调用的 Assistant 响应。它表达的意思类似：

~~~text
工具：bash
参数：command = "pwd"
~~~

这仍然只是模型的请求。此时还没有运行 `pwd`。

Runtime 在收到模型响应后，需要判断：这是继续执行工具，还是当前推理已经可以结束？

在 [DeepSeek Harness 的 `ReactLoopAgent.step()` 源码](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts) 中，核心判断是筛选 Assistant 消息中的 `tool-call` 内容块：

~~~typescript
const toolCalls = message.content.filter(block => block.type === 'tool-call')
if (toolCalls.length === 0) return { kind: 'completed' }
~~~

如果存在工具调用，则由 Runtime 交给工具执行器：

~~~typescript
const result = await this.loopCtx.tools.execute({
  calls: toolCalls,
  signal,
  agent: this,
  log: { turn, step },
  maxParallelToolCalls,
  toolSet: decision.toolSet,
})
~~~

这两段展示了明确的责任分工：

**模型选择“要调用哪个工具、传什么参数”；Runtime 识别并分发请求；执行器调用具体工具，操作才真正发生。**

例如 Bash 执行成功后，可能产生：

~~~text
命令：pwd
结果：/sandbox/workspace
退出码：0
~~~

这里的结果只是示例。真实路径与返回内容必须从实际工具记录中核对。

但一次真实操作还不是完整的 Agent Loop。因为模型要根据路径和文件列表生成说明，**工具返回的内容必须能够影响后续模型判断。**

## 四、工具结果怎样回到模型，形成下一次判断？

假如 Bash 已经执行 `pwd`，但 Runtime 没有把结果保存和传递给下一轮模型，那么模型仍不知道实际路径，后续判断只能凭空猜测。

因此工具执行之后，还需要完成两件事：

1. **记录行动和结果**：哪个工具被调用、传了什么参数、获得了什么返回。
2. **组织后续模型请求**：让模型在下次推理时可以使用这些真实结果。

DeepSeek Harness 通过 Session 事件与消息历史管理这些信息。Runtime 后续构造模型请求时，会从相关历史派生模型可见消息。

因此，工具反馈的作用不只是提供一段新文本，而是将前一轮行动变成下一轮决策的依据：

~~~text
模型：调用 bash 执行 pwd
          ↓
工具：返回实际路径
          ↓
Runtime：记录工具调用及其结果
          ↓
Runtime：构造新的模型请求
          ↓
模型：基于已有信息决定下一步
~~~

如果执行失败，工具返回的错误也可能成为模型调整行动的依据。但是**记录了错误、让模型看到错误、模型真的纠正了行动**，是三个不同的事实；最后一个必须通过运行轨迹验证。

同样，模型未必一定在获得 `pwd` 结果后才请求 `ls`。因为本实验的指令已经要求执行两条命令，模型也可能在同一次响应中请求多个工具。它是否依赖前一个结果，需要对照真实消息，而不能仅由先后顺序推断。

至此，任务能够向前推进的原因已经清楚：**模型提出行动，Runtime 执行，结果进入后续请求，模型继续判断。**

## 五、Runtime 怎样决定继续，还是结束？

如果模型每次都要请求新工具，运行可能无法结束；如果每次工具完成后立即结束，又无法完成多步骤任务。

所以 Runtime 必须根据模型响应、工具执行结果和运行限制来控制循环。

最基本的决策结构可以表示为：

~~~text
准备本轮模型请求
       ↓
调用模型
       ↓
是否有工具调用？
  ├─ 是 → 执行工具 → 记录结果 → 按控制规则继续或结束
  └─ 否 → 当前执行步骤可以完成
~~~

在所核查的 DeepSeek Harness 源码中：

- Assistant 消息没有工具调用时，`step()` 返回 `completed`。
- 存在工具调用时，执行器处理工具批次；批次结果可能要求当前 Step 结束，也可能进入下一步。
- 模型请求出错、被取消或达到输出限制时，还有独立处理路径。

这说明 `while True` 只是方便理解的外层形式；实际 Runtime 还需要处理请求异常、工具批次、执行限制等情况。

### 一段最小伪代码

~~~python
# 教学伪代码：不是 DeepSeek Harness 的逐字实现
while True:
    request = build_request(history, available_tools)
    response = call_model(request)

    if response.has_tool_calls:
        results = execute_tools(response.tool_calls)
        history = record_results(history, response, results)
        if results.should_conclude:
            break
        continue

    break
~~~

这里特别值得注意的是 **“执行结束”和“任务完成”不是一回事**。

例如，模型不再请求工具，或者 Runtime 正常结束本轮执行，并不能证明用户要求的文件真的存在，也不能证明模型正确理解了工具输出。

在 Phase 0 中，我们需要独立核查是否真的发生了 `pwd`、`ls` 调用。在未来的业务 Agent 中，还要独立检查报告内容和引用证据。

那么，怎样核查这些事实，而不是只看模型最后说了什么？

## 六、怎样从 Session 日志还原一次 Agent Loop？

Phase 0 在调用 SDK 时传入了 `session_id`，并使用独立的 `dsh_home` 保存运行资料。

用户最后看到的 `result.final_response` 只是结果文字。如果要知道它是怎样产生的，就需要检查底层的调用与执行记录。

这时才需要理解三个层次：

| 记录层次 | 主要解决的问题 |
| --- | --- |
| **Session** | 哪些历史和事件属于同一段连续交互？ |
| **Turn** | 本轮已接收输入的处理从哪里开始、在哪里结束？ |
| **Step** | 一个 Turn 内先后发生了哪些内部执行步骤？ |

在 DeepSeek Harness 中，`turn()` 会记录 `turn/start` 和 `turn/end`；Turn 内的执行步骤会记录 `step/start` 与 `step/end`。

如果用户一次请求需要多次工具调用，我们就可能看到一个 Turn 包含多个 Step。一个 Step 不一定只有一次模型 API 尝试：例如请求失败后的重试，可能仍发生在同一个 Step 中。

可以用下面的**示意结构**理解这些记录的关系：

~~~text
Session：一段交互历史
  └─ Turn：处理一次输入
       ├─ Step：模型请求工具
       │        → 工具执行 → 结果记录
       ├─ Step：依据已有结果继续判断
       │        → 可能再次调用工具
       └─ Step：模型不再提出工具调用
  └─ Turn 结束，附有结束原因
~~~

并非每一次运行都需要三个 Step；这里展示的是如何阅读层次，而非实测日志。

### 需要检查哪些具体证据？

把最开始的任务转换为一张检查表：

| 需要确认什么 | 可核查的内容 |
| --- | --- |
| 模型是否请求执行 `pwd` | Assistant 消息中的工具调用内容 |
| `pwd` 是否真正执行 | 对应工具结果、输出与退出状态 |
| 结果是否影响后续请求 | 后续模型可见历史或请求内容 |
| `ls -la .` 是否执行 | 工具调用和返回的实际文件列表 |
| 本轮为何结束 | Turn 的结束事件、结束原因 |
| 用户收到什么 | SDK 返回的最终响应 |

当前 [`src/session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py) 只统计 JSONL 文件里的**事件类型和数量**，不展示敏感的完整工具负载。它可以用于初步观察，但不能仅凭事件计数证明命令确实成功执行，也不能证明模型利用了某条结果。

为了验证具体调用链，仍需在安全环境中检查相应的原始事件及模型请求，按工具调用与结果建立配对，并对日志做必要脱敏。

### 现阶段怎样运行这项实验？

仓库已有 [`scripts/run-docker.sh`](./labs/sdk-minimal-phase0/scripts/run-docker.sh)：

~~~bash
cd agent-runtime/labs/sdk-minimal-phase0
bash scripts/run-docker.sh check
bash scripts/run-docker.sh test
bash scripts/run-docker.sh build

# 在安全环境中设置专用测试 DEEPSEEK_API_KEY
bash scripts/run-docker.sh run
bash scripts/run-docker.sh inspect
~~~

`test` 执行本地离线测试；`run` 才会尝试真实模型运行；`inspect` 仅汇总 Session 事件结构。**它们的职责不同，离线测试成功不能替代真实模型—工具调用验证。**

此外，`sdk-minimal` 的 Shell 默认使用 `danger-full-access` 策略。设置 `cwd` **不构成沙箱**；必须使用隔离容器、可丢弃工作区和专用凭据。当前 Docker 配置仍允许网络出站，且容器内环境变量可能被 Shell 访问，因此不能把银行内部资料、真实敏感数据或高权限凭据放入实验环境。

## 七、哪些能力由 DeepSeek Harness 提供，哪些需要新 Agent 自己实现？

沿着前面的例子，我们已经看到模型请求、工具执行、结果反馈和循环结束的全过程。这里还有一个工程上的问题：

**既然 Python 代码只需要调用 `harness.run()`，是否意味着 Agent 已经开发完成？**

并不是。我们之所以只写了少量 Python 代码，是因为 **DeepSeek Harness 已经实现了通用的运行机制**。我们仍然需要把这些机制配置到自己的执行环境，并实现具体业务任务所需的能力。

以目前的 Phase 0 实验和未来的 JD Research Agent 为例，可以区分三个层次。

| 需要的能力 | DeepSeek Harness 已提供什么 | 我们自己的项目负责什么 |
| --- | --- | --- |
| **模型调用** | 模型适配器、请求装配与响应处理机制 | 选择可用的模型、配置调用参数和凭据，并验证实际可用性 |
| **Agent Loop** | 根据模型响应决定执行工具还是结束，并在需要时继续模型调用 | 提供任务入口；不必重新实现基础循环 |
| **工具机制** | 工具注册表、Schema 装配、调用分发和执行器 | 选择允许使用哪些工具；需要新业务能力时自己实现或接入工具 |
| **Bash 工具** | `sdk-minimal` 已装配持久 Bash 工具及终端后端 | Phase 0 选择此 Profile，并准备隔离目录和受控容器 |
| **执行反馈** | 处理工具返回，将调用与结果记录到运行历史，供后续模型请求使用 | 设计业务工具应返回哪些数据和错误，确保结果可用于判断 |
| **Session 与记录** | Session 及 JSONL 持久化等基础机制 | 指定数据目录与 Session ID；实现必要的日志检查和业务证据保存 |
| **执行控制** | 基础的结束、错误、取消等运行处理机制及相关扩展接口 | 根据业务风险补充超时预算、批准规则、失败处置和外部副作用控制 |
| **任务理解与业务完成** | 模型可以依据任务与工具信息作出下一步判断 | 明确任务目标、数据范围、评价标准；验证真实业务产物是否符合要求 |

### 1. 当前 Phase 0 自己到底实现了什么？

[实验源码](./labs/sdk-minimal-phase0/README.md) 中真正由我们维护的是：

- [`run_phase0.py`](./labs/sdk-minimal-phase0/src/run_phase0.py)：准备任务、初始化 SDK、调用 `run()`，收集返回信息。
- [`run-docker.sh`](./labs/sdk-minimal-phase0/scripts/run-docker.sh) 与 [Dockerfile](./labs/sdk-minimal-phase0/docker/Dockerfile)：建立和启动实验运行环境。
- [`session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py)：统计本地 Session 事件的种类和数量。
- [配置补丁](./labs/sdk-minimal-phase0/config/disable-session-upload.patch.yml) 与离线测试：配置日志附加行为并检查应用包装代码。

也就是说，**我们没有自己写 `while` 循环、没有自行开发 Bash 工具执行器，也没有开发岗位检索工具**。这些不是缺漏的同一类问题：前两项可直接使用 Harness 的通用机制；岗位检索则是新业务 Agent 需要补充的能力。

### 2. 以后让 Agent 研究招聘岗位，还需要开发什么？

假设下一阶段的目标是：

> 读取完整 JD，识别 RAG 技术要求，区分必备与优先条件，并生成能够追溯到职位 ID 的报告。

DeepSeek Harness 仍然可以负责模型调用、工具执行和循环控制。但我们还需要提供 **职位数据的读取能力、检索或筛选接口、输出格式、证据校验和结果验收规则**。这些能力可以由专门的业务工具、固定工作流与模型决策组合实现，而不是期待 SDK 自动理解岗位数据库或保证统计结果正确。

显式 Planner、独立 Checker、多个 Agent、人工审批等也不是每个任务启动前都必须自行实现的一套组件；只有业务复杂度、风险与验证需求要求它们时，才逐步增加。

需要区分 **“框架具备扩展机制”** 与 **“当前项目已经配置并完成验证”**。例如，Harness 有工具权限和执行控制接口，并不意味着 Phase 0 的 `danger-full-access` Shell 已经具备生产级安全隔离；同样，SDK 能记录 Session，也不意味着岗位分析报告经过了业务验收。

**因此，我们构建新 Agent 的主要工作不是重新编写通用 Agent Loop，而是明确工作任务、接入真实业务能力、约束执行边界，并验证最终成果。**

---

## 八、从一次任务中应该真正理解什么？

一开始，应用只提交一句自然语言任务。随后发生的是：

~~~text
任务进入 Harness
       ↓
Runtime 根据 Profile 准备可用工具
       ↓
构造含工具说明与历史的模型请求
       ↓
模型返回文字或工具调用请求
       ↓
Runtime 识别并执行工具调用
       ↓
记录真实结果，必要时继续模型请求
       ↓
根据响应和运行条件结束本轮执行
       ↓
返回结果，并保留可核查的运行记录
~~~

这条链路解释了三个关键区别：

**一、一次 `harness.run()` 不等于一次模型请求。** Runtime 可以在一次运行中反复调用模型、执行工具。

**二、模型提出工具调用不等于工具已经执行。** 真正的操作来自预先装配的工具和 Runtime 执行器。

**三、Runtime 正常结束不等于业务任务成功。** 是否完成了真实工作，必须根据工具结果和任务产物单独核查。

学习 Agent Loop 的目标，不是记住一组术语，而是能够沿着一项真实任务，解释每一次模型请求为什么发生、工具实际上做了什么、结果怎样进入下一次判断，以及本轮为什么结束。

## 阅读入口

- [00 · Agent 与 Runtime](./README.md)——为什么从模型回答扩展到执行任务
- [学习路线](./LEARNING_PATH.md)——01 与后续专题的边界和实践阶段
- [Phase 0 实验入口](./labs/sdk-minimal-phase0/README.md)——运行环境与操作说明
- [Phase 0 逐行代码解读](./labs/sdk-minimal-phase0/01-code-walkthrough.md)——Python SDK、脚本和 Session 统计代码
- [本仓库 Python 运行入口](./labs/sdk-minimal-phase0/src/run_phase0.py)
- [本仓库 Profile 补丁](./labs/sdk-minimal-phase0/config/disable-session-upload.patch.yml)
- [DeepSeek Harness：sdk-minimal Profile 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)
- [DeepSeek Harness：ReactLoopAgent 源码](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts)
- [DeepSeek Harness：工具注册机制](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md)
