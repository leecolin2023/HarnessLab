# 05 · State、Session、Checkpoint：Agent 中断后，究竟能从哪里继续？

> **学习目标**：理解任务进度、会话历史与持久化检查点各自解决什么问题；能够判断 Agent 进程退出后，哪些信息可以恢复、哪些外部操作不能直接重放。
>
> **贯穿案例**：一个 JD Research Agent 正在分析固定的脱敏岗位快照，已经提取部分职位的技术要求，准备汇总报告时突然退出。我们需要判断：重新启动后，该怎样继续而不是重新做一遍，或重复写入错误结果？
>
> **承接关系**：[04 · Context Engineering](./04-context-engineering.md) 讨论每轮模型应该看到什么；本篇讨论**进程中断后，系统还保存了什么，以及能依据什么继续工作**。
>
> **工程事实边界**：当前 [HarnessLab SDK Minimal Phase 0](./labs/sdk-minimal-phase0/README.md) 有 Python SDK 运行入口、Session 事件统计与 Docker 配置，但没有开发 JD 业务进度检查点，也没有公开可核验的真实中断—恢复实验结果。下文的 JD 数据、文件内容和流程用于解释设计，不是已经实测的业务实现。

## 一、报告已经写到一半，Agent 突然退出，会发生什么？

从一项具体任务开始：

> 统计岗位职责或任职要求中出现 RAG 的岗位，提取 Python、Milvus、BM25、Reranker 等技术要求，区分必备与优先，并输出可回查职位 ID 的报告。

我们让 Agent 处理一批固定的脱敏 JD。假设它已经完成了 JD-001 到 JD-080 的分析，在读取 JD-081 时进程突然退出。

重新运行程序时，至少有三个问题：

1. 模型还能不能看到之前的讨论、工具调用与结论？
2. 应用怎么知道哪些职位已经**实际分析并保存成功**？
3. 如果退出前正在写文件，重启后再次执行是否会重复写入，或者覆盖正确结果？

这三个问题不是一回事。

即使模型恢复了全部聊天历史，也不等于程序知道哪一步已经提交成功；即使某个文件存在，也不能断定文件完整且对应同一份数据快照。

要解决它们，先看我们真正希望恢复的是什么。

## 二、如果只保存一段对话，为什么还不足以继续任务？

假设 Agent 上一次输出：

> 已完成 80 个职位，下一步分析 JD-081。

这句话能帮助理解进度，但它只是**模型声称的进度**。如果实际上 JD-080 的结果还没保存、原文证据缺失，那么按照这句话直接跳到 JD-081，就会造成遗漏。

对于业务系统，我们真正需要的是一份明确的任务状态。例如：

~~~json
{
  "task_id": "rag-requirements-demo",
  "snapshot_id": "jd-snapshot-v1",
  "rule_version": "rag-scope-v1",
  "status": "running",
  "completed_job_ids": ["JD-001", "JD-002"],
  "pending_job_ids": ["JD-003"],
  "results_path": "results/extractions.jsonl",
  "report_path": "results/report.md"
}
~~~

这是**简化的教学状态示例**，不是现有 job-agent 的文件格式。实际系统不能只依赖一个未经校验的 ID 数组，更要确保结果表与标记一致。

### 什么是 State？

**State（状态）** 是完成当前工作所需、能够说明“现在处于什么阶段”的信息。

在 JD 任务中，至少包括：

- **任务身份和输入版本**：对哪一份职位快照、按哪一版统计口径处理。
- **已完成工作**：哪些职位的结构化结果已经校验并保存。
- **尚未完成或失败的工作**：哪些职位仍要读取、重试或人工确认。
- **真实产物位置**：结构化结果、证据和报告写在哪里。
- **任务阶段**：正在提取、待汇总、已完成还是需要恢复核查。

这些内容不一定全部存在一个 JSON 文件里。可以是数据库记录、进度表、结果文件及元数据的组合。

但它们必须能回答：**不依靠模型口头回忆，应用怎样判断下一项实际应该做什么？**

### Session 和 State 有什么不同？

Session 主要关注**Agent 的交互与执行过程**，例如用户说过什么、模型请求过哪些工具、工具返回了什么。

业务 State 关注**这项研究工作的当前事实**，例如哪些职位已持久保存、统计分母是多少、报告是否已完成。

两者可以互相引用，但并不是同一个对象：

| 例子 | 属于哪一层 | 能证明什么 |
| --- | --- | --- |
| 模型说“JD-080 已处理” | 会话中的文字 | 模型作过这个表述 |
| 工具返回“写入 JD-080 结果成功” | 执行记录 | 一次工具调用报告成功 |
| 结果表中存在校验通过的 JD-080 记录 | 业务数据 | 可以确认这条业务结果当前存在 |
| 业务状态将 JD-080 标记为 completed | 业务进度 | 应用认为该记录已完成，仍应与结果表保持一致 |

所以不要把“模型记得进度”当作“业务进度已经可靠落盘”。

## 三、Session 是怎样保存的？重新创建 Agent 就能继续吗？

现在来看 DeepSeek Harness 已经提供的会话能力。

Phase 0 的 [Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py) 用下面的方式启动运行：

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

这里有两个容易忽略的参数：

- `session_id`：识别这段会话的身份。
- `dsh_home`：指定 DeepSeek Harness 的本地存储环境，Session 持久化文件存放在它管理的目录下。

`cwd` 用于指定工作区，**不是安全沙箱**，也不能替代 `dsh_home` 保存 Session。

### 同一个 Session ID，是否一定能读到旧历史？

不一定。还需要原先的持久化资料能够找到并正常读取，使用兼容的 Runtime 配置，而且不能存在互斥占用等问题。

DeepSeek Harness 的 [Python SDK 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md) 提供了明确的恢复接口：

~~~python
# 示意：saved_session_id 是上一次运行实际保存的 Session ID
with DeepSeekHarness(
    dsh_home="/absolute/path/to/saved-home",
    cwd="/absolute/path/to/workspace",
    provider="deepseek-official",
    model="deepseek-v4-flash",
    profile="sdk-minimal",
) as harness:
    session = harness.resume_session(saved_session_id)
    result = session.run("根据已保存的记录，先核查进度，再继续任务。")
~~~

其中具体路径、模型和 Profile 必须与实际可用环境匹配。这是**SDK 用法示例**，不是 Phase 0 已经执行过的恢复脚本。

`resume_session(id)` 会恢复已持久化的历史，并返回可供 `run()` 的 Session；**恢复动作本身不发送新任务输入**。因此，真正继续工作，还需要应用决定后续要发什么任务。

也不要把 `start_session(id)` 当作同义词：SDK 文档明确指出，它只是打开惰性句柄，**不会主动要求恢复既有持久化历史**。

### 恢复了会话，外部 Shell 也会恢复吗？

不会。

SDK 文档明确说明：`resume_session` **不会恢复 Shell、浏览器等外部进程**。即使旧 Session 里记录过某个 Bash 命令，新的运行进程也不意味着旧 Bash 的环境变量、后台子进程或内存状态仍然存在。

同样，工作区文件可能保留，也可能因为容器被销毁、挂载变化或外部操作而不再存在。**会话历史与外部运行环境的连续性必须分别验证。**

因此，“继续之前的聊天”与“恢复之前的执行现场”是两个不同层次的问题。

## 四、Session 历史为什么需要持久化检查点？

现在出现一个更细的风险。

假设 Agent 发起了一次工具调用：

~~~text
模型：调用 save_extraction("JD-080", ...)
                ↓
Runtime 准备执行工具
                ↓
工具成功写入文件
                ↓
进程突然崩溃
                ↓
模型尚未收到工具成功结果
~~~

如果下一次运行只看到“模型请求了写入”，却不知道工具是否已经完成，就无法决定是否安全重试。

这里的第一步是**尽量把已经发生的请求、调用和结果可靠保留下来**。这正是 DeepSeek Harness 自带 Session 持久化和检查点策略的职责。

### DeepSeek Harness 已经装配了什么？

在 [`sdk-minimal` Profile 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) 中，可以找到：

~~~yaml
- id: sessions
  name: '@deepseek-ai/dsh-session-persistence-jsonl'
  config:
    root: !!js dshHomePath('sessions')
    compression: none

- id: session-checkpoint-policy
  name: '@deepseek-ai/dsh-session-checkpoint-policy'
~~~

上面是相关配置节选，不能独立作为完整 Profile 加载。

它们分担两项职责：

**`session-persistence-jsonl` 负责保存会话事件。** `sdk-minimal` 选择不压缩的 JSONL 形式；这说的是**磁盘编码**，与 04 中把模型可见历史压缩为摘要的 Compaction 不是一回事。

**`session-checkpoint-policy` 负责决定什么时候必须确认日志已写入持久化存储。** 不是仅靠“程序最后正常退出时再保存一次”。

### 检查点究竟加在什么地方？

根据 [官方 Session Checkpoint Policy](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-checkpoint-policy/README.zh.md)，它在三个关键边界执行持久化屏障：

1. **模型请求之前**：让相关请求记录先安全落盘，再真正调用模型。
2. **顶层工具执行之前**：让已记录的工具调用先落盘，再执行可能改变外部系统的工具。
3. **进入下一 Agent Step 之前**：把上一 Step 的响应及工具结果等已完成记录刷新，再继续派生下一次请求。

其作用是让 Runtime 在进程崩溃之后，仍有足够的持久事件去判断“之前请求过什么、哪些结果确实被记录了”。

如果持久化屏障失败，当前策略会阻止后续模型请求或顶层工具正文运行，而不是假装日志已经安全。

### 有了它，是否能保证所有工具恰好执行一次？

不能。

检查点可以先记录“即将调用工具”，却**无法与任意外部工具的副作用形成同一个原子事务**。

如果文件写入成功后，进程在写入成功结果事件之前崩溃，恢复时只能看到“调用已发起，结果未知”。

DeepSeek Harness 文档明确将这种中断工具调用恢复为 `TOOL_OUTCOME_UNKNOWN`，并且**不会默认自动重试**。对于可能有副作用的调用，需要先核对外部状态或征求确认。

这是一条非常重要的工程边界：

**持久化检查点帮助系统知道“自己已经做过什么记录”；它不能凭空证明外部动作到底发生到哪一步。**

## 五、什么是业务 Checkpoint？它与 Session 检查点有何不同？

回到 JD 研究任务。

即使 Session 日志能够恢复，我们仍然需要知道：

> 哪些职位的结果已经提交、哪些只做了一半、下一次应该从哪里继续？

这需要业务层的 **Checkpoint（进度恢复点）**。

它可以表现为已校验结果表、阶段状态和输入版本等数据，而不一定要另建一个名字叫 Checkpoint 的文件。

### 一个最小的业务进度设计

例如，每个任务保存：

~~~json
{
  "task_id": "rag-requirements-demo",
  "snapshot_hash": "sha256:example",
  "rule_version": "v1",
  "phase": "extract",
  "completed": ["JD-001", "JD-002"],
  "pending": ["JD-003"],
  "result_store": "results/extractions.jsonl",
  "report_status": "not_started"
}
~~~

这是教学格式；`snapshot_hash` 的值不是真实哈希。它表达的原则是：

- **恢复必须针对同一份输入**，否则“已处理 JD-001”可能对应另一版 JD。
- **恢复必须遵守同一套规则**，否则先前的 required/preferred 分类未必与新结果可比。
- **completed 应以已经持久保存且校验通过的结果为依据**，不能只因为模型说完成。
- **报告状态与提取状态分离**，避免因为报告生成失败而重新分析全部 JD。

### 为什么“保存进度数字”还不够？

假设先写入：

~~~json
{"completed_count": 80}
~~~

但只有 79 条完整结果落盘。

恢复程序看到 80，就可能跳过一条真实未完成的职位。

因此，业务进度要和业务结果建立可验证的关系。更稳妥的做法是：通过稳定的 `(task_id, snapshot_hash, job_id, rule_version)` 识别每条结果，并从已持久化结果推导哪些职位真的完成。

如果进度标记和结果写入属于两个独立文件，需要处理它们之间的提交次序或在恢复时校验一致性。若使用数据库，可以利用事务把结果和状态更新合并为一个提交。

**Session 检查点保护执行历史；业务检查点保护可以可靠续跑的工作进度。** 两者要配合，而不是互相替代。

## 六、最麻烦的情况：文件已经写成功，但完成状态还没写入，怎么办？

假设 JD-080 的结果文件已成功保存，而应用在记录“JD-080 completed”之前突然崩溃。

恢复后出现两种可能：

- **只看进度标记**：JD-080 还没完成，于是再次写入。
- **只看文件是否存在**：文件可能是不完整、上一版本或错误产物。

两者都不可靠。

### 恢复时先核查什么？

先定位这项工作对应的目标记录，然后依次确认：

1. 结果记录是否存在，格式是否完整。
2. 它是否对应同一 `task_id`、输入快照和规则版本。
3. 其中 `job_id`、原文证据与分类字段是否通过规定的校验。
4. 若真实有效，补齐进度标记；若结果缺失或损坏，再按允许的方式重新执行。

例如，恢复规则可以抽象成：

~~~python
# 教学伪代码，非当前仓库的可运行实现
for job in planned_jobs:
    saved = result_store.get(task_id, snapshot_hash, job.job_id, rule_version)

    if saved is not None and validate(saved, job):
        mark_completed(job.job_id)
        continue

    if has_inflight_unknown_side_effect(job.job_id):
        reconcile_external_result_before_retry(job.job_id)
        continue

    result = analyze(job)
    result_store.upsert_validated(job.job_id, result)
    mark_completed(job.job_id)
~~~

这里的 `upsert_validated` 代表“按稳定键重复提交不会产生重复结果”的业务操作，不代表现成的 SDK API。

### 怎样减少重复写入？

对于结果表，可以使用唯一键和事务或幂等写入；对于文件产物，可以先生成临时文件、校验完成，再在同一文件系统中原子替换目标文件，并记录任务版本。

但**原子重命名只解决某个文件提交的完整性，不自动使“文件已写入 + 业务进度已更新”两件事成为同一事务**。如果二者不共用事务，恢复流程必须能处理它们之间的空窗。

对于发送消息、修改远程系统、提交交易等不可轻易撤销的动作，不能照搬“没看见成功结果就重试”。这部分留到 06 的幂等、重试与补偿机制深入讨论。

## 七、重新启动时，应该先恢复 Session，还是先恢复业务 State？

没有必须固定的单一步骤。关键是先明确不同来源各自能证明什么，以及哪个来源决定外部业务步骤是否需要再做。

一个合理的 JD 研究恢复过程是：

~~~text
重新启动应用
      ↓
读取任务元数据：输入快照、规则版本、任务 ID
      ↓
核对业务结果表与真实报告文件
      ↓
确定已完成、未完成与结果未知的工作
      ↓
按需恢复原 Session，供模型理解之前的交互与判断
      ↓
向模型提供当前核实过的状态与下一项合法任务
      ↓
继续处理尚未完成的部分
~~~

注意，这不是要求每次恢复都把整份业务 State 复制到聊天历史；应用可以只将当下工作需要的进度与证据交给模型。

### 为什么不能直接让模型“接着刚才继续”？

如果旧 Session 的最后一条消息是“我将写入 JD-080”，模型可能把这当成未完成动作再执行一次。但业务文件也许早已成功写入。

所以模型的下一步行动不能仅靠旧对话推断。恢复程序应先核对当前结果，再给模型明确的任务，例如：

> 已核对结果表：JD-001 至 JD-080 的完整结果均已校验存在。请从 JD-081 开始分析；不要覆盖已有结果。统计规则仍为 v1。

这个示意 Prompt 中的完成数量必须来自**真实核查结果**，不是人工随便写一个数字。

### 如果 Session 恢复失败怎么办？

例如旧会话不存在、损坏、被占用或与当前 Runtime 不兼容。SDK 文档指出，`resume_session` 在这些情况下会抛出异常，不会默默创建替代 Session。

此时不应假装会话已恢复；如果应用仍然保存了可靠的业务状态、原始数据和工具接口，可以**在独立的新 Session 中继续一个可恢复的业务阶段**，但要明确这是新的会话，并携带必要的已核实进度。

反过来，如果只恢复了 Session，却丢失固定数据快照和结果表，也不能轻率声称整个研究任务可以原样继续。

## 八、如果中断发生在不同位置，恢复策略有什么区别？

为了理解机制，可以把同一条 JD 的处理拆成几个可能发生崩溃的位置。

| 中断位置 | 可以直接确定的事实 | 恢复时的动作 |
| --- | --- | --- |
| 模型请求发出前 | 新的业务分析还没有得到结果 | 核查业务进度后，可重新发起相应工作 |
| 模型生成中途 | 部分输出可能只是暂态 | 不把不完整流当作合格分析结果 |
| 工具调用已记录，尚无结果 | **无法仅凭 Session 判断工具是否有副作用** | 先核查外部状态；不能盲目重复有副作用操作 |
| 结果已写入，完成标记未写入 | 文件与标记可能不一致 | 校验真实结果，必要时补记完成 |
| 完成标记已写入，报告尚未生成 | 提取可能完成但最终报告未完成 | 从汇总或报告阶段继续 |
| 报告已经生成但未做验收 | 产物存在不等于任务成功 | 重新运行规定的验证程序 |

这说明，**恢复不一定是“重新运行最后一个工具”**。它更像是根据已经确认的事实，重新确定下一项安全且必要的工作。

其中“工具调用结果未知”是 Session 恢复中最需要特别处理的场景。DeepSeek Harness 给出 `TOOL_OUTCOME_UNKNOWN` 并拒绝自动重试，正是为了避免 Runtime 在缺少证据时把“未知”强行解释成“没执行过”。

## 九、怎样在 HarnessLab 中真正验证这些结论？

根据 [学习路线阶段 6](./LEARNING_PATH.md)，可以将实验逐步拆成三层，不必一开始就开发完整 JD 业务平台。

### 第一层：确认当前 Phase 0 真正提供什么

阅读 [`run_phase0.py`](./labs/sdk-minimal-phase0/src/run_phase0.py) 可以确认它通过 `harness.run(...)` 发起任务，保存 Session ID、`finish_reason` 和事件种类等元数据；[`session_report.py`](./labs/sdk-minimal-phase0/src/session_report.py) 统计 Session 事件数量。

这些代码**没有实现 `resume_session` 的恢复流程，也没有业务结果表和进度检查点**。

当前仓库的离线测试主要检查包装层逻辑，不是“真实模型运行—中断—重启—恢复”的端到端证据。

### 第二层：独立验证 Session 恢复

在隔离环境中创建一个最小 Session，保存实际 Session ID；正常结束后关闭 Runtime，再使用相同 `dsh_home` 与工作区，通过 `resume_session` 恢复并发起新输入。

观察它能否取得先前对话与必要历史，比较“创建新 Session”“恢复旧 Session”“仅使用相同 Session ID”之间的差别。

进一步可以在可控容器中模拟执行过程中断，检查是否出现正确的结束状态与中断工具结果记录。**这需要真正的事件轨迹，不能只用 FakeHarness 的返回值代替。**

### 第三层：独立验证业务进度恢复

用 5—10 条**固定、脱敏、可人工判断**的 JD 建立最小结果表，设定在“保存结果后、更新完成标记前”中断。

重新启动后，应用应当能够：

- 检测已有且符合快照版本的结果；
- 对缺失结果继续处理，而不是重复追加已完成职位；
- 对结果未知的动作标记需要核查；
- 在不恢复旧 Session 的情况下，仍能根据可靠业务状态从一个阶段边界继续；
- 必要时在恢复旧 Session 后，仍坚持以真实结果表为完成依据。

以上是**待实现、待验证的实验设计**，不代表当前仓库已有这些测试结果。

### 完成标准是什么？

至少能够实际展示三种不同结果：

1. **新 Session**：没有自动承接旧交互历史。
2. **恢复 Session**：可以使用之前持久化的会话历史，但外部进程不会自动复活。
3. **按业务 Checkpoint 继续**：能够依照已核实的结果，从正确职位或正确阶段续跑，而不产生重复统计或重复写入。

如果只能展示“模型记得上一轮说过什么”，还没有验证真正的业务恢复机制。

## 十、哪些能力 DeepSeek Harness 已经提供，哪些需要新 Agent 实现？

| 需要解决的事情 | DeepSeek Harness / sdk-minimal 已提供 | 新 Agent 仍需负责 |
| --- | --- | --- |
| Session 身份与事件历史 | 会话管理、事件记录与 JSONL 持久化 | 记录真实 Session ID，管理对应工作环境 |
| 会话恢复 | SDK 的 `resume_session` 与 Runtime 的历史修复 | 决定何时恢复、恢复后发什么任务 |
| 持久性检查点 | `session-checkpoint-policy` 的三个关键写入屏障 | 不能将其当成业务阶段事务 |
| 中断工具调用 | 将无结果调用识别为未知，并避免默认重试 | 查询外部状态，设计具体的安全恢复决策 |
| 业务 State | 不自动维护职位处理进度与业务口径 | 设计数据快照、进度、结果表和版本 |
| 业务 Checkpoint | 不自动知道“哪些 JD 已完成分析并校验” | 原子写入或事务、幂等去重、恢复核查 |
| 外部运行环境 | 提供工具与运行时机制 | 管理容器、工作区、服务连接和数据权限 |
| 任务成功判定 | Runtime 能返回完成或错误状态 | 校验统计分母、技术分类和报告证据 |

这张表对应两个常被混为一谈的说法：

**“Harness 有 Checkpoint”**——成立，指它具备在关键边界持久化 Session 记录的策略。

**“所以我的 JD Agent 可以从任何中断位置完全恢复工作”**——不成立。业务状态、外部副作用及结果验收仍需要应用层设计。

## 十一、这篇文章最终要理解什么？

从“JD 研究执行到一半突然退出”的场景出发，我们区分了三个紧密相关、却不能互相替代的机制：

**State** 说明业务任务现在是什么状态、还剩哪些工作。

**Session** 保存 Agent 的交互和执行历史，让模型及 Runtime 在后续调用中能够参考之前发生的事情。

**Checkpoint** 是在明确边界持久化可恢复信息的机制；它既可以是 Runtime 的 Session 写入屏障，也可以是业务层可核验的进度提交点，但两者保护的对象不同。

最重要的因果关系是：

> **只有“会话历史恢复 + 业务真实状态核对 + 对未知副作用的安全处理”结合起来，才有可能让 Agent 可靠地继续一项中断的工作。**

下一步的 **06 · 执行控制与故障恢复** 将继续研究超时、重试、幂等、取消与补偿。它所解决的不是“有没有保存过去”，而是“知道过去之后，下一步怎样做才不会造成新的错误”。

## 参考资料

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)
- [04 · Context Engineering](./04-context-engineering.md)
- [学习路线](./LEARNING_PATH.md)
- [SDK Minimal Phase 0](./labs/sdk-minimal-phase0/README.md)
- [Phase 0 Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py)
- [Phase 0 Session 事件统计](./labs/sdk-minimal-phase0/src/session_report.py)
- [DeepSeek Harness Python SDK：`resume_session`](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)
- [DeepSeek Harness：Session Checkpoint Policy](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-checkpoint-policy/README.zh.md)
- [DeepSeek Harness：JSONL Session Persistence](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-persistence-jsonl/README.zh.md)
- [DeepSeek Harness：sdk-minimal 配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)
- [LangGraph：Persistence 与 Checkpoints](https://docs.langchain.com/oss/python/langgraph/persistence)
