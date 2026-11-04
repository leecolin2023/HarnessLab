# 08 · 任务验证与结束条件：Agent 说“完成了”，我们凭什么相信？

> **学习目标**：区分 Runtime 正常结束、工具执行成功、文件生成和业务任务真正完成；理解怎样从用户目标定义可检查的完成标准，并通过 Checker、证据与有限修正决定是否交付。
>
> **贯穿任务**：JD Research Agent 从固定、脱敏的职位快照中筛选岗位职责或任职要求出现 RAG 的职位，提取技术要求，区分必备、优先和未明确，并生成有职位 ID 和原文证据的 `report.md`。
>
> **承接关系**：[01 · Agent Loop](./01-agent-loop-execution-mechanism.md) 研究模型与工具的执行循环及结束分支；[02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md) 研究谁控制工作阶段；[06 · 执行控制与故障恢复](./06-execution-control-and-failure-recovery.md) 研究失败后如何恢复；[07 · 权限、Sandbox 与人工审批](./07-permissions-sandbox-human-approval.md) 研究什么行动被允许。本篇进一步回答：**工具都执行了，结果却可能不合格时，系统凭什么宣布任务完成？**
>
> **事实边界**：目前 [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 只实现 SDK 入口、Bash 最小实验和 Session 事件统计，没有完成 JD 业务工具、报告生成与业务 Checker。文中的 JD、数据结构、工具结果及检查代码均为教学设计，不代表项目已实现或已跑出实际结果。

## 一、报告文件已经生成，为什么任务仍可能失败？

用户提出的任务是：

> 统计岗位职责或任职要求中出现 RAG 的岗位，分析相关技术要求，区分必备与加分项，并提供可回查的职位证据。

假设 Agent 经过多次工具调用，最后告诉我们：

> 已完成分析，报告已经保存到 `report.md`。

文件确实存在：

~~~markdown
# RAG 岗位技术要求分析

本次共统计 80 个岗位。

主要必备技术：Python、Milvus。

结论：Milvus 是 RAG 岗位的普遍必备要求。
~~~

这能证明什么？

**只能证明某份报告写出来了。**

例如，一条原始 JD 其实写的是：

> 必须掌握 Python；有 Milvus 使用经验者优先。

那么这份报告把 Milvus 归为“必备”，已经与证据冲突。

另外，“80 个岗位”可能是模型读过的原始记录数，而不是去重后真正满足统计口径的职位数；报告既没有职位 ID，也没有原文位置，任何人都无法回查所谓的结论。

于是，一个看起来流畅完整的报告，仍可能存在四类问题：

- **范围错误**：遗漏或多纳入岗位，或者选错统计字段。
- **语义错误**：把“优先”当成“必须”，把“无需经验”当成要求。
- **计算错误**：重复计数，或报告中的分母与明细不一致。
- **证据错误**：引文不存在、来源 ID 不对，或结论超出原文能够支持的范围。

如果系统仅凭“模型停止调用工具”或“`report.md` 存在”宣布成功，这些问题就无法被阻止。

因此，第一步不是设计一个更聪明的 Checker，而是明确：**系统要验证的到底是什么成果。**

## 二、Runtime 的 `completed` 究竟是什么意思？

先回到我们实际使用的 DeepSeek Harness。

在 [Phase 0 的 Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py) 中，任务通过 SDK 发出：

~~~python
result = harness.run(args.prompt, session_id=args.session_id)

print(result.finish_reason)
print(result.final_response)
~~~

这两项返回信息并不代表同一件事。

根据 [DeepSeek Harness Python SDK 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)，`RunResult.finish_reason` 对应根会话最后一个 `turn/end` 的结束原因，比如 `completed`、`max-tokens` 或 `error`；`final_response` 是此次活动区间内最后提交的助手文本。

结合 [`ReactLoopAgent.step()` 源码](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts)，模型响应不再包含工具调用时，当前步骤可以返回 `completed`；某个工具批次也可以按照执行结果结束当前步骤。

**这属于 Runtime 的循环控制语义，不是业务验收结论。**

可以把几件事并排比较：

| 观察事实 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| 模型说“完成了” | 模型作出了这一陈述 | 任务确实完成 |
| `save_report` 返回成功 | 工具报告保存操作成功 | 报告内容合格 |
| 工作区存在 `report.md` | 某个文件当前存在 | 数据统计与证据准确 |
| `finish_reason="completed"` | Runtime 这一轮按正常条件结束 | 用户要求的研究结果达标 |
| 应用完成业务验收 | 已按明确标准检查相关产物 | 对一切未知现实场景都绝对正确 |

如果结束原因是 `max-tokens`，模型输出还可能被截断；如果是 `error` 或被取消，更不能直接交付为“已完成”。

### Phase 0 已经验证到哪一步？

当前 [`run_phase0.py`](./labs/sdk-minimal-phase0/src/run_phase0.py) 会保存 Session ID、运行事件种类、`finish_reason`、最终响应长度等元信息，并对异常结束原因返回非零状态码。

这对最小 SDK 实验有帮助，但它没有自动核验两条 Bash 命令实际是否成功执行，更没有 JD 的统计契约和报告检查器。

所以必须增加一个 Runtime 之外的判断：**业务任务的成功条件是否满足。**

## 三、怎样把一句自然语言任务转为可以检查的完成条件？

任务是：

> 统计岗位职责或者任职要求出现 RAG 的岗位，相关技术要求是什么？

实现时会遇到几个口径问题：

- “出现 RAG”是字面命中，还是要求语义上确实开展 RAG 工作？
- `RAGFlow` 算不算出现 RAG？
- “无需 RAG 经验”在候选筛选中如何处理？它当然不应因此变成一项“必须掌握 RAG”的技术要求。
- “熟悉 Milvus 者优先”是否必须单列为优先要求？
- 记录同一 `job_id` 却来自不同采集批次时，哪一个版本用于统计？

如果这些规则在开始时没有明确，Checker 在结束时也无法凭空知道标准答案。

一份业务完成契约（Acceptance Contract）可以由用户约定的统计口径、输入数据版本、输出格式和可验证证据组成。

~~~yaml
# 教学示例；candidate_rule 尚待业务方确认，并非可运行配置
task_id: rag-requirements-demo
snapshot_id: fixed-redacted-jd-v1

candidate_fields:
  - responsibilities
  - requirements
candidate_rule: requires_explicit_definition
dedupe_key: job_id

requirement_labels:
  - required
  - preferred
  - unspecified

required_outputs:
  - report.md
  - job_status.jsonl
  - extractions.jsonl
  - validation.json

evidence:
  require_job_id: true
  require_source_field: true
  require_original_text: true
~~~

这里 `candidate_rule` 的示例值不是已确认的统计规则。它反而提醒读者：**未确认的口径应当暴露出来，不能在一份漂亮的配置文件里假装问题已经解决。**

### 完成契约和执行计划有什么区别？

在 02 中，Planning 回答“先处理哪些 JD，再做什么分析，最后怎样生成报告”。

完成契约则回答：

**达到什么条件，才允许宣布用户的任务已经完成？**

模型可以在不同 JD 之间调整处理顺序，但不能因此取消“区分必备和优先”“保留证据”和“按稳定职位 ID 去重”这些已确认的约束。

任务执行过程中若确实需要修改验收条件，应该由有权用户或业务控制器确认，而不是生成报告的模型自行降低标准。

## 四、第一道 Checker 为什么更适合用普通程序？

假设模型输出一条技术提取结果：

~~~json
{
  "job_id": "JD-001",
  "technology": "Milvus",
  "requirement": "required",
  "evidence": "有 Milvus 使用经验者优先",
  "source_field": "任职要求"
}
~~~

不调用第二次大模型，我们就可以验证很多事情：

1. `job_id` 是否真的属于本次固定快照。
2. `requirement` 是否属于允许的枚举。
3. `source_field` 是否属于本次规定的字段。
4. 证据句子能否在该职位的对应原文字段中定位。
5. 结果是否使用了唯一职位 ID。
6. 汇总报告里的分母和技术频次是否与明细一致。

这些属于**确定性检查**。它们可以用程序在同一份输入上稳定重跑，而无需让模型判断“这份报告看起来是否合理”。

| 检查关卡 | 业务问题 | 建议方法 |
| --- | --- | --- |
| 输入 | 是否用了指定的固定 JD 快照？ | 快照 ID 或内容摘要 |
| 候选 | 是否按确认的口径选全了职位？ | 程序独立计算并比较 ID 集合 |
| 去重 | 是否重复计入同一职位？ | 按稳定 `job_id` 约束唯一性 |
| 进度 | 每条候选 JD 是否已处理？ | 独立的职位处理状态表 |
| 结构 | 技术、分类、证据字段是否合法？ | JSON Schema、类型和枚举检查 |
| 证据 | 引文是否出现在正确 JD 字段？ | 原文定位 |
| 汇总 | 频次与分母是否等于明细的统计结果？ | 从结果表重新计算 |

一个简单的教学伪代码可以是：

~~~python
def check_report(contract, snapshot, job_status, extractions, report):
    # 教学伪代码：数据接口和业务规则尚未在 HarnessLab 实现
    expected = select_and_dedupe(snapshot, contract.candidate_rule)
    errors = []

    if set(job_status.keys()) != set(expected.keys()):
        errors.append("候选职位覆盖不完整或范围错误")

    for job_id, state in job_status.items():
        if state not in {"completed", "unresolved", "failed"}:
            errors.append(f"{job_id}: 未知处理状态")

    for row in extractions:
        if row["requirement"] not in {"required", "preferred", "unspecified"}:
            errors.append(f'{row["job_id"]}: 非法要求标签')
        if not evidence_in_original_field(row, snapshot):
            errors.append(f'{row["job_id"]}: 证据不能定位')

    if report.denominator != len(expected):
        errors.append("报告分母与候选职位数不一致")

    return {"passed": len(errors) == 0, "errors": errors}
~~~

这里有一个容易被忽略的设计问题：

**候选 JD 的完成状态不能只从“提取到了多少技术”反推。** 一条职位可能确实纳入了候选集合，但没有明确的技术要求，或者存在待复核表达。如果没有独立的 `job_status`，这条记录可能被误当成遗漏。

所以业务应用除了保存技术提取结果，还应该保存“每条候选职位是否完成分析、是否需要复核”的信息。

## 五、结构和证据都正确，为什么仍可能得出错误结论？

回到刚才的句子：

> 有 Milvus 使用经验者优先。

模型的结构化结果写成：

~~~json
{
  "job_id": "JD-001",
  "technology": "Milvus",
  "requirement": "required",
  "evidence": "有 Milvus 使用经验者优先"
}
~~~

字段合法、职位存在、原文也真实。所有格式检查都可能通过。

但 `required` 与“优先”冲突。这个问题已经不是检查 JSON 格式能解决的了，而是要理解自然语言的**条件性质**。

这是语义 Checker 应该承担的部分：

- 该技术在原文里是必备、加分，还是仅被提到？
- 引文能否支持结论？有没有遗漏否定词或限制条件？
- 原文是否表达得足够明确，能够给出确定分类？

| JD 原文 | 应重点判断什么 |
| --- | --- |
| 必须掌握 Python | 明确的必备要求 |
| 有 Milvus 经验者优先 | 明确的优先条件 |
| 负责 RAG 知识库建设 | 说明岗位职责，不代表全部 RAG 技术都为必备 |
| 了解 FAISS | 是否归为未明确或其他类别，取决于已确认口径 |
| 无需 RAG 项目经验 | 否定性质，不能当成必备经验 |

这里不能把表中所有例子直接写成统一的标准标签：有些用语的处理需要在任务契约里先明确。

### 再调用一个模型做 Checker，就能保证准确吗？

不能保证。

第二个模型可能重复第一次的错误，尤其是如果它只看到 Writer 自己总结的内容，而没有看到原始 JD。

如果需要模型复核，应让它看到**待审查的明确判断、完整必要原文、分类口径**，并要求指出证据与判断之间的具体对应关系。

存在语义争议、证据缺失或规则未定时，应该留下 `unresolved` 或 `needs_review` 状态，而不是通过不断重问使模型最终输出一个看似确定的答案。

**Checker 可以是普通程序、一次受约束的模型调用或人工复核，并不天然需要另一个 Checker Agent。**

## 六、Checker 应该在最后才运行，还是每个阶段都运行？

设想两种工作方式：

~~~text
方式 A：全部完成后统一检查

筛选 → 提取全部 JD → 汇总 → 生成 report.md → Checker
~~~

如果最后才发现候选范围错了，之前的提取可能白做；如果最后才发现“优先”被普遍写成“必备”，就需要追查整批结果。

另一种方式是：

~~~text
方式 B：关键阶段就设置验收边界

固定快照 → 筛选与去重 → 校验候选 ID 集合
                              ↓
逐批提取技术要求 → 校验结构、证据与条件性质
                              ↓
保存已验证结果 → 汇总计数并复核分母
                              ↓
生成 report.md → 验证报告与结果表一致
                              ↓
交付 / 局部修正 / 标记待复核
~~~

这样错误发生时，系统更容易知道是筛选错、模型理解错、证据错还是最后汇总错。

这与 01 的 Agent Loop 并不冲突：

- **内部 Agent Loop** 负责模型请求工具、接收反馈和继续行动。
- **外部业务 Checker** 负责阶段产物是否满足业务约束，并决定是否进入下一阶段。

如果某条 JD 的 `required / preferred` 判断被发现错误，可以只修正该职位的提取结果，而不是从头再跑完整任务。

但必须控制修正次数。如果相同证据反复产生冲突，或需要修改统计口径，应暂停或转人工，而不是无休止地调用模型。

**工具能连续执行不代表成果能自动自证正确，纠错循环也不能无限延长。**

## 七、哪些情况下可以交付，哪些必须停止或标记待复核？

当所有阶段都完成后，应用需要一个明确的交付决策，而不是等待模型说一句“我已经完成了”。

例如，可以由应用定义以下业务状态：

| 业务状态 | 成立条件示例 | 应向用户说明什么 |
| --- | --- | --- |
| `completed` | 所有必需关卡通过，产物与证据可回查 | 报告、范围、统计口径与产物路径 |
| `needs_review` | 有不能自动裁决的语义争议 | 哪些职位需要复核、为何无法确认 |
| `blocked` | 数据、授权、外部服务或口径缺失 | 阻塞原因及尚未完成的部分 |
| `failed` | 核查失败且不能在预算内修复 | 已完成内容、失败位置和证据 |
| `canceled` | 用户明确取消 | 已保存产物与未处理事项 |

**这些是业务层建议的状态，不是 DeepSeek Harness SDK `finish_reason` 的取值清单。**

比如 Runtime 返回 `completed`，但 Checker 发现报告使用了错误的统计分母，那么业务状态仍不能是 `completed`。

反过来，如果模型因输出 Token 上限结束，此前已经正确保存的部分 JD 提取结果仍然有价值，但不能因此宣称整项报告完成。

### 谁负责宣布真正完成？

最好由**拥有业务契约、数据快照和产物访问权的应用控制器**决定。

~~~python
# 教学伪代码：不是 DeepSeek Harness 原生的业务完成 API
run_result = run_research_agent(task)

if run_result.finish_reason != "completed":
    return mark_unfinished_from_runtime(run_result)

verification = verify_saved_outputs(task.contract)

if verification.passed:
    return mark_completed(verification)

if verification.requires_review:
    return mark_needs_review(verification)

if verification.retryable and task.has_remaining_budget:
    return repair_only_failed_stage(verification)

return mark_failed(verification)
~~~

实际实现还应考虑进程中断后已有文件、结果未知、工具已执行但成功事件尚未落盘等情况，分别由 05 的 State/Checkpoint 和 06 的故障恢复机制处理。

**模型可以生成候选产物和建议修正，但不能在没有授权的情况下改变验收条件，替自己宣布通过。**

## 八、DeepSeek Harness 有 Goal 功能，是否已经解决了“任务完成”问题？

这个问题容易把两个不同能力混在一起。

DeepSeek Harness 除了普通 Agent Loop，还有独立的 [Goal 能力组](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/goal/README.zh.md)：

- `dsh-goal`：保存一个会话中的长期目标及其 active、paused、blocked、complete 等状态。
- `dsh-tool-goal`：让模型通过工具操作 Goal。
- `dsh-goal-round-driver`：满足条件时自动安排后续 Round，让目标在多轮内继续推进。

这些组件主要解决的是**长期目标怎样保存、推进和停止**。

[Goal Round Driver 官方文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/goal/goal-round-driver/README.zh.md) 还明确说明：该驱动器**没有独立的结果评估器**。它可以管理轮次上限、继续与停止条件，但并不会自动核验 JD 分母、Milvus 标签和引用证据。

因此，Goal 标记为 `complete`，不直接等于我们这份统计报告通过了业务 Checker。

而且 [`sdk-minimal` Profile 的配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) **没有默认装配 `dsh-goal`、`dsh-tool-goal` 与 `dsh-goal-round-driver`**。当前 Phase 0 不应该被描述成已经拥有长期 Goal 调度。

可以把它们区分为：

~~~text
Agent Loop：本轮模型与工具活动为何结束？
                ↓
可选 Goal：长期目标如何记录、继续、暂停和结束？
                ↓
业务 Checker：当前实际产物满足了哪些验收要求？
                ↓
应用：允许交付、局部修正，还是标记失败？
~~~

这是一张**层次关系图，不是每一个 Agent 都必须执行的四步流水线**。

对当前 JD Research Agent，我们可以先由外部 Workflow 管理阶段、由 Checker 验证结果。只有确实存在跨多轮自主推进的需要时，再评估可选 Goal 组件的价值。

## 九、要证明任务完成，为什么不能只保存最终回答？

假设 Checker 发现一项错误：

> `report.md` 将 Milvus 统计为 required，但原 JD 写的是“Milvus 经验优先”。

如果只能看到报告里一句“Milvus 是必备技术”，我们不知道错误在哪里产生。

理想情况下，应能沿着以下关系回查：

~~~text
报告结论：Milvus / required
             ↓
结构化结果：JD-001 / Milvus / required
             ↓
原文证据：有 Milvus 使用经验者优先
             ↓
固定输入快照与分类口径
             ↓
模型处理与工具执行记录
~~~

每一层都是不同的证据：

| 证据 | 主要证明什么 |
| --- | --- |
| 快照 ID、字段范围和职位数量 | 分析对象是什么 |
| 候选职位 ID 与去重清单 | 统计分母能否成立 |
| 逐职位处理状态 | 是否有遗漏、失败或待复核 |
| 技术提取记录与标签 | 哪些判断参与了统计 |
| 原文字段、证据摘录和定位 | 判断是否有原文支持 |
| `report.md` 及校验结果 | 报告与底层数据是否一致 |
| Session、工具调用与模型请求轨迹 | 系统怎样产生了这些判断 |

**Session 记录适合解释“怎么执行”，业务数据与原文证据才是判断“结果是否可靠”的重要基础。**

例如 Session 中模型声称“已分析全部候选岗位”，也不等于实际处理状态表已经覆盖全部候选 ID。

注意保留证据并不意味着无限制保存敏感信息：真实业务应依照授权和脱敏要求记录必要内容。本篇始终使用固定、脱敏的教学快照。

## 十、怎样为“任务完成”建立第一个可运行的验证实验？

根据 [学习路线阶段 3 和阶段 8](./LEARNING_PATH.md)，建议先用一份小型、固定、可人工核对的 JD 快照，把**一项研究任务的验收**做扎实，再考虑更完整的端到端评测。

### 1. 最小样本需要覆盖什么？

至少包含这些有区分价值的情况：

- 明确的必备：例如“必须掌握 Python”。
- 明确的优先：例如“Milvus 使用经验优先”。
- 技术被提及，但要求性质不明确。
- 否定表述、条件冲突或字段缺失。
- 重复 `job_id`、不同版本、证据无法定位。
- 一条候选岗位没有可抽取的具体技术，但已经真实处理完成。

样本大小不必因“需要完整 RAG 流程”就机械规定为某个数量；最初的目标是能够**人工逐条核对验收规则**，随后再扩大覆盖范围。

对于口径尚无一致答案的样本，应保存争议，而不能为了形成“标准答案”强制给出唯一标签。

### 2. 比较没有 Checker 与有 Checker

~~~text
方案 A：
固定快照 → 模型提取 → 汇总 → report.md → 直接交付

方案 B：
固定快照 → 模型提取 → 分阶段程序校验
                              ↓
                    必要的语义复核
                              ↓
                      有限次局部修正
                              ↓
                    重新校验并决定交付
~~~

比较两种方案时，需要观察：

1. 基础方案出现了哪些真实错误：错分必备/优先、漏职位、错分母、错误证据等。
2. Checker 实际发现了多少错误，是否还把正确结果误判为错误。
3. 修正是否减少了错误，还是引入了新的误改。
4. 额外增加了多少模型请求、时间与人工复核工作。
5. 不确定样本是否得到正确标注，而非被强制判定为通过。

这些是未来需要运行的实验，不是本文已经取得的性能结论。

### 3. 为什么不能只比较最终报告的答案？

假设两次运行都输出“Milvus 出现 10 次”。

第一次可能完整分析了所有候选 JD，第二次可能漏处理了若干职位，却恰巧也得到 10。

**相同的最终数字不代表相同的任务完成程度。** 只有查分母、候选 ID、原文证据及处理状态，才能解释这个数字是否可信。

至此，本篇完成了“**单项任务的交付条件怎样定义和验证**”的核心目标。

后续 [10 · 端到端评测与优化](./LEARNING_PATH.md) 再深入跨样本评测、误差归因、任务成功率、运行轨迹与持续改进，不在这里重复完整评测体系。

## 十一、DeepSeek Harness 已经提供什么，新 Agent 又要自己做什么？

| 事情 | DeepSeek Harness / 当前 Phase 0 | 新 JD Agent 的责任 |
| --- | --- | --- |
| 结束当前模型—工具循环 | Agent Loop 已实现，SDK 有 `finish_reason` | 不把 Runtime `completed` 当成业务通过 |
| 工具调用与 Session 记录 | 提供执行流水线、事件与持久化 | 关联任务 ID、职位 ID、快照与业务结果 |
| 初步运行状态 | Phase 0 已记录会话 ID、事件种类、结束原因等 | 补充报告、处理状态和独立验收记录 |
| 长期 Goal | 框架有可选插件；`sdk-minimal` 未默认装配 | 按跨轮任务需要决定是否引入 |
| 固定验收契约 | 不自动提供岗位统计口径 | 明确候选规则、去重、分母及交付要求 |
| 确定性 Checker | 可由应用直接编写程序 | 检查结构、原文定位、覆盖率与计算 |
| 语义 Checker | 可以复用模型与工具机制 | 设计证据复核、争议分类和人工升级 |
| 修正与停止 | Runtime 有基础结束及失败机制 | 按业务验收反馈进行有限修正或明确失败 |
| 最终完成 | 框架不能自动证明 JD 报告满足业务要求 | 由应用根据实际结果和契约决定交付 |

这张表表达了整个学习路线到 08 的核心边界：

**Harness 已实现模型调用、工具执行和运行结束；我们仍要让 Agent 的业务结果成为可验收的工作成果。**

## 十二、这一篇应该真正理解什么？

最初我们只看到一个事实：`report.md` 已经生成。

沿着任务要求检查后，才发现“文件有了”与“统计做对了”之间隔着几层必要的工作：

~~~text
用户提出任务
       ↓
应用明确数据范围、统计口径与完成条件
       ↓
Agent / Workflow 执行研究工作
       ↓
程序与必要的语义 Checker 检查阶段产物
       ↓
保存可回查的结果、原文证据与验收记录
       ↓
对照完成条件
   ├─ 通过 → 交付报告
   ├─ 可修正 → 局部修正并有限次复验
   ├─ 存在争议 → 标记待复核
   └─ 无法继续 → 如实说明阻塞、失败或取消
~~~

最重要的三个区别是：

**第一，`finish_reason="completed"` 表示 Runtime 的执行结束，不表示用户要求的工作已经正确完成。**

**第二，Checker 不需要必然成为另一位 Agent。** 能用规则确定的内容由程序核验，需要理解自然语言和证据的部分再引入模型或人工。

**第三，任务完成不能由模型自己宣布。** 它应该由事先约定的任务要求、真实产物和可回查证据共同支持。

对于 JD Research Agent，下一步最有价值的实现不一定是更多智能体，而是：**确认候选筛选和去重口径、保存每条职位的处理状态与证据、增加程序 Checker，并将最终交付与验收结果绑定**。

本篇到此完成。下一篇 [09 · 部署与服务化](./09-deployment-and-serving.md) 将讨论如何将本地应用部署成可服务多用户的系统；10 再进一步研究端到端评测与持续优化。

## 参考阅读

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop](./01-agent-loop-execution-mechanism.md)
- [02 · Workflow、Planning 与 Multi-Agent](./02-workflow-planning-multi-agent.md)
- [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)
- [04 · Context Engineering](./04-context-engineering.md)
- [05 · State、Session、Checkpoint](./05-state-session-checkpoint.md)
- [06 · 执行控制与故障恢复](./06-execution-control-and-failure-recovery.md)
- [07 · 权限、Sandbox 与人工审批](./07-permissions-sandbox-human-approval.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [Phase 0 Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py)
- [DeepSeek Harness · Python SDK `RunResult`](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)
- [DeepSeek Harness · Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md)
- [DeepSeek Harness · ReactLoopAgent 源码](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts)
- [DeepSeek Harness · Goal 能力组](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/goal/README.zh.md)
- [DeepSeek Harness · Goal Round Driver](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/goal/goal-round-driver/README.zh.md)
- [DeepSeek Harness · sdk-minimal Profile](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/README.zh.md)
