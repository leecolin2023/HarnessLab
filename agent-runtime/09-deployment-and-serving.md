# 09 · 部署与服务化：一个本地 Agent 怎样同时为多个用户工作？

> **学习目标**：理解本地 SDK 运行脚本和持续在线的 Agent 服务之间的差别。能够从一次用户提交出发，追踪 HTTP 请求、业务任务、队列、Worker、Runtime 进程、Session 和报告产物的关系，并解释如何控制并发、隔离、恢复与交付。
>
> **贯穿任务**：用户提交一个 JD 研究任务：基于固定脱敏快照，统计岗位职责或任职要求涉及 RAG 的职位，区分技术的 required、preferred 与 unspecified，生成带职位证据的报告。现在要求两个用户可以各自提交任务、查询状态、取得自己的结果，互不干扰。
>
> **承接关系**：[05 · State、Session、Checkpoint](./05-state-session-checkpoint.md) 解决怎样恢复；[06 · 执行控制与故障恢复](./06-execution-control-and-failure-recovery.md) 解决怎样避免错误重试；[07 · 权限、Sandbox 与人工审批](./07-permissions-sandbox-human-approval.md) 解决允许做什么；[08 · 任务验证与结束条件](./08-task-verification-and-completion.md) 解决怎样判定业务成功。本篇把这些机制放进**一个可持续接受任务的服务**。
>
> **实现边界**：当前 [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md) 是 Docker 中运行一次任务的最小实验，尚未提供 HTTP 接口、任务队列、多租户鉴权或并发服务。本篇的接口、代码和架构是下一阶段设计示例，不是仓库已实现或压力测试通过的产品。

## 一、现在已经能运行 Agent，为什么还不能让别人直接调用？

在 Phase 0，我们用命令启动一次任务：

~~~bash
bash scripts/run-docker.sh run
~~~

脚本准备隔离目录、启动容器，容器中 Python 代码使用：

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

这里的 `harness.run(...)` 可以启动一次 Agent 工作，取得 `session_id`、`finish_reason`、`final_response` 等结果。

现在假设我们给其他人提供一个网页，让他们点击“分析 RAG 岗位”，后台直接运行这个脚本。会遇到哪些实际问题？

第一位用户提交任务后，Agent 可能需要分析几百条 JD，等待若干次模型和工具调用。第二位用户此时也提交任务，Web 服务是否要等待第一个任务结束？

如果用户关闭浏览器，已经启动的 Agent 应不应该停止？

如果服务重启，用户还能否看到刚才任务的进度和已有结果？

如果两人的 Session ID、目录或报告文件共用同一位置，会不会把报告交错覆盖，甚至把另一个人的业务数据带入模型上下文？

**本地脚本能够完成一次工作，与在线服务能够持续、安全地接受很多次工作，是两种不同的能力。**

因此，服务化的第一步不是直接给 `harness.run()` 外面套一个 HTTP 路由，而是区分“用户的一次请求”和“可能运行很久的一项任务”。

## 二、用户发出一个 HTTP 请求，任务要运行几分钟，应该怎么返回？

设想一个简单接口：

~~~http
POST /v1/tasks
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "dataset_id": "redacted-jd-v1",
  "rule_id": "rag-requirements-v1"
}
~~~

Web API 首先确认请求身份与数据访问权限，然后创建一个稳定任务记录。

一种更合适的返回方式是：

~~~http
HTTP/1.1 202 Accepted
Location: /v1/tasks/task-001
Content-Type: application/json

{
  "task_id": "task-001",
  "status": "queued"
}
~~~

这段是**设计中的 API 契约**，不是 HarnessLab 已启动的真实服务。返回 `202 Accepted` 的意思是服务**接受了处理请求**，而不是 JD 分析已经完成。

用户以后可以查询：

~~~http
GET /v1/tasks/task-001
Authorization: Bearer <access-token>
~~~

服务器在检查请求身份与任务归属后返回：

~~~json
{
  "task_id": "task-001",
  "status": "running",
  "progress": {
    "processed": 80,
    "total": 120
  },
  "report_ready": false
}
~~~

只有 `processed` 和 `total` 来自真实业务状态时，才能提供这样的进度；如果系统当前只有模型输出文本，就不应凭空显示“已处理 80/120”。

为什么不让初始 HTTP 请求一直等待到报告生成？

因为 HTTP 连接的存活时间和 Agent 任务生命周期并不相同：浏览器可能断开、代理可能超时、客户端可能重试。**连接结束不应该自动被解释成业务任务失败，也不能只凭连接还在就判定任务正在正确执行。**

当然，如果某项任务确实只需要很短时间，同步请求也可能合理。本篇选择异步任务模型，是因为我们研究的是可持续执行、可能需要恢复和验证的 JD 分析任务。

## 三、`task_id`、`session_id` 和 Runtime 进程，为什么不能混成一个编号？

我们已经有 `session_id`，为什么还要创建 `task_id`？

因为它们分别描述不同对象。

| 对象 | 代表什么 | 谁负责维护 |
| --- | --- | --- |
| HTTP Request ID | 客户端与服务一次交互 | Web API / 网关 |
| `task_id` | 一项待完成的业务工作及其状态 | 业务任务系统 |
| `session_id` | DeepSeek Harness 的会话身份及历史 | Runtime / Session 持久化 |
| Worker ID | 哪个工作进程当前承接任务 | 调度与执行平台 |
| Runtime 进程 | 真正承载 SDK、模型请求与工具的运行实例 | SDK 包装层 / Worker |
| 结果 ID / 路径 | 最终报告、结构化结果及证据 | 业务结果存储 |

例如，用户提交 `task-001`，应用创建 `session-xyz` 并记录映射。Worker 在运行到一半时崩溃，任务仍然应该存在，稍后由另一个可用 Worker 根据已保存的业务 State 决定如何恢复。

恢复时可能沿用旧 Session，也可能因历史不可用而开一个新 Session 续做剩余阶段。**同一业务任务不必天然等于一个永不改变的 Session 或操作系统进程。**

反过来，一条 Session 也可能接收多次用户输入；不能把每次 SDK 调用都当成新的业务任务。

应用至少应该保存这种关联：

~~~text
task_id: task-001
owner_id: user-a
dataset_version: redacted-jd-v1
rule_version: rag-requirements-v1
business_status: running
session_id: session-xyz
worker_lease: worker-2 / expires_at
output_manifest: outputs/task-001/manifest.json
~~~

其中 `worker_lease` 是业务调度器的示意字段，不是 DeepSeek Harness SDK 自带的数据结构。

这里还需要一项重要约束：**Session ID 不应该由外部用户随便指定，就允许访问与之对应的历史**。应用必须用自己的任务归属和授权规则做映射与核查。

## 四、业务任务交给谁执行？为什么引入 Queue 与 Worker？

如果 HTTP 服务自己在请求处理线程里运行所有 Agent 工作，一旦用户同时提交多项长任务，Web 服务就可能长时间被占用。

可以把接收请求与执行任务分开：

~~~text
用户 A / 用户 B
       ↓
   受控 HTTP API
       ↓
身份鉴别、参数校验、任务授权
       ↓
写入持久化任务记录
       ↓
   有界任务队列
       ↓
 ┌───────────┬───────────┐
 │ Worker 1  │ Worker 2  │
 │ Runtime A │ Runtime B │
 └───────────┴───────────┘
       ↓
  业务状态与产物存储
       ↓
 API 查询状态 / 下载结果
~~~

这是一个**建议的最小服务架构**。这里的 Worker 是运行任务的业务执行进程或容器；它不要求我们自研 DeepSeek Harness 的内部 Agent Loop。

### 为什么任务状态要先持久化？

假设 API 返回 `202 Accepted`，但任务只在 Web 进程内存中排队。服务重启后，这项任务可能直接消失。

因此，接受请求应当建立可恢复的持久记录。队列和任务表可以用同一个事务系统，也可以使用消息队列搭配数据库；重要的是让“已接受但未执行”“正在执行”“已完成”能够在重启后核查。

不要把“消息成功入队”当作“任务已完成”。更不能只依赖队列里的消息保存最终报告。

### 谁决定下一项任务可以启动？

由业务调度器控制，包括：

- Worker 当前是否空闲；
- 同一用户是否达到并行任务上限；
- 系统整体模型请求、CPU、内存和网络预算是否允许；
- 任务需要何种数据权限和运行环境；
- 是否已有另一个 Worker 正在处理同一任务。

Agent 可以在任务内部调用多个工具，但**它不应该越过业务队列，自行获得无限数量的执行实例**。

## 五、同一台机器同时运行十个 Agent，是十个 Session，还是十个 Runtime？

这要分清几种“并发”。

### 1. HTTP 并发

同时有 100 个用户访问状态接口，不代表有 100 个模型正在推理。大量查询只是读取任务表。

### 2. 任务并发

同时有 10 个 JD 分析任务处于 `running`。它们可能分配给 10 个 Worker，也可能被少量 Worker 按容量调度。

### 3. Session 并发

每项任务可能拥有独立 Session，但 Session 是执行历史与状态的边界，并不是独立的安全容器或独占模型实例。

### 4. Runtime 进程并发

每个 Worker 可以启动一个 SDK Runtime 子进程；也可以考虑复用一个可管理多个会话的 Runtime。进程复用方式将影响启动成本、隔离、故障传播和资源管理。

### 5. 模型服务并发

这些任务可能同时向同一个模型 API 发送请求。真正的模型吞吐、提供方限流、排队与费用，不由 `session_id` 的数量直接决定。

### 6. 单任务内部工具并发

一个 Agent 也可能同时查询若干 JD。这又是一层独立的并发控制，不能和“服务器接收十个任务”混为一谈。

**并发的层次不同，限流点也不同。** 增加 HTTP Worker 并不会自动提高模型服务容量；提高工具并发也不表示可以无限创建 SDK 进程。

## 六、DeepSeek Harness 的 Python SDK 到底启动什么？能不能直接作为 Web 服务？

根据 [DeepSeek Harness Python SDK 官方文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)，Python SDK 会通过 **stdio 上的按行分隔 JSON-RPC** 驱动本地 `dsh` Runtime 子进程。

它并不是一个已经对外提供多租户 HTTP API 的托管服务。

~~~text
我们的 Python 应用 / Worker
           ↓
DeepSeekHarness Python SDK
           ↓  stdio JSON-RPC
       dsh Runtime 子进程
           ↓
     Agent Loop / Session
           ↓
      模型请求与工具执行
~~~

官方 SDK 还说明：

- `DeepSeekHarness` 在首次需要时启动 Runtime，直到 `close()` 或上下文管理器退出才结束，进程在此期间可复用。
- `Session.run()` 等待当前输入对应的 Agent 活动到达下一次空闲边界，返回包含会话 ID、最终文本、结束原因与事件的 `RunResult`。
- SDK 支持多个调用重叠，但它并不替应用定义跨用户业务隔离和调度策略。
- `request_timeout_seconds` 限制的是协议响应等待，不是之后可能持续运行的完整任务时间。
- `resume_session(id)` 可以尝试恢复持久化会话，但不恢复 Shell、浏览器等外部进程。

这解释了一个常见误解：

> “SDK 已支持并发调用，所以我直接用一个全局 SDK 对象服务所有用户就行。”

**并发调用能力不等于多租户安全模型。** 一个 Runtime 进程可以共享其工具提供方、环境、凭据或其他进程级资源；仅靠 Session ID 不足以证明用户之间已经隔离。

### 最小版本应该怎样选？

对于最早期的**受控、低并发、内部教学环境**，更容易说明边界的方案是：

~~~text
一项业务任务
    ↓
一个受控 Worker / 容器
    ↓
一个 SDK Runtime 实例及其限定的工作区
    ↓
专属 Session 与业务输出目录
    ↓
完成后清理运行环境，保留需要的日志与结果
~~~

这并不是性能最优架构，而是**隔离和故障归属较容易验证的起点**。

当我们掌握了任务运行时长、内存、模型调用量、Worker 启动耗时和资源峰值，才有充分依据考虑 Runtime 复用池。

### 进程池一定能节省更多资源吗？

未必。复用进程可能减少启动和初始化开销，但也增加进程内状态、Session 绑定、工具资源泄漏、故障传播和不同任务互相影响的管理复杂性。

尤其如果某个 Runtime 加载了高权限 Shell、数据库凭据或不同用户的工具作用域，简单把它们混入一个进程可能扩大风险。

因此可以把演进理解为：

**先验证单任务隔离；再测量开销；最后决定是提高单实例复用，还是增加可隔离的 Worker 副本。**

## 七、两个用户同时执行任务，究竟要隔离什么？

假设用户 A 和用户 B 各提交一项 JD 研究任务。

如果 A 的任务只是读取 A 有权限的数据，B 的任务却能通过一个 `get_job` 工具读取 A 的快照，那么即使两人有不同的 Session ID，系统仍存在越权。

多用户隔离至少包括以下几个方面：

| 隔离对象 | 应保证什么 |
| --- | --- |
| 任务所有权 | 用户只能查询、取消或下载自己有权访问的任务 |
| 输入数据 | 业务工具按已认证身份检查快照和职位范围 |
| Session | 不因用户提交或猜中 Session ID 而读取其他会话 |
| 工作目录 | 工具执行时不能访问其他任务的文件 |
| 输出产物 | 报告路径和下载权限绑定任务归属 |
| 凭据 | 不让所有任务共享无差别的高权限密钥 |
| 资源配额 | 单个用户或任务不能耗尽整个服务的执行容量 |

特别要注意：**不同路径不自动意味着真正的访问隔离**。

如果两个任务运行在同一个具有完整文件权限的进程里，仅把工作目录设成两个不同 `cwd`，并不能阻止一个 Shell 去读另一个目录。

正如 [07 专题](./07-permissions-sandbox-human-approval.md) 已核实的，当前 `sdk-minimal` 是 `danger-full-access` 策略；真正的隔离主要依靠外层执行环境。Phase 0 的 Docker 默认 bridge 网络还允许出站，模型测试 Key 通过环境变量进入容器。

所以服务化时不仅要隔离业务路径，还要确认容器挂载、进程身份、网络出口、工具范围和凭据分发。**不要把 Phase 0 的教学容器直接公开为承载真实银行数据的生产服务。**

## 八、任务运行了一半，Worker 崩溃，服务要怎样继续？

这时前面 05、06 的知识就开始发挥作用。

设想：

~~~text
Task task-001 状态：running
Worker-1 正在处理 JD-081
              ↓
Worker-1 崩溃 / 被平台终止
              ↓
租约过期，调度器发现任务没有活跃执行者
              ↓
核查已保存的业务 State 与真实结果
              ↓
确定哪些职位已完成、哪些结果未知
              ↓
新的 Worker 接管未完成部分
~~~

这里的 **Lease（租约）** 是一种业务调度设计：Worker 获得任务执行权，在有效期内负责该任务；如果不再续约，调度器可以判定需要恢复核查。

但**租约过期本身不证明旧 Worker 一定已停止**。在网络分区或进程卡住的情况下，旧 Worker 可能仍然执行外部操作。

因此，恢复还需要：

- 针对同一任务防止两个 Worker 同时写最终报告的并发控制；
- 使用稳定业务键实现幂等保存；
- 对结果未知的工具调用先核查外部副作用；
- 对数据快照、规则版本和已经保存的 JD 结果进行一致性验证。

恢复旧 Session 时应使用 SDK 的真实恢复接口；但即使 Session 可以恢复，也不能依赖它替代业务状态。

### 服务重启为什么不等于任务要从零重跑？

因为任务表、原始快照与已验证结果应保存在容器之外的持久数据存储中。

如果所有进度只放在 Worker 的内存里，服务重启就会丢失任务事实；如果结果都保存在明确的业务 Store 中，新的 Worker 可以依据已核查的结果继续。

这个机制主要属于应用的**任务编排与存储设计**，而非必须修改 DeepSeek Harness 的 Agent Loop 内核。

## 九、什么时候需要把执行进度实时推给用户？

一个长任务如果只显示“处理中”，用户可能不知道服务是否还在运行。

我们可以在任务页展示已核实的状态，例如：

~~~text
任务 task-001
状态：running
固定数据快照：redacted-jd-v1
候选职位：120
已完成并验证：80
待复核：3
最新阶段：校验技术要求
~~~

但是，展示进度至少要区分两个来源：

**业务进度**：真正被保存、校验通过的职位处理数量和阶段状态。

**运行事件**：模型正在调用工具、生成内容、等待审批或处理错误。

运行事件可以通过轮询、SSE 或 WebSocket 及时展示；它们不等于已经提交的业务成果。

例如模型流式输出“已经找到了很多岗位”不能直接算成 `processed=80`。业务进度应由真实结果表或明确的阶段事件产生。

### 什么时候用 SSE / WebSocket？

如果只是提交任务、查看状态、下载报告，简单的 `POST / GET` 加定期轮询已经可以工作。

只有需要实时观察工具步骤、模型输出或人机交互时，再考虑 SSE 或 WebSocket。增加实时传输后，还要处理网络断开、事件重连、权限验证及敏感信息脱敏。

**实时展示不是第一阶段的必要条件，稳定状态和正确报告才是。**

## 十、API 的成功返回应该代表什么？怎样避免混淆三个状态？

我们已经在 08 讨论过：`finish_reason="completed"` 不代表业务验收通过。

服务化后又增加一层 HTTP 成功：

~~~text
HTTP 请求成功
     ≠
Runtime 本轮正常结束
     ≠
业务任务经验证完成
~~~

因此，API 契约应分别表达：

- `POST /v1/tasks` 返回 `202 Accepted`：任务已被接收并持久登记。
- `GET /v1/tasks/{id}` 返回 `queued` / `running` / `needs_review` / `completed` / `failed` 等**业务任务状态**。
- `GET /v1/tasks/{id}/report`：只有有权用户可以取得相应产物；如果报告尚未就绪，不能返回虚假的完成文档。

例如，Runtime 返回 `completed`，但 Checker 发现“Milvus 经验优先”被归类为必备，那么任务状态应该是需要修正或复核，而不是 `completed`。

这样前端、API、Worker、Runtime 都可以各自拥有明确的成功判据，避免错误的状态向上层传播。

## 十一、一个可执行的最小服务化方案应该怎样逐步搭建？

不要一开始就采购复杂的微服务与分布式平台。先把一个 **单机、低并发、受控内部服务** 跑通，再看哪里需要拆分。

### 第一阶段：用业务 API 管理任务

定义：

~~~text
POST /v1/tasks              提交一项 JD 研究任务
GET  /v1/tasks/{task_id}    查询任务状态
GET  /v1/tasks/{task_id}/report  获取报告
POST /v1/tasks/{task_id}/cancel  请求取消
~~~

每个端点都必须鉴权并检查任务归属，不能只凭 URL 中的 `task_id` 放行。

提交接口应校验输入数据快照、规则版本、幂等键以及用户配额。重复提交同一业务意图如何处理，需要在 API 契约中定义。

### 第二阶段：用最小任务表与 Worker 执行

例如：

~~~python
# 机制伪代码：不是当前仓库的可运行服务代码
def submit_task(principal, request):
    authorize_dataset(principal, request.dataset_id)
    task = create_durable_task(
        owner_id=principal.id,
        snapshot=request.dataset_id,
        rules=request.rule_id,
        idempotency_key=request.idempotency_key,
    )
    enqueue_or_make_claimable(task.id)
    return {"task_id": task.id, "status": task.status}

def worker_once():
    task = claim_next_task_with_lease()
    if task is None:
        return
    try:
        run_in_isolated_runtime(task)
        verify_saved_artifacts(task)
        finalize_task_if_lease_still_valid(task)
    except Exception as exc:
        record_failure_without_assuming_no_side_effects(task, exc)
    finally:
        release_owned_resources(task)
~~~

这里的 `claim_next_task_with_lease`、`run_in_isolated_runtime`、`verify_saved_artifacts` 代表不同职责，不是 DeepSeek Harness SDK 的原生方法。

尤其是调用 `run_in_isolated_runtime` 时，Worker 应根据任务的已认证身份生成受限工作区与工具配置，而不是把用户输入的任意 Shell 命令交给高权限 `sdk-minimal`。

### 第三阶段：保存业务 State 与产物

持久保存：

- `task_id`、`owner_id`、快照 ID、规则版本；
- Session ID 和必要的恢复定位信息；
- 已处理职位、待核查项、报告位置及内容校验信息；
- 明确的业务状态及时间记录；
- 安全审计所需的结构化事件，而非无限制保存所有原始 Prompt。

### 第四阶段：验收两个用户同时使用

让两个模拟用户分别提交受控任务，观察它们是否具有独立的任务记录、Session、工作目录、结果和访问授权。

测试中断后是否仍然可以查询任务，是否出现重复执行或产物覆盖。若任意隔离失败，应当先修复权限边界，不是靠提高 Worker 数量绕过去。

## 十二、什么时候才值得扩展容量和做 AgentOps？

单机任务跑通后，才有必要分析容量问题。

常见瓶颈可能在不同位置：

| 观察到的现象 | 可能首先需要研究的环节 |
| --- | --- |
| 很多任务排队，Worker 空闲 | 任务领取与调度问题 |
| Worker 总是满载，模型请求等待 | Worker 容量与外部模型配额 |
| 相同 JD 被反复读取和分析 | 数据缓存、去重与业务流程 |
| 创建容器和 Runtime 很慢 | 启动成本与可控复用 |
| 工作内存持续增长 | Runtime 生命周期与资源泄漏 |
| 用户只能看到 HTTP 200 | 业务状态、报告验收与可观测性不足 |
| 重启后出现重复报告 | 租约、幂等写入与业务恢复问题 |

**不能仅凭“同时运行十个 Agent”判断系统容量。** 请求数量、Agent Step、模型调用、Token 使用、工具 I/O、Session 大小和业务验收耗时都可能构成不同的限制。

本篇所说的 AgentOps，并不是要求先搭建一套全新的平台，而是从现实运行中记录足以定位问题的最少信息：

- 每个任务的创建、领取、开始、完成、失败与取消时间；
- 每个 Worker 的活动任务数量与资源使用；
- 每个任务的模型请求次数、Token、延迟、工具错误与重试；
- Session 与业务任务的关联及异常恢复情况；
- 业务 Checker 是否通过、哪些职位仍需人工复核；
- 每项调用的授权主体及必要的操作审计。

同时区分**任务级监控**与**模型服务监控**：模型 API 吞吐高不代表 JD 报告合格，任务最终成功率也不能说明哪个模型调用最慢。

更复杂的弹性扩容、分布式调度、成本归因和系统级质量评测，可以在有了真实负载后逐步增加。

## 十三、哪些由 DeepSeek Harness 提供，哪些必须由新服务实现？

| 能力 | DeepSeek Harness / 当前 Phase 0 | JD 服务还需要负责 |
| --- | --- | --- |
| 模型与工具执行循环 | Harness 已实现 | 不重写 Runtime 内核 |
| Python 调用入口 | `DeepSeekHarness` 管理本地 Runtime 子进程 | 用 Worker 可靠启动、关闭与回收 |
| Session | 创建、运行、持久化和恢复的基础机制 | 绑定真实业务任务与访问主体 |
| SDK 调用重叠 | 文档允许调用重叠 | 不能等同于多租户安全、无限并发 |
| 单任务工作区 | Phase 0 提供独立工作区与外层 Docker 约束 | 每用户/任务建立可验证的资源边界 |
| HTTP API 与认证 | Python SDK 不提供业务 HTTP 服务 | 任务提交、鉴权、归属校验、查询与下载 |
| 排队与调度 | 不是 `sdk-minimal` 的业务能力 | 任务队列、Worker、配额、租约与并发控制 |
| 业务进度与产物 | Session 日志不等于职位统计 State | 业务结果表、报告存储与进度查询 |
| 中断恢复 | 提供 `resume_session` 等机制 | 核查外部副作用并按业务 State 续跑 |
| 任务完成 | Runtime 返回结束原因 | 独立验收报告、证据与统计分母 |
| 服务运营 | 运行事件可供应用观察 | 健康检查、访问控制、监控与容量规划 |

所以这一篇最重要的工程边界是：

**DeepSeek Harness 负责让 Agent 能够决策、调用工具、保存会话并继续运行；业务服务负责让很多用户能够受控地提交、管理和取得这些工作成果。**

## 十四、读完之后，应该能够解释什么？

从一个本地 `harness.run(...)` 开始，真正的服务化不是简单多加一个 HTTP 路由，而是形成这条链：

~~~text
用户提交有权限的研究请求
             ↓
API 验证身份、任务参数与配额
             ↓
持久创建业务任务并返回 task_id
             ↓
调度器按容量把任务交给 Worker
             ↓
Worker 在隔离环境启动/复用适合的 Runtime
             ↓
Agent 使用模型和工具处理真实 JD
             ↓
业务 State、原文证据和报告持续保存
             ↓
Checker 验收，决定业务完成或待复核
             ↓
用户通过任务 ID 查询与领取自己的结果
~~~

在这里：

- **HTTP 请求**只是提交或查询工作的入口；
- **Task** 是可管理、可恢复的业务工作；
- **Session** 是 Harness 的会话历史与执行边界；
- **Runtime** 是承载 Agent Loop 与工具的实际运行实例；
- **Worker / Queue** 控制何时执行、能同时执行多少以及由谁接管；
- **业务 State 与验收**决定用户真正得到的结果。

这几个对象的生命周期不相同，不能因为它们在第一版脚本中恰好一起开始、一起结束，就把它们设计成同一个东西。

对当前 JD Research Agent，最合适的下一步是**先建立一个受控、低并发的 HTTP 任务入口和可持久恢复的 Worker**，而不是急着搭建复杂的多 Agent 平台或高并发调度系统。

后续 [10 · 端到端评测与优化](./LEARNING_PATH.md) 将研究如何用任务结果与实际运行轨迹改进整条系统链路，本篇不提前展开完整评测设计。

## 参考阅读

- [00 · Agent 与 Runtime](./README.md)
- [01 · Agent Loop 的运行机制](./01-agent-loop-execution-mechanism.md)
- [03 · Tool Calling 与 MCP](./03-tool-calling-and-mcp.md)
- [05 · State、Session、Checkpoint](./05-state-session-checkpoint.md)
- [06 · 执行控制与故障恢复](./06-execution-control-and-failure-recovery.md)
- [07 · 权限、Sandbox 与人工审批](./07-permissions-sandbox-human-approval.md)
- [08 · 任务验证与结束条件](./08-task-verification-and-completion.md)
- [Agent Runtime 学习路线](./LEARNING_PATH.md)
- [HarnessLab Phase 0](./labs/sdk-minimal-phase0/README.md)
- [Phase 0 Python 入口](./labs/sdk-minimal-phase0/src/run_phase0.py)
- [Phase 0 Docker 运行脚本](./labs/sdk-minimal-phase0/scripts/run-docker.sh)
- [DeepSeek Harness · Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.zh.md)
- [DeepSeek Harness · sdk-minimal Profile](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/README.zh.md)
- [DeepSeek Harness · Agent Loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.zh.md)
- [DeepSeek Harness · Session 持久化](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-persistence-jsonl/README.zh.md)
- [OWASP · API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
