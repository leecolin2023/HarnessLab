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

