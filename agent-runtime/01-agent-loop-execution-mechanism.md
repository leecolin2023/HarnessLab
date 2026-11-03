# 01 · Agent Loop 的运行机制：一次任务怎样真正执行起来？

> 本篇承接 [00 · Agent 与 Runtime](./README.md)。00 已经说明 Agent 为什么需要“模型决策 → 工具执行 → 反馈 → 继续或结束”；本篇不再重复这个定义，而是从一个**能够观察的实际任务**出发，解释每一次行动究竟如何发生，以及为什么能接着执行下一步。
>
> 贯穿案例是 [SDK Phase 0 实验](./labs/sdk-minimal-phase0/README.md) 当前阶段 0 的最小任务。文章中标为“示意”的输出和运行轨迹用于讲解机制，不是已经获得的真实 Session 日志。应用代码与 DeepSeek Harness 源码可以核对执行路径，但目前尚缺少公开可核验的完整模型调用轨迹。

## 一、向 Agent 发送一句话，它是怎样开始执行任务的？

假设我们已经启动一个可以使用 Bash 工具的 Agent。现在像平时聊天一样，**只向它发送一句自然语言指令**：

> 请在隔离工作目录中执行 `pwd`，再执行 `ls -la .`，最后根据实际结果告诉我当前目录和里面有哪些文件。

我们并没有手动编写“先调用哪个函数、再调用哪个函数”的程序。希望 Agent 自己根据这句话执行操作，最后给出真实结果，而不是猜测文件列表。

### 1. 这句话怎样传给 Harness？

最直接的方式，是把它作为字符串传入 DeepSeek Harness Python SDK 的 `run()`：

~~~python
# 假设 harness 已经初始化，并运行在隔离环境中
task = "请在隔离工作目录中执行 pwd，再执行 ls -la .，最后根据实际结果告诉我当前目录和里面有哪些文件。"

result = harness.run(task, session_id="lesson-01")
print(result.final_response)
~~~

这样，`task` 就是我们交给 Agent 的任务描述；`run(task, ...)` 是应用向 Harness 发起任务执行的入口；`result.final_response` 则是本次运行返回给应用的最终文字。

这里故意省略了模型配置、工作目录等初始化代码，先只关注**“发送一句话 → Harness 接收任务”**这一步。上面的调用并不表示命令已经执行成功；是否执行以及执行了什么，要查看工具记录。

当前 [本实验的真实代码](./labs/sdk-minimal-phase0/src/run_phase0.py) 也是这个调用方式。它先把更完整的任务说明保存为 `DEFAULT_PROMPT`（增加只读限制和不得编造结果等要求），再通过 `args.prompt` 传给 SDK：

~~~python
result = harness.run(args.prompt, session_id=args.session_id)
~~~

应用在这之前通过 `DeepSeekHarness(...)` 指定了模型、Profile、工作目录等运行配置。**运行配置决定 Agent 能连接什么环境；自然语言任务决定这一次希望它做什么。** 需要注意，单独设置工作目录 `cwd` 不构成安全沙箱，实际实验仍须在隔离容器或虚拟机中进行。

### 2. 发送一句话之后，为什么会出现多个动作？

现在问题来了：Python 只调用了一次 `run()`，但用户希望 Agent 至少完成读取当前路径、列出文件、根据输出进行说明这几个动作。

**为什么一次 `run()` 能够引发多次模型判断和真实工具执行？是谁在第一次模型返回之后继续推进任务？**

一种可能的执行过程是：

~~~text
用户交给 Agent 一项任务
          ↓
模型判断：先执行 pwd
          ↓
工具真的执行 pwd，并返回路径
          ↓
模型根据结果决定执行 ls -la .
          ↓
工具真的执行 ls，并返回文件列表
          ↓
模型根据实际结果生成说明
          ↓
本次运行结束
~~~

这是一条**帮助理解的示意路径**。真实模型也可能在一次响应中提出多个工具调用，或者改变执行顺序；不能把这张图当作已经观察到的日志。

这张图的第一步是“模型判断：先执行 `pwd`”。但模型怎么知道它能够使用 Bash 工具，又怎样把“执行命令”表达为真实可执行的行动请求？这就需要从第一次模型调用说起。

## 二、模型为什么知道可以执行 `pwd`，而不只是回答一段文字？

假设我们直接调用一个普通文本模型：

> 你现在位于什么工作目录？

模型可以生成文字，但它并不知道当前容器的真实路径。它也不会因为说出“我执行一下 `pwd`”，就真的操作了文件系统。

所以，当我们要求模型**选择真实行动**时，必须先让它知道外部有哪些操作能力可用。

但“运行环境提供工具”这句话还不够具体。**工具究竟在哪里定义、怎样交给 Agent，以及模型为什么能看到它？**

### 1. 这个例子中的 Bash 工具是谁提供的？

先回到 本实验已有的 Python 代码。启动时有一个容易被忽略的配置：

~~~python
with DeepSeekHarness(
    provider="deepseek-official",
    model=args.model,
    cwd=str(workspace),
    dsh_home=str(home),
    profile="sdk-minimal",
    patches=(str(patch),),
) as harness:
    result = harness.run(args.prompt, session_id=args.session_id)
~~~

这里最关键的是 **`profile="sdk-minimal"`**。它不是告诉模型“请自行想办法执行 Bash”，而是选择 DeepSeek Harness 已经准备好的一套运行配置。

我们在 [DeepSeek Harness 官方 `sdk-minimal/cordis.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) 中可以找到相应的插件装配。下面只摘出与 Bash 相关的配置项（省略了其余配置）：

~~~yaml
- id: terminal-bash
  name: '@deepseek-ai/dsh-terminal-bash'

- id: tools
  name: '@deepseek-ai/dsh-tools'

- id: tool-executor-native
  name: '@deepseek-ai/dsh-tool-executor-native'

- id: agent-loop
  name: '@deepseek-ai/dsh-agent-loop'

- id: persistent-bash
  name: '@deepseek-ai/dsh-tool-bash-persistent'
~~~

这些配置分别解决不同问题：

| 组件 | 在当前任务中的作用 |
| --- | --- |
| `dsh-tool-bash-persistent` | **提供并注册 `bash` 工具**：定义它叫什么、接受什么参数，以及执行时怎么操作 Shell |
| `dsh-tools` | **保存和管理工具定义**：让 Runtime 能查找当前可用的工具 |
| `dsh-tool-executor-native` | **接收并调度实际工具调用**：根据工具名称找到对应实现并执行 |
| `dsh-terminal-bash` | **提供 Bash 终端后端**：让命令能真正交给终端执行 |
| `dsh-agent-loop` | **组织模型与工具的往返循环** |

这就回答了“Bash 从哪里来”：**不是 Python `run()` 自动发明了 Bash，而是 `sdk-minimal` 在启动时装配了 Bash 工具插件。**

在 Linux/macOS 上，该 Profile 使用持久 Bash；在 Windows 上，对应的是 PowerShell。下文继续以 Linux 容器里的 Bash 为例。

### 2. 工具装配好了，模型为什么能知道它存在？

只有 Bash 程序安装在系统里，还不够。

例如，容器里即使装有 `git` 或 `python`，模型也不会自动得到名为 `git`、`python` 的独立工具定义。它需要通过已经公开的 `bash` 工具执行相应命令。

一个能被模型选择的工具，至少需要两方面：

- **面向模型的说明**：工具名称、用途和输入参数，例如 `bash` 接受 `command` 参数。
- **面向执行器的实现**：真正接收参数并执行命令的代码。

[`dsh-tool-bash-persistent` 官方说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/shell/tool-bash-persistent/README.zh.md) 明确指出，它会注册名为 `bash` 的工具。[`dsh-tools` 官方说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md) 则说明，已注册且获准使用的工具，其名称、描述和参数 Schema 会提供给模型。

在当前源码中，Runtime 会先解析本轮可用的工具集合，再据此构造模型请求。

因此，工具从配置到模型的过程是：

~~~text
Python 选择 profile="sdk-minimal"
             ↓
Harness 加载 persistent-bash 工具插件
             ↓
插件向工具注册表注册 bash
             ↓
Runtime 解析本轮可用工具
             ↓
把 bash 的名称、说明和参数 Schema 加入模型请求
             ↓
模型才有机会返回 bash 工具调用
~~~

这里要特别区分：

**注册工具是让系统具有某项能力；把工具 Schema 提供给模型，是让模型知道可以请求这项能力。** 两者都有了，模型才能按接口提出有效的行动请求。

### 3. 如果不是使用内置 Bash，而是提供自己的工具呢？

假设后续 JD Research Agent 需要一个独立的 `read_job` 工具，按职位 ID 读取脱敏的岗位信息，而不是让模型直接运行任意 Shell 命令。

我们就需要自己实现这项功能，并把它注册给 Harness。

DeepSeek Harness 的 [工具注册机制](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md) 提供 `defineTool` 和 `ctx.tools.register()`。一个自定义工具的核心结构可以表示为：

~~~typescript
// 结构示例：需放在正确装配的 Harness 插件中，不能直接粘贴到 Python SDK 执行
ctx.tools.register(defineTool({
  name: 'read_job',
  description: '按职位 ID 读取一条脱敏岗位资料',
  parameters: {
    job_id: { type: 'string', required: true },
  },
  output: {
    schema: { type: 'string' },
    render: (_args, value) => [{ type: 'text', text: value }],
  },
  async execute(args) {
    return readJobFromApprovedDataset(args.job_id) // 示例业务实现
  },
}))
~~~

其中，`name`、`description` 和 `parameters` 帮模型理解怎么调用；`execute` 才是真正读取数据的代码。上面是**说明接口关系的片段**，不是当前 SDK Phase 0 实验 已经实现的功能，也不是可直接运行的完整插件。

完成定义后，还必须让自定义插件被当前 Profile 或配置补丁加载；仅仅编写这个函数并不会使工具自动出现。

另一条路线是接入 MCP Server：由 MCP 客户端发现外部服务器提供的工具，并注册到同一套工具机制中。它解决的是外部工具的接入问题，后续 **03 · Tool Calling 与 MCP** 再展开具体协议与配置。

需要明确：**当前 本实验只配置了现成的 `sdk-minimal` 工具，并没有注册上面的 `read_job`，也没有接好 JD 检索 MCP Server。** 不应误认为 Python SDK 的 `run()` 自动提供所有业务工具。

### 4. 现在回到第一次模型请求

我们已经知道，`bash` 工具为什么会出现在模型可用的工具集合中。

在当前任务中，Runtime 会在构造模型请求时提供与任务有关的信息，其中包括 Bash 工具的名称、说明及参数 Schema。模型于是能够选择提出一个工具调用请求，而不只是生成普通回答。

第一次模型请求可以简化理解为：

~~~text
任务：
  在当前工作目录执行 pwd，再查看文件列表并说明结果

可用能力：
  受控的 Bash 执行工具

已有信息：
  当前任务的上下文

          ↓
       模型推理
          ↓
模型返回：希望调用 Bash 执行 pwd
~~~

这里有两个重要的区别：

**第一，工具通过 Profile 加载、插件注册和 Runtime 的工具集合装配，才真正成为模型可调用的能力。** 这不等于模型拥有任意系统权限。

**第二，工具出现在模型请求中，不等于工具已经被执行。** 模型返回的只是下一步想采取的行动。

这就引出了下一问：模型已经说要执行 `pwd`，谁来把它变成真实操作？

## 三、模型提出工具调用后，命令是谁执行的？

模型可能返回带有工具调用信息的响应。具体字段随模型接口和工具定义而变化，但表达的含义是：

~~~text
工具调用请求：
  工具：Bash
  参数：执行 pwd
~~~

此时 `pwd` 还没有执行。

Runtime 必须先接收模型响应，识别其中是否存在工具调用请求，再交给实际执行器。

在当前核查的 [DeepSeek Harness `ReactLoopAgent` 源码](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts) 中，`step()` 会从 Assistant 消息中筛选类型为 `tool-call` 的内容块。

如果存在工具调用，便进入工具执行路径。核心逻辑可以写成下面的教学伪代码：

~~~python
response = await call_model(request)
tool_calls = find_tool_calls(response)

if tool_calls:
    results = await tool_executor.execute(tool_calls)
~~~

**这段代码中的真正行动是 `tool_executor.execute(...)`，不是模型生成工具请求的那一刻。**

在 本实验当前配置下，执行器来自 DeepSeek Harness 的工具体系；本实验的 Python 脚本没有自己实现一套 Bash 工具执行代码。

如果一切正常，执行器可能得到这样的结果：

~~~text
命令：pwd
退出状态：0
标准输出：/workspace
~~~

这里的 `/workspace` 仅是示意路径，不是本次真实运行结果。

到这里，我们解决了“模型怎样实际执行一次工具操作”的问题。

但这个任务还没有完成：我们只知道工作目录，还不知道目录里有什么。于是出现了更重要的问题：

**已经执行的工具结果，怎样让模型在下一次判断时使用？**

## 四、`pwd` 返回结果之后，模型为什么还能继续执行 `ls`？

想象一下，如果执行器运行完 `pwd`，却没有把结果传给模型，会怎样？

模型可能仍然不知道实际路径，只能重复猜测。即使接下来执行了 `ls`，它也未必知道前一个动作是否成功。

所以，工具执行完成之后，需要把结果保留为后续模型能够获得的信息。

例如，下一次模型请求应能表达这样的事实：

~~~text
此前任务：
  在当前工作目录查看路径和文件列表

此前行动：
  请求执行 pwd

真实结果：
  执行成功，返回 /workspace

尚未完成：
  查看文件列表，并根据真实输出说明结果
~~~

模型基于这些信息，才有条件提出下一步行动，例如执行 `ls -la .`。

这就是反馈的实际作用：**不是单纯记录“做过一件事”，而是让上一轮的真实结果成为下一轮决策的输入。**

在当前 DeepSeek Harness 源码中，Assistant 消息与工具执行相关信息会进入 Session 的事件与历史机制，后续请求再从这些历史构造模型可见内容。应用端不需要在每次工具返回后手工重新拼接完整 Prompt。

将过程接起来：

~~~text
第一次模型判断
  └─ 请求执行 pwd
          ↓
Runtime 交给 Bash 工具
          ↓
Bash 返回实际路径
          ↓
Runtime 保留调用与结果
          ↓
准备下一次模型请求
  └─ 模型能看到先前工具的实际结果
          ↓
模型继续请求 ls，或者选择其他行动
~~~

这里也说明了为什么一次 `run()` 可以涉及多次模型请求：**Runtime 没有在第一次工具调用后立刻返回，而是将结果带入后续决策。**

### 如果 `pwd` 失败了呢？

例如，工具返回错误而不是路径。

如果 Runtime 让模型获得了这个错误信息，模型才可能考虑换一种方式检查环境，或者如实说明无法执行。

但需要区分：

- 工具把错误返回给 Runtime；
- Runtime 让模型在后续请求中看到错误；
- 模型确实根据错误改变了行动。

这三件事不是一回事。前两者构成反馈通道，第三件事是否发生，必须根据具体运行结果判断。

现在，一次工具调用与下一次模型决策已经连接起来了。但是程序也不能永远重复调用模型。

那么，**Runtime 凭什么知道应该继续，还是结束？**

## 五、模型每次返回之后，Runtime 怎样决定继续或结束？

假设模型已经执行 `pwd` 和 `ls`，现在根据工具结果返回一段说明文字，没有再提出新的工具调用。

此时 Runtime 就不应该继续无意义地执行工具。

但如果模型返回的是新的工具调用请求，Runtime 则通常还需要执行工具，并在适当情况下进入下一次模型推理。

因此，Runtime 需要检查每一次模型响应，而不是无条件继续。

先看最基本的两条路径：

~~~text
模型返回响应
      ↓
包含工具调用请求吗？
    ├─ 是 → 执行工具 → 获取结果 → 继续下一轮判断
    └─ 否 → 当前模型—工具执行步骤可以结束
~~~

这就是 Agent Loop 的基本分支。

对照当前 DeepSeek Harness 的 `step()` 源码，可以看到两个关键事实：

1. 如果 Assistant 消息没有 `tool-call`，`step()` 返回 `completed`。
2. 如果存在工具调用，Runtime 会执行工具批次；工具批次的返回结果还可能决定当前步骤直接结束，还是继续后续步骤。

因此，不能把它简化成“只要调用过工具，就一定再次调用模型”。**是否继续还受到工具执行结果和运行控制条件影响。**

另外，还可能出现模型请求失败、输出达到限制、工具执行异常、执行被取消等情况。它们不能被当作正常完成。更深入的重试、超时和补偿机制放在后续的“执行控制与故障恢复”专题研究。

### 这时再回看完整循环

现在我们已经顺着一个真实操作理解了各环节为什么存在，可以把它们合起来：

~~~python
# 仅解释机制，不是 DeepSeek Harness 的逐字源码
while True:
    request = prepare_model_request(history, available_tools)
    response = call_model(request)

    if response.has_tool_calls:
        results = execute_tools(response.tool_calls)
        history = record_calls_and_results(history, response, results)
        continue

    return finish_current_run(response)
~~~

这个简化循环说明：模型负责提出行动；Runtime 负责把行动变成真实执行、记录反馈，并决定下一轮是否发生。

在完整实现中，还需要处理工具批次直接结束、异常、取消和运行限制，因此不能把伪代码当成 SDK 的全部控制分支。

**至此，我们从一次 `pwd` 操作，推导出了 Agent Loop 的运行机制，而不是先背下 Loop 定义，再寻找例子。**

不过，学会画循环图还不够。下一步是验证：**这个过程在真实程序里到底发生了几次？**

## 六、怎样在日志中找到刚才的每一次行动？这时为什么需要 Turn、Step 和 Session？

现在才需要引入之前容易让人困惑的几个术语。

假设程序运行结束，只返回一段最终说明：

> 当前目录包含三个文件……

仅凭这句话，我们不知道模型是否真的执行过 `pwd`、`ls`，也不知道中间调用了几次模型。

要还原过程，就需要查看运行过程中保留的记录。

### 1. 为什么需要 Session？

当我们希望知道某项任务的历史调用和执行结果时，需要一个能够关联它们的身份及记录。

在 DeepSeek Harness 中，**Session** 承担连续交互与执行事件的关联和持久化职责。

这里先只记住它的作用：

> 查找同一段任务交互发生过什么，需要从对应的 Session 记录入手。

Session 不是一个模型请求，也不是一个工具操作。

### 2. 已经找到 Session，为什么还有 Turn？

因为同一个 Session 可能先后接收多次用户输入。

运行日志需要标记：哪些操作属于本轮被处理的输入，哪些属于后续新输入。

在 DeepSeek Harness 当前实现中，一轮输入处理具有 **Turn** 边界，源码会写入 `turn/start` 与 `turn/end`。

因此，Turn 帮助我们回答：

> **这一轮用户输入引发的处理从哪里开始、到哪里结束？**

### 3. 一个 Turn 里面为什么还有 Step？

刚才的示意过程包含：模型决定执行 `pwd`，看到结果后又决定执行 `ls`，最后给出说明。

这些连续的内部处理步骤需要能够区分。

DeepSeek Harness 使用 **Step** 作为 Turn 内的执行边界，源码会记录 `step/start` 和 `step/end`。

因此，Step 帮助我们回答：

> **同一轮输入中，Runtime 先后经历了哪些内部执行步骤？**

但不要把 Step 等同于模型 API 请求：一个 Step 中可能因为模型请求重试而发生多次请求；一次模型响应也可能包含多个工具调用。

### 4. 这些概念现在怎样帮助我们理解运行？

我们就能按层次找到真正关心的东西：

~~~text
Session：这一段连续交互及其事件记录
  └─ Turn：处理一次已接收输入
      ├─ Step：准备模型请求，收到工具调用并执行
      ├─ Step：利用结果继续判断和执行
      └─ Step：完成本轮响应
~~~

这是一个**解释记录层次的示意图**，并不规定每个任务必须有三个 Step。

由此可以看出，术语不是学习 Agent Loop 的起点。它们是在我们需要**核查多次行动究竟怎样发生**时才有用的定位工具。

## 七、如何用 SDK Phase 0 实验 验证这篇文章，而不是只相信示意图？

当前项目已经提供两个入口：

- [`src/run_phase0.py`](./labs/sdk-minimal-phase0/src/run_phase0.py)：通过 SDK 运行最小任务，并保存运行元数据。
- [`src/session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py)：统计 Session JSONL 的事件种类和数量。

但这里存在一个重要限制：`session_report.py` 目前只汇总事件类型及数量，**不展示模型的具体工具请求及对应执行结果**。

因此，不能仅凭“日志存在三个事件”，就断言模型执行了三个工具。

### 第一轮真正要验证什么？

先在独立容器里运行阶段 0 的示例（具体命令与隔离边界见 [SDK Phase 0 实验 README](./labs/sdk-minimal-phase0/README.md)）。

然后按下面的因果顺序核查：

| 想回答的问题 | 应该核查的证据 |
| --- | --- |
| 模型是否请求执行 `pwd`？ | Assistant 响应中有没有对应的工具调用 |
| `pwd` 是否实际执行？ | 工具执行结果及对应退出状态 |
| 模型是否获得了反馈？ | 后续模型请求中是否包含该结果 |
| 是否又执行了 `ls`？ | 新的工具调用与执行记录 |
| Runtime 为什么结束？ | Step/Turn 结束原因与 SDK 的运行终态 |

这里的“后续模型请求中实际包含了什么”需要能观察相应请求或可验证的派生消息，不能只根据最终回答猜测。

对于当前 DSH 实现，可沿 [`ReactLoopAgent` 源码](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts) 定位：

- `preStep()` 与 `buildRequest()`：模型请求是怎样准备出来的；
- `step()`：模型响应怎样进入工具执行或完成分支；
- `turn()`：一次输入怎样经过多个 Step，并留下结束原因。

**这些是源码层面的机制证据，还不是本次任务已经按预期执行的证明。** 真实运行轨迹需要以实际环境、SDK/Runtime 版本和本地 Session 为准。

### 最后，怎么把这个认识迁移到真正的 JD 研究任务？

当前演示只是读取工作目录，尚未实现 JD 统计。等进入下一阶段，用户可能提出：

> 读取一组固定的完整 JD，找出涉及 RAG 的岗位，并生成带职位 ID 的报告。

任务变了，但运行机制仍然是同一条链：

~~~text
模型决定读取职位文件
        ↓
工具返回 JD 原文
        ↓
模型利用原文选择下一项处理
        ↓
工具生成实际报告文件
        ↓
检查报告是否存在、证据是否可回查
~~~

最后一项“报告是否真实且正确”是**业务任务验证**，并不等于 Runtime 正常结束。后续 08 专题再深入研究这一差别。

---

## 八、本篇最终要弄懂什么？

从一次 `run()` 出发，我们依次解决了六个问题：

1. 为什么一个 SDK 调用可能包含多个模型请求和工具操作？
2. 运行环境如何装配并注册工具，模型又如何获得工具说明？
3. 模型提出的工具请求怎样变成真实执行？
4. 工具结果怎样进入下一次模型判断？
5. Runtime 根据什么继续或结束循环？
6. 怎样通过 Session、Turn、Step 和真实工具事件核查上述过程？

到这里，Agent Loop 不再只是一句“模型决策、工具执行、反馈”的定义，而是一条能够沿程序源码和运行记录追踪的执行链。

**本篇最重要的判断标准是：面对一次 Agent 运行，能否沿着“模型请求 → 模型响应 → 实际工具执行 → 反馈进入下一次请求 → 结束原因”解释它究竟做了什么，以及为什么能够继续。**

接下来的课程再深入研究其他问题：

- **02 · Workflow、Planning 与 Multi-Agent**：多个步骤由谁控制、何时需要显式计划或多 Agent。
- **03 · Tool Calling 与 MCP**：工具定义、注册、协议和实际业务接口怎样连接。
- **04 · Context Engineering**：每轮请求到底该包含哪些信息。
- **05 · State、Session、Checkpoint**：历史和任务进度怎样持久化与恢复。
- **06 · 执行控制与故障恢复**：异常、取消、重试和副作用怎样安全处理。
- **08 · 任务验证与结束条件**：怎样判断工作成果真正符合目标。

## 参考资料

- [00 · Agent 与 Runtime](./README.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [Phase 0 实验代码架构解读](./labs/sdk-minimal-phase0/01-code-walkthrough.md)
- [SDK Phase 0 应用入口（固定提交）](./labs/sdk-minimal-phase0/src/run_phase0.py)
- [DeepSeek Harness Agent Loop 源码（固定提交）](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/core/agent-loop/src/agent.ts)
