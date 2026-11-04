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

