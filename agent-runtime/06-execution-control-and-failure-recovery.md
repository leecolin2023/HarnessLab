# 06 · 执行控制与故障恢复：工具失败以后，Agent 应该怎么办？

> **学习目标**：理解 Agent 的工具调用发生超时、失败、取消或结果未知时，谁决定重试、停止、核查与补偿；分清 Retry、Idempotency、Resume 和 Compensation。
>
> **贯穿任务**：JD Research Agent 先通过只读的 `get_job(job_id)` 获取招聘信息，再通过 `save_report(...)` 保存报告。这两个操作都可能超时，却不能采取相同的恢复方式。
>
> **前后关系**：[05 · State、Session、Checkpoint](./05-state-session-checkpoint.md) 讨论中断后保存了什么，本篇讨论**知道出现了什么异常后，下一项行动该怎么安全执行**。07 再专门研究权限、Sandbox 和人工审批。
>
> **代码边界**：当前 [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 已有 DeepSeek Harness SDK、持久 Bash、Session 和离线包装测试，尚未实现 JD 工具、报告写入器或故障注入实验。下文案例与代码均为教学设计，不代表已执行的业务实验。

## 一、读取 JD 超时了，为什么不能立即把它当成失败？

用户给 Agent 一项任务：

> 读取 JD-001 的完整岗位要求，判断 Milvus、Python 等技术是必备还是优先，并附原文证据。

Agent 发起工具调用：

~~~text
模型：get_job(job_id="JD-001")
       ↓
Runtime：把请求交给职位查询服务
       ↓
等待查询结果
       ↓
5 秒后仍然没有收到响应
~~~

模型现在知道的，只有“客户端没在截止时间内获得查询结果”。

我们需要区分至少三种可能：

~~~text
A. 调用在执行前被取消，工具正文没有开始
B. 查询已经开始，但尚未完成
C. 查询已经完成，只是成功响应丢失
~~~

三种情况都可能表现为“没有收到结果”，但对应的事实不同。

如果这是**固定快照上的纯只读查询**，重新读取通常不会造成外部副作用，我们可以在限制次数和预算的前提下重试。

但如果调用是“保存分析报告”或“发送完成通知”，远端也许已经完成操作。此时重复提交可能生成第二份产物。

所以，处理失败的首要问题是：

**实际执行状态能够确认到什么程度？再次执行是否会改变外部世界？**

## 二、同样没有成功响应，下一步为什么不同？

业务工具应该把正常业务结果和技术执行异常区分开。

例如，查不到指定职位是一种正常查询结果：

~~~json
{"status":"not_found","job_id":"JD-001"}
~~~

查询服务不可达则不同：

~~~json
{"status":"error","code":"UPSTREAM_UNAVAILABLE"}
~~~

前者不应该因为“没找到”就无休止重试；后者可能允许一段时间后重新查询。

可以从结果证据判断下一步：

| 能确认的情况 | 下一步怎么处理 |
| --- | --- |
| 工具正文尚未分发 | 修正错误后可考虑发起操作 |
| 工具明确成功 | 验证返回结果与业务质量 |
| 查询成功但无记录 | 返回未找到，而非作为服务故障重试 |
| 临时服务器故障 | 判断操作是否适合有界重试 |
| 请求超时、结果未知 | 有副作用时先查外部真实状态 |
| 用户取消 | 停止新操作，并核查已开始操作的影响 |
| 参数非法或权限拒绝 | 不应靠重复相同请求解决 |

模型最终说“报告已经生成”也不等于报告真的存在。工具返回成功、业务数据已持久化、报告正确，是三件不同的事实。

## 三、超时要设置在哪一层？模型能够自行决定吗？

不能让模型单独负责“最多等多久”。超时是执行约束，需要运行环境实际执行。

JD 研究任务可能同时有几层预算：

~~~text
整个任务的截止时间和费用上限
           ↓
当前阶段的时间限制
           ↓
单次模型请求和模型重试预算
           ↓
单次工具调用的截止时间
           ↓
工具内部 HTTP / 数据库请求的超时
~~~

例如全任务还剩 10 秒时，即使某工具通常允许重试三次，也不能无视剩余预算继续等待。

### DeepSeek Harness 的真实情况

[`sdk-minimal` 的配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) 为持久 Bash 设置了 `timeoutMs: 300000`，即单条命令最多 300 秒墙钟时间。

[持久 Bash 工具说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/shell/tool-bash-persistent/README.zh.md) 指出超时、取消或 Shell 退出会重置不确定的 Shell 状态，下一次命令进入新 Shell。

**但这不意味着未来自己注册的 `get_job` 自动继承 Bash 的超时。**

[`dsh-tools` 官方说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md) 明确区分：普通工具定义中的 `timeoutMs` 仅作为声明；若要由通用执行层强制工具截止时间，需要装配对应的 `dsh-tool-call-timeout-policy`，或者在业务工具、远端客户端实现自己的实际超时控制。

而且，客户端停止等待不等于服务器已经停止处理。业务工具需要主动响应取消信号；远端服务也应有自己的截止时间与必要的状态查询能力。

## 四、什么情况下需要 Retry？模型请求重试和工具重试一样吗？

假设 Agent 同时碰到两种问题：

~~~text
模型 API：RATE_LIMIT
业务工具：get_job 查询超时
~~~

它们都可能在再次请求后恢复，但属于不同的层次。

### 1. 模型 API 的重试由谁负责？

DeepSeek Harness 提供 [`dsh-llm-retry`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-retry/README.zh.md)，目前的 `sdk-minimal` 也已加载它。

该插件在 Agent 的模型请求步骤处理暂时性错误。官方文档说明，未覆盖的 normal mode 默认对 `EMPTY_RESPONSE`、`RATE_LIMIT`、`SERVER`、`TIMEOUT`、`TRANSPORT` 等代码执行最多五次的有界重试，并使用带抖动的退避。

一次模型重试意味着又发起一次模型服务请求，可能再次产生费用；**它不等于重新执行此前成功的工具调用**。

插件还支持 `always` 模式，但官方明确提醒这种模式可能一直重试不可恢复的错误，直至成功、取消或释放。不能把它当成任何生产任务都应该启用的默认选择。

### 2. 业务工具的重试由谁负责？

对 `get_job("JD-001")` 的重试需要独立的业务策略。例如：

~~~python
# 机制伪代码：并非当前 HarnessLab 的可运行脚本
for attempt in range(1, MAX_ATTEMPTS + 1):
    try:
        result = read_fixed_snapshot("JD-001", timeout=PER_CALL_LIMIT)
        return check_query_result(result)
    except TemporaryServiceError:
        if attempt == MAX_ATTEMPTS or overall_deadline_reached():
            raise
        backoff_with_jitter(attempt)
~~~

其中“职位不存在”“参数不合法”和“权限不足”不应该被无差别当作暂时性错误。

重试还应固定数据快照；否则所谓“再次读取同一职位”，可能得到版本已经发生变化的新 JD，造成统计不一致。

### 3. 为什么需要次数和总预算两层约束？

只限制“最多重试三次”不代表任务延迟可控：每次请求自身可能等得很久。

反过来，只限制总时间但允许无限请求，也可能给模型服务或业务 API 带来不必要的压力与费用。

更稳妥的控制至少包括**可重试错误类型、最大尝试次数、单次截止时间、整体剩余时间**。它们解决的是“有限恢复”，而不是让 Agent 永远坚持到成功。

## 五、报告可能已经写入，为什么不能照搬查询的重试？

现在换成另一个工具：

~~~text
save_report(task_id="rag-study", content=report)
~~~

假设报告实际上保存成功了，但客户端在收到“成功”消息前断开。

如果再次执行同一调用，结果可能是：

- 按追加模式重复写入；
- 生成两条相同数据库记录；
- 覆盖另一个执行者修改过的报告；
- 重复触发发布或通知。

这类问题需要 **Idempotency（幂等）**：同一业务操作重复提交，产生的约定业务效果应该与成功执行一次等价。

### 幂等键为什么需要来自业务，而不是随便生成一个随机 ID？

同一个研究任务、相同快照与规则版本、相同报告产物应有一个稳定操作身份，例如：

~~~text
operation_key = (task_id, snapshot_hash, rule_version, output_name)
~~~

服务收到重复的 `operation_key` 和相同内容摘要，可以返回此前已完成的结果；若键相同而内容不同，应明确拒绝冲突或进入版本更正流程。

如果每一次重试都生成一个新的随机键，服务便无法知道它们其实属于同一项写入意图。

### 文件写入应该怎么做？

教学实验可以先将完整内容写入临时文件并校验，再原子替换目标文件。但原子替换仅帮助保证**单个文件**不会被半截覆盖；并不能自动使报告文件、数据库状态与消息通知共同形成一个事务。

对于并发写者，仍需要唯一约束、锁或事务。对于远端 API，必须验证接收端真的按幂等键去重，而不是客户端单方面相信某个 header 生效了。

如果报告工具结果未知，安全顺序是：**先查询现有产物和摘要，再判断是否需要再次提交。**

## 六、用户点击“停止”，正在执行的工具会立刻撤销吗？

假设模型正在保存 `report.md`，用户此时点击取消。

这意味着用户不再希望继续新的工作，但不能推断**已发出的请求在远端一定没有生效**。

需要区分：

- **Timeout**：操作超出某个执行阶段的时间预算。
- **Cancel**：用户或上层系统要求停止后续工作。
- **Abort**：具体执行组件接到中止信号后，尝试停止其拥有的活动。

取消不是数据库事务的 rollback，也不是一台远程服务器已经撤销操作的证明。

### DeepSeek Harness 采用什么方式？

[`dsh-tools`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md) 采用协作式取消：工具实现能够获得取消信号，应该及时观察该信号。

如果在真正分发工具正文前就取消，Runtime 可报告 `ABORTED_BEFORE_DISPATCH`。对于已经开始的操作，结果可能成为 `ABORTED`，但仍应核实远端是否已经产生副作用。

[原生工具执行器](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tool-executor-native/README.zh.md) 不能强行终止一个忽略取消信号的同进程工具，而是需要等待已启动活动结算。

持久 Bash 的实现另有自身的超时、终止与 Shell 重置机制。它不代表所有未来的数据库、HTTP 或 MCP 工具都会自动取消服务器端的工作。

**业务约束**：取消后不要再由模型自由发起新的补救操作；对于已经开始的写入，应由受控程序查询其最终状态，必要时进入获授权的修正流程。

## 七、操作已经部分成功时，为什么还需要 Compensation？

考虑一项比“保存文件”稍复杂的工作：

~~~text
生成报告
    ↓
写入报告索引
    ↓
发送完成通知
~~~

如果前两个步骤成功，最后的通知失败，怎么办？

我们不能简单说“全部重新执行”。因为再次生成和索引报告可能产生重复；而且通知也有可能已经送达、只是成功响应丢失。

先核对每一步的真实状态，再决定下一项行动。有时可以只重试**具备幂等键的通知步骤**；有时需要将报告标记为“已生成、通知待处理”；有时需要撤回一项尚未公开的中间产物。

如果必须通过新的业务动作来修正已经发生的效果，这叫 **Compensation（补偿）**。

### 它与 Rollback 有什么不同？

数据库事务 rollback 可以在同一事务的提交边界内撤销未提交的修改；但文件、数据库、远程 API 和外部消息通常不能全部纳入一个事务。

例如，已经被外部人员读取的报告，即使后来删除，也不能保证对方没有留下副本。

因此补偿是一项**具有业务语义的后续操作**，不保证完整回到过去。发布了错误报告，可能需要发布更正版本，而不是默默删除。

对只读的 `get_job`，一般不存在需要补偿的副作用。对于需要发送、发布或修改外部系统的工具，补偿规则必须由应用定义，并受对应权限与审批约束。

## 八、Agent 一次并行调用多个工具，失败怎么处理？

例如模型一次请求读取 JD-001、JD-002 和 JD-003。三个只读查询通常可以并行。

但“保存报告”和“发布报告”存在先后依赖：后者必须等前者真正完成并通过校验。

DeepSeek Harness 的 [原生执行器](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tool-executor-native/README.zh.md) 支持并行安全的工具调用重叠执行，独占调用形成执行屏障。[Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md) 允许配置 `maxParallelToolCalls`，当前官方默认值为 10，设为 1 表示串行。

但是**Runtime 支持并发，不等于所有业务操作适合并发**。

~~~text
可能安全并行：
  get_job(JD-001)    get_job(JD-002)    get_job(JD-003)

需要业务依赖顺序：
  validate_report → save_report → publish_report
~~~

如果并行批次被取消，其中可能有的工具已完成、有的正在执行、有的根本未启动。恢复时必须逐项核查，不能将整个批次简单标记为“全部成功”或“全部失败”。

## 九、当一次调用没有正常返回，如何决定下一步？

现在能够把文章中的问题串起来。一个适合业务控制器采用的判断路径是：

~~~text
调用没有正常返回
        ↓
能够确定工具正文尚未执行吗？
    ├─ 是 → 根据错误原因修正参数/权限或重新发起
    └─ 否
        ↓
这个操作可能产生外部副作用吗？
    ├─ 否 → 检查是否临时故障、是否还有重试预算
    │         ├─ 有条件 → 有界重试
    │         └─ 无条件 → 记录失败并结束或交人工
    └─ 是
        ↓
查询业务键和外部真实状态
    ├─ 已完成且正确 → 补记成功，禁止重复提交
    ├─ 确认未执行 → 按授权与预算决定是否重新提交
    ├─ 已执行但需修正 → 受控补偿流程
    └─ 仍无法确认 → 标记未知，停止危险重试
~~~

这不是 DeepSeek Harness 自带的 JD 业务状态机，而是我们根据工具副作用性质设计的恢复决策。

它强调两点：

**第一，执行控制不能只凭模型产生的文字判断工具状态。**

**第二，失败处理必须知道真实外部操作的性质。** 只读查询和有副作用写入，适合的重试边界本来就不同。

## 十、DeepSeek Harness 已经提供什么，新 Agent 需要实现什么？

| 机制 | DeepSeek Harness / sdk-minimal | 业务 Agent 的职责 |
| --- | --- | --- |
| Agent Loop 与工具分发 | 已有运行循环、工具注册与原生执行器 | 定义业务工具的输入、结果与边界 |
| 模型请求 Retry | `sdk-minimal` 已装配 `dsh-llm-retry` | 依据具体模型路由与预算检查实际重试行为 |
| 持久 Bash 超时 | 配置了单条命令 300000ms 的超时 | 不误以为所有工具都继承这个超时 |
| 通用工具超时 | 框架有相应声明和可选策略扩展 | 为自定义工具装配真正的截止时间、远端超时和取消机制 |
| 取消 | 提供协作式取消信号和结构化错误 | 让工具支持取消，并核查已开始的远端动作 |
| Session 与恢复 | 有持久事件、写入屏障及未知结果的恢复约定 | 在业务数据层确认操作是否真的发生 |
| 幂等 | Runtime 能保留调用身份与执行记录 | 设计稳定业务键、唯一约束、事务或安全文件提交 |
| 补偿 | 可通过工具或工作流执行补偿操作 | 定义哪些效果可以修正、需要什么授权 |
| 并行执行 | 支持有界并行和独占屏障 | 识别业务依赖，避免不安全并发 |
| 端到端可靠性 | 不自动理解职位统计和报告正确性 | 验证数据快照、统计分母、原文证据与最终产物 |

这意味着，我们不必自行重写模型请求重试器，也不需要重新开发 Agent Loop。

但**一个框架能处理模型请求重试，不等于它知道“同一份报告是否已经被保存过”**。这正是业务 Agent 需要承担的工程职责。

## 十一、用什么最小实验验证这些机制？

根据 [学习路线阶段 7](./LEARNING_PATH.md)，建议先在**纯脱敏、可丢弃的本地环境**准备两种假工具：

- `get_job`：查询固定快照，只读。
- `save_report`：按稳定的任务键写入报告，能核查现有产物。

先不接真实招聘网站、生产数据库或外部发送服务。

### 实验 A：只读工具有一次暂时性故障

第一次返回临时服务错误，第二次成功。确认只有被允许的错误才会按预算重试。

再对比参数非法、权限拒绝和正常的 `not_found`，确认系统不会把所有失败都当作“等一会就能成功”。

### 实验 B：实际写入成功，却故意丢掉成功响应

模拟报告已保存、客户端却超时。恢复时查询相同业务键，验证不会产生第二条记录；同一键但内容不同，应当拒绝冲突或走更正流程。

### 实验 C：在不同时间取消工具

分别在分发前、执行中和执行后发送取消。核对工具是否启动、远端是否有副作用，以及未开始的操作有没有被继续执行。

### 实验 D：把一项工具设置成持续失败

明确设置总时长、模型请求次数与工具重试上限，验证失败不会导致 Agent 一直调用模型或工具。

### 怎样留下可回查的证据？

记录操作 ID、业务幂等键、工具名称、参数摘要、开始时间、截止时间、实际重试次数、取消状态、最终工具结果，以及报告文件或结果表的实际内容。

特别要区分**模型请求重试**与**工具执行重试**；单纯统计“调用了多少次”并不能解释恢复是否正确。

以上都是待实现的实验设计。当前 Phase 0 的 FakeHarness 离线测试和 Session 事件种类统计不能替代这些真实的失败注入结果。

## 十二、这篇文章真正要理解什么？

最初的问题只有一个：一次工具调用没有按时返回成功结果，Agent 应该怎么办？

现在我们知道，关键不在于统一设置“失败重试三次”，而在于**先判断操作是否已开始、是否可能已经完成、是否会产生副作用，再选择控制手段**。

- **Timeout**：规定执行或等待的时间上限。
- **Cancel / Abort**：要求停止后续或正在执行的动作，但不证明外部副作用被撤销。
- **Retry**：针对适合重新执行的失败，在有限预算内再试。
- **Idempotency**：重复提交同一业务意图，不应产生重复业务效果。
- **Resume**：结合真实 State 和 Session，从正确阶段继续，而不是复读最后一个工具调用。
- **Compensation**：通过新的受控业务动作处理已经产生的部分影响。

它们不是每一个 Agent 必须从头实现的六套框架，而是不同失败条件下的工程控制措施。

对于 JD Research Agent，最先需要落地的是：**只读查询的有界重试、写报告的幂等保护、失败类型的明确区分，以及依据真实产物恢复进度**。

下一篇 07 继续研究一个不同的问题：**即使 Agent 知道应该调用某个工具，它是否有权执行？执行到什么程度？** 这才是工具授权、Sandbox 和人工审批的重点。

## 参考阅读

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)
- [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)
- [05 · State、Session、Checkpoint](./05-state-session-checkpoint.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [HarnessLab Phase 0 实验](./labs/sdk-minimal-phase0/README.md)
- [DeepSeek Harness · sdk-minimal 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)
- [DeepSeek Harness · 模型请求重试](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-retry/README.zh.md)
- [DeepSeek Harness · 工具注册与执行控制](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.zh.md)
- [DeepSeek Harness · 原生工具执行器](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tool-executor-native/README.zh.md)
- [DeepSeek Harness · 持久 Bash](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/shell/tool-bash-persistent/README.zh.md)
- [DeepSeek Harness · Session Checkpoint Policy](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-checkpoint-policy/README.zh.md)
