# 01｜读懂 job-agent：项目整体架构与核心代码

> 本文研究对象：[job-agent](https://github.com/leecolin2023/job-agent)（基准提交 `70326a48b85ef813642f8e5298f44465fa98166e`）。  
> 本文属于 HarnessLab 的**代码阅读与机制理解**材料，工程源码继续留在 job-agent，不在这里复制维护。  
> 阅读目标：先把 [Agent Runtime 的基本执行循环与复杂任务增强机制](../README.md#二为了完成工作任务agent-需要具备哪些能力) 对应到当前 job-agent 的应用代码和 DeepSeek Harness 实现，再逐段理解工程架构、核心函数与执行过程。
>
> **事实边界：** 已逐文件阅读这个提交中的应用代码、Docker、配置、测试和 CI；仓库已有 GitHub Actions 离线检查通过的记录，但没有从仓库中获得真实的模型调用和完整 Session 执行轨迹。因此下面的代码行为分为**源码确认的流程**与**仍待实测的 Runtime 行为**，绝不把预期结果当成已观察到的事实。

---

## 一、先回答一个问题：job-agent 究竟是什么项目？

假设现在让你打开 [job-agent](https://github.com/leecolin2023/job-agent)，不看项目名称，单看代码，你会发现一个事实：它没有实现自己的 Agent Loop，也没有直接调用任何 job-rag 检索工具。

目前它实际做的是：

1. 在隔离容器中准备 Python SDK 和运行目录。
2. 通过 Python SDK 启动 DeepSeek Harness Runtime。
3. 发送一个要求执行 `pwd` 与 `ls -la .` 的简单任务。
4. 接收运行结果，保存少量元数据。
5. 扫描 Runtime 持久化的 Session JSONL，统计事件类型与数量。
6. 通过不需要真实模型的离线测试检查上述包装代码。

因此，当前版本最准确的定位是：

> **job-agent 是一个用于学习、验证和逐步扩展 Agent Runtime 能力的应用实验项目。第一版是 DeepSeek Harness 的最小运行与观测样例，而不是已经完成的招聘岗位分析系统。**

名称中的两个词要拆开理解：

- **job** 表示后续计划解决招聘岗位研究问题，例如分析 RAG 相关职位要求；现阶段尚未接入职位库。
- **agent** 表示它选择通过现成 Agent Harness 执行任务，而不是在自己的 Python 代码中重新实现模型与工具的循环。

这不是“代码太少所以没有 Agent”。更恰当的理解是：**Agent 的一部分运行能力被封装在依赖中，job-agent 只编写自己的应用入口与运行约束。**

### 1.1 目前已经有的和还没有的

| 能力 | 当前情况 | 对应证据 |
| --- | --- | --- |
| Python SDK 调用入口 | **已实现代码** | `src/run_phase0.py` |
| Docker 隔离运行配置 | **已实现代码，未见真实容器运行验证** | `docker/Dockerfile`、`scripts/run-docker.sh` |
| 模型 / Profile / Session 参数 | **已传给 SDK，实际模型路由待实测** | `DeepSeekHarness(...)` |
| Session 事件结构统计 | **已实现，离线测试覆盖** | `src/session_report.py` |
| 禁止额外附加 Session 日志的配置 | **已声明，实际生效需核查运行版本** | `config/disable-session-upload.patch.yml` |
| GitHub Actions 离线检查 | **已有成功记录** | `.github/workflows/phase0-offline.yml` |
| 真实 DeepSeek 请求与工具调用 | **未获得实测证据** | 尚无真实 Session 样本 |
| job-rag 检索、完整 JD 解析 | **未实现** | 仓库不存在相应模块 |
| RAG 技术要求统计、报告生成、结果校验 | **未实现** | 仍是后续业务目标 |
| 自建 Planner、MCP、业务 State、Checkpoint | **未实现** | 不能把 DSH 内置能力直接当作项目自有实现 |

要避免两个相反的误解：一是把当前版本包装成完整招聘智能体，二是因为代码只有几份文件就忽视它实际依赖的 Agent Runtime。

---

## 二、整体架构：哪些是我们写的，哪些由 DeepSeek Harness 提供？

### 2.1 先从系统边界看

```text
                         job-agent 仓库（我们维护）
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  scripts/run-docker.sh                                       │
│    │ 负责 build / run / inspect / test                       │
│    ▼                                                         │
│  Docker 容器：运行环境和文件访问边界                          │
│    │                                                         │
│    ├── src/run_phase0.py  ← Python 应用逻辑                   │
│    │       │                                                 │
│    │       └── DeepSeekHarness(...).run(...)                  │
│    │                 │                                       │
│    │                 ▼                                       │
│    │          DeepSeek Harness Python SDK                    │
│    │                 │ stdio JSON-RPC                        │
│    │                 ▼                                       │
│    │          dsh Runtime（外部依赖）                         │
│    │            ├── Agent Loop                               │
│    │            ├── 模型适配器 ─────────────→ 模型 API        │
│    │            ├── Tool Executor ─────────→ 容器内 Bash     │
│    │            └── Session Store ─────────→ JSONL 文件      │
│    │                                                         │
│    └── src/session_report.py                                 │
│            └── 读取已有 JSONL，只统计事件结构                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
        │                 │                      │
        ▼                 ▼                      ▼
  .local/workspace   .local/dsh-home       .local/results
  工具工作区         Profile / Sessions     本次调用元数据
```

**最关键的边界：**

- **job-agent 自己负责“如何启动、传什么参数、保存什么、怎样观察”。**
- **DeepSeek Harness 负责“模型怎样与工具交替执行，以及 Session 如何被管理”。**
- **模型 API 负责“根据输入生成文本或者工具调用意图”。**
- **Docker 限制这个高权限执行器可以接触到哪些宿主资源。**

这四层的职责不能混在一起。例如，给 Python SDK 传入 `cwd`，并不会让 SDK 自动成为一个安全沙箱；真正约束容器与宿主之间文件访问的是 Docker 挂载和操作系统权限。

### 2.2 为什么不直接让 Python 调用模型 API？

如果只是问一句“你好”，直接调用模型 API 的确更简单。

但现在的目标不只是获得文本，还要能够观察：

```text
模型收到任务
    ↓
模型决定是否调用工具
    ↓
工具在真实环境执行
    ↓
结果回到模型
    ↓
模型继续决策或结束
    ↓
全过程形成 Session 事件
```

直接模型 API 只提供模型服务能力；工具注册、调用调度、状态推进和 Session 持久化仍需要应用自己实现。DeepSeek Harness 帮我们承担这部分 Runtime 工作，于是第一步只需编写很薄的 Python 应用。

这个选择有代价：**调用代码短，并不意味着运行机制简单。** 要真正理解内部循环，后续还需要追踪 DSH 的原生事件与相关源码。

### 2.3 目录不是功能架构：先分清三种角色

| 角色 | 当前文件 | 作用 |
| --- | --- | --- |
| **运行与部署** | `scripts/run-docker.sh`、`docker/Dockerfile`、`config/*.yml` | 解决在哪里运行、用什么版本、拥有哪些权限 |
| **应用与观测** | `src/run_phase0.py`、`src/session_report.py` | 解决调用什么任务、获得什么结果、怎样读日志 |
| **质量保障** | `tests/test_phase0.py`、`.github/workflows/phase0-offline.yml` | 解决应用包装代码是否有明显错误，不等同于真实 Agent 评测 |

`README.md` 是工程使用说明，`.gitignore`、`.dockerignore` 是文件边界；它们不属于 Agent 决策链，但关系到项目能否安全和稳定地运行。

**源码地图**（链接固定到本次解读的提交，避免未来改版导致解释与代码不符）：

- [Docker 运行入口](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/scripts/run-docker.sh)
- [Python Agent 调用入口](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/run_phase0.py)
- [Session 日志分析](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/session_report.py)
- [SDK 安装镜像](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/docker/Dockerfile)
- [Session 日志传输补丁](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/config/disable-session-upload.patch.yml)
- [离线测试](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/tests/test_phase0.py)
- [CI 配置](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/.github/workflows/phase0-offline.yml)

---

## 三、从最基本的 Agent Loop 到复杂任务增强：如何对应代码？

上一篇 [Agent Runtime 原理](../README.md#二为了完成工作任务agent-需要具备哪些能力) 已建立了一个顺序：

> **先理解模型决策 → 工具执行 → 反馈 → 继续或结束，再研究显式规划、计划修订、业务验证和人工审批等复杂任务机制。**

读这个项目也应采用同样的顺序。不要先搜索 `Planner` 类名，也不要把项目中没有 Planner 理解为“没有 Agent”。先找出让基本循环运转起来的代码，再看它何时需要更高层的任务控制。

### 1. 最基本的执行循环：模型决策 → 工具执行 → 反馈 → 继续或结束

把 [`src/run_phase0.py`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/run_phase0.py) 与 [DeepSeek Harness 的 `ReactLoopAgent`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts) 放在一起读。

#### 1.1 模型决策：谁决定下一步做什么？

job-agent 应用只把任务交给 SDK：

```python
with DeepSeekHarness(
    provider="deepseek-official",
    model=args.model,
    profile="sdk-minimal",
    # 其他参数见完整源码
) as harness:
    result = harness.run(args.prompt, session_id=args.session_id)
```

它并没有写 `if need_pwd: execute_pwd()`。模型是否调用工具、调用哪个工具，由 DSH Runtime 组织的模型请求结果决定。

DSH [`ReactLoopAgent.step()` 所在的实现](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts) 在模型返回 Assistant 消息后，检查其中的工具调用块：

```ts
const toolCalls = message.content.filter(block => block.type === 'tool-call')
if (toolCalls.length === 0) return { kind: 'completed' }
```

这就是最基本的**模型决策分支**：没有工具请求可以完成当前步骤；有工具请求则进入执行路径。模型给出怎样的工具请求，仍然需要实际运行才能观察。

顺带注意：`scripts/run-docker.sh` 的 `case "$ACTION"` 只是程序根据用户命令选择 `build/run/inspect`；它与 Agent 自主选择工具无关。

#### 1.2 工具执行：模型要求执行 Bash，谁真正执行？

紧接着上面的分支，DSH 源码调用：

```ts
const result = await this.loopCtx.tools.execute({
  calls: toolCalls,
  signal,
  agent: this,
  log: { turn, step },
  maxParallelToolCalls,
  toolSet: decision.toolSet,
})
```

这一步把模型的 `tool-call` 交给 Runtime 的工具执行体系，而不是让模型自己执行命令。

谁提供具体工具？[`sdk-minimal/cordis.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml) 装配 `dsh-tool-executor-native`、`dsh-tool-bash-persistent`（Linux）等插件。job-agent 的 `DeepSeekHarness(profile="sdk-minimal")` 选择这一组组件，而 [`run-docker.sh`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/scripts/run-docker.sh) 决定它在什么 Docker 环境下运行。

因此角色分工是：

- **模型**提出工具调用意图。
- **DSH Runtime** 负责识别、分发和调用工具。
- **Bash 工具**在容器内真正执行命令。
- **job-agent** 负责启动 SDK、选择 Profile、提供隔离环境，**没有另写一份工具执行器**。

有一个必须保留的边界：`sdk-minimal` 采用 `danger-full-access`，所以把 `cwd` 设为某个工作目录并不代表 Shell 只能访问该目录。Docker 挂载、用户权限及隔离策略才是这里的关键限制。

#### 1.3 反馈：工具返回后，为什么还能影响下一次决策？

工具完成后，DSH 的工具执行和 Session 机制保存调用及结果，再由 Agent Loop 基于已经形成的历史准备后续模型请求。它不是让 Python 应用先解析一遍 `pwd` 的文本，再手动追加到 Prompt。

与此相对，[`src/session_report.py`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/session_report.py) 只是在运行结束后统计日志事件类型。它用于**观察反馈是否有记录**，不是反馈通路本身。

这里要区分：

- **Runtime 具备反馈机制**：工具执行结果可进入 Session 和后续模型上下文。
- **本次实验确实发生了反馈**：必须从真实 JSONL 找到对应的调用及返回。
- **模型根据反馈纠正了错误**：要看到下一步行动真的发生改变，不能仅凭两次顺序调用推断。

#### 1.4 继续或结束：为什么一次 `harness.run()` 可能经历多次模型请求？

DSH 的 `ReactLoopAgent` 维护 Turn 和 Step 的执行过程。模型响应没有工具调用时，当前 Step 可进入 `completed`；如果有工具调用，执行结果通常会推动下一个 Step；出错、取消或触发限制也可能结束。

而 job-agent 应用只拿到最终的 `RunResult`：

```python
result.finish_reason
result.final_response
result.events
result.notifications
```

它还执行以下检查：

```python
if result.finish_reason not in (None, "completed"):
    return 1
return 0
```

**这只是脚本对运行终态的检查，不是“确认两个工具都执行成功”，更不是业务任务通过验证。** 尤其当前代码接受 `finish_reason=None`，故不能用脚本退出码为 0 证明 Agent 已完成目标。

把这四个环节连起来，就得到当前项目的核心运行路径：

```text
job-agent Python → harness.run(prompt)
                        ↓
                DSH Agent Loop
                        ↓
                 准备模型请求
                        ↓
                   模型决策
                 /         \
             直接回答       Tool Call
                │             ↓
                │        DSH 工具执行
                │             ↓
                │        Session 记录结果
                │             ↓
                │        下一次模型决策
                └─────→ 结束 / 中断
                        ↓
                   SDK RunResult
                        ↓
             job-agent 输出结果摘要
```

图中 DSH 内部行为依据官方源码和 Profile 配置；**仓库尚没有真实模型调用和工具事件样本，不能把这张逻辑图当作已经实测的轨迹。**

### 2. 当任务复杂起来：四种增强机制在项目里有没有？

基本执行循环讲清楚后，再问一个新的问题：如果目标不只是查看当前目录，而是**分析数百份 JD、找到涉及 RAG 的职位、统计必备和加分技术，并形成有原文证据的报告**，当前架构还缺少什么？

| 复杂任务机制 | 解决的问题 | 当前 job-agent / DSH Profile 状态 |
| --- | --- | --- |
| **显式任务规划** | 面对大目标，先明确样本范围、检索、筛选、统计与报告步骤 | **未实现**：`DEFAULT_PROMPT` 已直接规定两条命令；应用没有 Planner；`sdk-minimal` 没有装配 Plan Mode |
| **计划修订** | 数据或执行结果变化后更新待办、依赖和进度 | **未实现**：已有反馈通道，但没有独立的计划对象、完成状态或修订器 |
| **业务结果验证** | 防止遗漏 JD、错误计数、混淆必备/加分或引用不存在的职位 | **未实现**：仅有运行终态检查和日志结构统计，没有业务 Checker |
| **人工审批和权限** | 高风险修改、外部发送或敏感数据访问需要有效授权 | **未实现独立业务审批**：项目有 Docker 隔离选项，但没有针对业务操作的审批工作流 |

#### 2.1 显式规划：为什么当前看不到 Planner？

看 [`DEFAULT_PROMPT`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/run_phase0.py)：

```python
DEFAULT_PROMPT = (
    "这是一个隔离工作区实验。请先使用 bash 工具执行 `pwd`，再执行 `ls -la .`。"
    "只检查当前目录；不访问上级目录、环境变量或网络，也不修改文件。"
    "请用中文说明你实际调用的工具及返回结果；工具不可用就如实说明，"
    "不要编造执行记录。"
)
```

这里要求的是**按已知顺序执行两项操作**，不是生成一个多步骤计划。

进一步核对官方 [`sdk-minimal Profile`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/cordis.patch.yml)：虽然它挂载了 `agent-loop`、工具和 Session，但并没有挂载 `dsh-plan-mode`。

这不代表整个 DeepSeek Harness 没有规划功能。官方 [Plan Mode 插件](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/plan/plan-mode/README.md) 支持先探索、提交计划供用户审批等流程；完整 `sdk` Profile 的 SDK 命令路由也支持 `/plan`。**框架有功能和当前 Profile 启用了功能，是两件不同的事情。** 仅在当前项目中发送 `/plan` 文本，不能断言启用了官方 Plan Mode。

因此，当前 job-agent 还没有显式任务规划；它仍可依赖基本循环完成简单操作。未来分析 JD 时，可以再决定采用应用层 Planner、扩展 DSH 插件，还是保留动态行动决策而不维护完整计划。

#### 2.2 计划修订：和“看过工具结果后决定下一步”有什么区别？

如果 `pwd` 返回错误，模型可能决定修改下一次工具调用。这属于**基本循环中的反馈决策**。

而在数百份 JD 分析中，假设已经制定“检索 500 条 → 全文分类 → 汇总 → 校验”的计划，执行过程中发现岗位 ID 重复严重，就可能要改变样本范围、更新进度和重新计算分母。

后者不只是选择一条新命令，而是**显式更新计划、任务状态与完成条件**。目前 job-agent 没有相应 State 或 Plan 数据结构。

#### 2.3 业务验证：为什么 `finish_reason` 和离线 CI 都不够？

如果 Agent 最后回答“Python 是 RAG 岗位最常见技能”，需要有统计范围、分母、职位 ID 和可回查的原文支持。

当前代码只检查 `result.finish_reason`，并统计 `result.events` 的数量；离线 `FakeHarness` 测试能验证 Python 包装逻辑，但不能证明统计过程或结论正确。

未来的业务 Checker 至少应验证：检索样本范围固定、岗位按 ID 去重、必备/优先技术分开计数、每项结果保留证据、报告真实存在。**正常结束、工具成功和业务验收，是不同层次。**

#### 2.4 人工审批：为什么 Docker 不是审批系统？

Docker 的 `--read-only`、`--cap-drop=ALL`、挂载目录限制了容器的部分执行范围，但它并不认识“这个用户是否可以更新 JD 数据库”这样的业务规则。

当前项目没实现用户身份、资源权限或人工审批流程；而 API Key 作为容器环境变量传入，Shell 仍有机会读取它。真正接入外部系统前，必须根据工具风险补充适用的授权控制，必要时在高风险调用前请求用户确认。

### 3. 当前实现到哪一步？接下来怎样验证？

| 需要确认的事实 | 已有依据 | 尚缺的证据 |
| --- | --- | --- |
| 应用能够调用 SDK | `src/run_phase0.py` 有调用代码，`FakeHarness` 单元测试通过 | 真正 SDK 初始化和模型请求 |
| DSH 可以做模型决策 / 工具执行 | `agent-loop/src/agent.ts`、`sdk-minimal/cordis.patch.yml` | 本项目真实的 Tool Call 与工具返回 |
| 工具反馈可以推动下一轮 | DSH Agent Loop 源码 | 本项目一次完整“调用 → 返回 → 后续决策”事件链 |
| 显式规划 / 计划修订 | 当前没有应用实现或对应 Profile 插件 | 后续需求与新实现 |
| 业务验证 / 审批 | 当前没有业务 Checker 或审批流程 | 后续实现及独立测试 |

**学习顺序也应保持一致：先在一次真实 Session 中核实最小循环，再研究为何复杂岗位分析任务需要额外的计划、校验和授权机制。** 没有必要一上来设计一个包含所有高级能力的庞大平台。

---

## 四、从入口开始：一次任务是怎样被启动的？

不要从 `run_phase0.py` 的第一行开始死读。更自然的方式是顺着真实用户的操作：

```bash
bash scripts/run-docker.sh check
bash scripts/run-docker.sh build
bash scripts/run-docker.sh run
bash scripts/run-docker.sh inspect
```

四个命令分别对应环境检查、镜像构建、Agent 执行和 Session 观察。

### 4.1 `run-docker.sh` 为什么是第一层入口？

打开 [`scripts/run-docker.sh`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/scripts/run-docker.sh)，开头几行确定四个路径：

```bash
LAB="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$LAB/.local/dsh-home"
WORKSPACE="$LAB/.local/workspace"
RESULTS="$LAB/.local/results"
```

这里有三个不同的存放位置：

- **WORKSPACE**：Agent 执行任务时操作的文件目录。
- **STATE**：DeepSeek Harness 的 Home，放 Profile、Session 等运行时状态。
- **RESULTS**：我们自己的 Python 代码保存的执行摘要。

为什么不放在一个目录里？因为它们的责任不同。比如你想清理演示任务创建的文件，不应该同时删除 Session 证据；你想清空某次会话，也不一定要删除用户交付的文件。

接着脚本用 `case "$ACTION"` 选择 `check`、`build`、`run`、`inspect` 或 `test`。

这里也出现一个重要概念区别：

> **`run-docker.sh` 的分支是一段普通 Bash 控制流程，不是 Agent 的 Workflow Planning。**

脚本并没有让模型选择“应该 build 还是 inspect”。这些步骤由用户明确指定，程序按照固定规则执行。

### 4.2 `build` 究竟构建了什么？

`build` 分支执行 `docker build`，Dockerfile 的关键代码是：

```dockerfile
FROM python:3.12-slim-bookworm
ARG DSH_SDK_VERSION=""
RUN set -eux; \
    if [ -n "$DSH_SDK_VERSION" ]; then \
      python -m pip install --no-cache-dir "deepseek-harness-sdk==${DSH_SDK_VERSION}"; \
    else \
      python -m pip install --no-cache-dir deepseek-harness-sdk; \
    fi; \
    python -m pip check
```

代码有两个设计：

**第一，选择 Python SDK 而不是自己部署一套 Agent 服务。** 官方 `deepseek-harness-sdk` 包依赖匹配的 Runtime 二进制 wheel，正常启动 SDK 不需要另行从源码构建 Node.js 服务。

**第二，支持指定 SDK 版本但默认不锁定。** 不提供 `DSH_SDK_VERSION` 时，每次构建可能安装不同版本。对于学习实验，这会带来一个问题：同样的代码，过几天运行结果不同，究竟是 Prompt 影响还是 SDK 升级？

因此当前项目提供了版本锁定入口，但尚未在仓库固定版本。后续进行可比较实验时，应记录镜像摘要、SDK 与 Runtime 版本、模型端点及模型版本。

另外，`python -m pip check` 只检查 Python 依赖一致性，**不验证 DSH 能否成功启动，更不会调用模型**。

### 4.3 `run` 怎样把 Agent 放进容器？

最值得看的不是参数数量，而是三个方面：

**第一组：限制执行环境。**

```bash
docker run --rm --init --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --pids-limit=128 --memory=2g --cpus=2 \
  ...
```

这些选项来自脚本内的 `ARGS` 数组。它们限制进程权限和资源、让容器根文件系统只读。脚本还用当前宿主用户 UID/GID 运行容器，避免以容器镜像的默认用户权限直接处理绑定目录。

**第二组：把三类路径挂入容器。**

```bash
--mount "type=bind,src=$LAB,dst=/sandbox/lab,readonly"
--mount "type=bind,src=$STATE,dst=/sandbox/state"
--mount "type=bind,src=$WORKSPACE,dst=/sandbox/workspace"
--mount "type=bind,src=$RESULTS,dst=/sandbox/results"
```

宿主项目目录只读；运行时 Home、任务工作区与结果目录可写。这意味着模型通过 Shell 即使修改文件，也应限制在容器可写挂载范围内，而不能随意修改宿主其他路径。

**这里有一个关键边界：** `sdk-minimal` 使用的 `danger-full-access` 指的是相对于其进程所能接触到的环境；它可以访问整个容器内对其开放的文件，而不只 `/sandbox/workspace`。Docker 是外层隔离层，但并非绝对安全边界。

**第三组：传递输入与启动 Python。**

```bash
--env DEEPSEEK_API_KEY
--env "HOME=/sandbox/state" --env "DSH_HOME=/sandbox/state"
...
python /sandbox/lab/src/run_phase0.py \
  --workspace /sandbox/workspace \
  --dsh-home /sandbox/state \
  --patch /sandbox/lab/config/disable-session-upload.patch.yml \
  --output "/sandbox/results/$SESSION_ID.json" \
  --session-id "$SESSION_ID"
```

脚本还允许自定义 `DEEPSEEK_BASE_URL`、`DSH_MODEL`，并用时间戳加 Shell PID 构造本次 Session ID。注意这仅是一个便捷命名方案，不是分布式系统中经过验证的全局唯一标识生成器。

**这一阶段的理解：** Bash 负责准备运行条件和传参；真正的 Agent 尚未开始做模型决策。

---

## 五、核心代码一：`src/run_phase0.py` 怎样调用 Agent？

这是本项目最关键的 Python 文件：[查看完整代码](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/run_phase0.py)。

### 5.1 为什么先写一个固定的 `DEFAULT_PROMPT`？

`DEFAULT_PROMPT` 的主要要求是：

```text
请使用 bash 工具执行 pwd、ls -la .
只检查当前目录，不修改文件。
说明实际调用的工具和结果；失败时不要编造。
```

为什么不直接让它“分析 500 条 RAG 职位”？因为现阶段首先要确认的是**执行链是否真的通了**：模型是否能发现工具、发起调用，工具是否产生了真实结果，模型是否参考结果作答。

`pwd` 和 `ls -la .` 具有低复杂度、容易人工复核的输出，有利于定位基础运行问题。

但这里仍有一条重要边界：**Prompt 只是向模型提出行为要求，不是可强制执行的安全策略。** 要禁止访问上级目录、泄露密钥或联网，必须依靠执行环境和真正的权限控制，而不是依靠这几句话。

### 5.2 为什么在导入 SDK 之前检查参数？

`main()` 用 `argparse` 接收：

```text
--workspace   工具工作区
--dsh-home    Runtime 的独立 Home
--patch       Profile 补丁
--output      元数据输出文件
--session-id  本次 Session ID
--model       使用的模型 ID
--prompt      本次任务
```

随后检查 `DEEPSEEK_API_KEY` 是否存在；用 `Path.resolve(strict=True)` 确认所需路径存在；要求工作区与 Home 不相同，也不能互相包含。

为什么要做这些检查？因为一旦 Runtime 启动，错误可能表现为很难理解的“SDK 初始化失败”或“工具访问不到目录”。应用先检查能够确定的配置条件，就可以更早、更明确地停止。

但**路径不相同**只表示目录组织清晰，不意味着它们已经获得操作系统级隔离；安全边界仍主要来自 Docker 和宿主权限。

### 5.3 项目的中心：`DeepSeekHarness(...)`

代码真正调用 Agent 的地方只有下面这一段：

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(
    provider="deepseek-official",
    model=args.model,
    max_tokens=4096,
    cwd=str(workspace),
    dsh_home=str(home),
    profile="sdk-minimal",
    patches=(str(patch),),
) as harness:
    result = harness.run(
        args.prompt,
        session_id=args.session_id,
    )
```

逐项理解参数：

| 参数 | 实际控制什么 | 容易误解之处 |
| --- | --- | --- |
| `provider` | 模型适配器的路由名称 | 不是 URL，也不一定表示模型一定已经成功调用 |
| `model` | 提交给适配器的模型 ID | 必须与端点实际可用模型匹配 |
| `max_tokens` | 模型单次输出上限设置 | 不是整个 Agent 任务的 Token 预算 |
| `cwd` | Session 工作目录 | 不是沙箱或权限限制 |
| `dsh_home` | Profile、Session、运行资源等的 Home | 不是业务岗位数据库 |
| `profile` | 选择 DSH 的插件组合 | `sdk-minimal` 不是一个 Python 自写 Agent 类 |
| `patches` | 启动时额外叠加的配置 | 需通过实际 Runtime 确认补丁成功应用 |
| `session_id` | 标识本次会话 | 本项目尚未使用恢复 API |

`with ... as harness` 使用上下文管理器启动和关闭 SDK 生命周期；官方 SDK 会在需要时启动独立的 `dsh` 进程，并通过 stdio JSON-RPC 与之通信。

**为什么看不到 `while` 循环？**

因为 `while` 形式的 Agent Loop 不在 `run_phase0.py`。在当前设计中，应用一次调用 `harness.run()`，而模型请求、工具调用、反馈和后续模型调用由 DeepSeek Harness Runtime 内部组织。

这就是“使用 SDK 构建 Agent”和“自己实现 Agent Runtime”的实质区别。

### 5.4 `RunResult` 返回后，项目处理了什么？

当前代码使用以下字段：

```python
result.session_id
result.finish_reason
result.events
result.notifications
result.final_response
```

它们分别代表会话身份、终止原因、根会话事件、通知以及最终文本。

项目又把这些信息压缩为一个摘要：

```python
kinds = Counter(event_kind(e) for e in result.events)
record = {
    "session_id": result.session_id,
    "finish_reason": result.finish_reason,
    "root_event_count": len(result.events),
    "notification_count": len(result.notifications),
    "root_event_kinds": dict(sorted(kinds.items())),
    "final_response_length": len(result.final_response or ""),
    # ...
}
```

为什么不直接将所有原始事件打印出来？因为工具参数、用户输入或模型输出可能包含敏感内容。这个实验先保留事件数量和类型，既便于学习，也降低意外公开原始数据的风险。

但要特别注意：

- **`root_event_count` 不是模型调用次数。**
- **`notification_count` 不是工具执行次数。**
- **`finish_reason == "completed"` 不是业务任务验证通过。**
- **`root_event_kinds` 只是对已返回事件按字段分组，不能单凭计数复原执行因果链。**

当前代码检查 `finish_reason` 时还接受 `None`：

```python
if result.finish_reason not in (None, "completed"):
    return 1
```

因此脚本返回 0，并不能独立证明工具真的成功执行；它只表示没有遇到当前这段检查判定为失败的结束原因。

另一个细节：元数据字段 `session_log_upload_disabled_by_patch: True` 记录的是“调用时传入了禁用补丁”，**不是抓包验证过日志没有上传**。文章和后续评测不能把配置意图写成实测事实。

---

## 六、核心代码二：为什么需要 Session 日志分析器？

完成 `run()` 后，SDK 已经提供了最终回答；那么 [`src/session_report.py`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/src/session_report.py) 还有什么价值？

因为**最终回答是结果，而 Session 是运行过程的历史**。

例如，模型说“我检查了目录”，如果我们想知道它是否真的执行过 Bash，应该回查原生事件，而不是相信回答中的自我描述。

### 6.1 数据从哪里来？

DeepSeek Harness 的 `sdk-minimal` 使用位于 `DSH_HOME/sessions` 的 JSONL Session 存储。本项目 Docker 挂载将 `/sandbox/state` 映射到宿主 `.local/dsh-home`，所以真实运行后的日志预期可以在宿主找到。

`session_report.py` 做的第一件事，是：

```python
sessions = home / "sessions"
files = sorted(sessions.rglob("*.jsonl"))
```

这里的 `rglob` 表示递归查找，而不是只读取一个固定 Session ID。这个实现适合“先查看运行目录里有哪些 Session”，但如果 Home 里积累多个实验，就不应把它们的合计事件数解释为**最近一次任务**的事件数。

### 6.2 `classify()` 为什么只识别事件类型？

`classify(obj)` 依次尝试：

```python
for key in ("kind", "type", "event_type"):
    value = obj.get(key)
    if isinstance(value, str):
        return value
nested = obj.get("event")
return classify(nested) if isinstance(nested, dict) else "unknown"
```

这不是 DSH 事件协议的完整解析器，而是一个**兼容若干常见事件包装形式的结构查看器**。

例如，输入以下人为构造的数据：

```json
{"kind": "tool/result", "data": {"value": "private text"}}
```

分析器只会统计 `tool/result` 这一类，而不会输出 `data.value`。这个例子用于解释代码行为，**不是从真实 DSH Session 捕获的记录**。

### 6.3 `summarize()` 怎样处理异常数据？

它逐文件统计：路径、字节数、非空记录行数、无效 JSON 行数和事件类型。超过 32 MiB 的单个 JSONL 文件会被跳过，并在结果中标注；不存在 Session 目录会报错；Session 目录存在但没有 JSONL 文件时，命令返回非零状态。

为什么这样设计？因为现阶段的目标只是安全观察日志结构，而不是展示所有内容或实施业务审计。

但这个设计**尚不能**直接回答以下问题：

- 哪一次工具调用对应哪一次工具返回？
- 是哪一轮模型请求产生了这个工具调用？
- 工具失败后，模型是否改变了计划？
- 哪些事件是历史 Session 的，哪些属于本轮 `run()`？

要回答这些问题，需要在真实样本上读取事件序号、时间、消息关联、工具调用 ID 等原生结构，再建设专门的 Trace 分析器，而不是继续增加几个计数器。

---

## 七、一次任务的数据到底流向哪里？

把此前的代码串起来，你可以画出两个同时发生的流：**执行流**与**证据流**。

### 7.1 执行流：真实动作怎样发生？

```text
用户在 shell 输入 run
   ↓
run-docker.sh 创建 Session ID，准备宿主的三个目录
   ↓
Docker 启动带限制的容器
   ↓
Python 校验参数和路径
   ↓
DeepSeekHarness 通过 SDK 初始化 dsh
   ↓
Runtime 组织模型请求，携带当前任务与可用工具
   ↓
模型可能请求 bash 执行 pwd / ls
   ↓
Runtime 执行工具，结果回到后续模型输入
   ↓
模型形成回答，Runtime 结束当前 Turn
   ↓
SDK 返回 RunResult，Python 打印回答
```

其中最后几步是根据 SDK/Runtime 官方设计推导出的**预期路径**。仓库没有提交一次可用于核对的真实完整 Session，所以不能声称这次实验已经按图执行成功。

### 7.2 证据流：结果保存到哪里？

```text
                        dsh Runtime
                       /           \
                      /             \
      原生历史事件 JSONL          RunResult 返回 Python
             │                           │
             ▼                           ▼
 .local/dsh-home/sessions/      .local/results/<session-id>.json
             │                           │
             ▼                           ▼
 src/session_report.py          结构化运行摘要
             │
             ▼
 事件类型 / 数量 / 异常行统计
```

两份材料的目的不同：

- **JSONL** 保存 Runtime 的历史事件，适合追查具体过程；可能包含原始提示词、工具参数和工具结果。
- **结果 JSON** 是 job-agent 自己生成的执行摘要，只有时间、版本、结束原因和事件数量等元信息；不包含完整因果链。

`.gitignore` 排除了 `.local/`，所以运行时数据预期留在宿主本地，而不是自动提交到 GitHub。`.dockerignore` 额外排除这些内容，防止误放入 Docker 构建上下文。

**为什么必须区分“运行记录”和“模型上下文”？** Session 可以保存大量历史，而某次模型调用可能只看到经过选择、压缩或组合的信息。观察到历史事件并不能直接证明当时模型上下文包含所有历史内容。

---

## 八、配置解读：为什么这里要用 Profile Patch？

打开 [`config/disable-session-upload.patch.yml`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/config/disable-session-upload.patch.yml)：

```yaml
- id: session-log-deepseek
  config:
    enabled: false
```

这个文件很短，但很适合学习 SDK、Runtime 与配置之间的边界。

### 8.1 什么是 `sdk-minimal` Profile？

它不是一个提示词名称，而是一份由 DSH 装配的 Runtime 配置。官方 `sdk-minimal` 主要面向轻量 Coding Agent，包含 Agent 执行、模型适配、持久 Shell、Session JSONL 和上下文压缩等能力。

Python 代码选择 `profile="sdk-minimal"`，相当于选择这一组已经存在的执行组件，而不是自己在 Python 中实现它们。

### 8.2 Patch 改变了什么？

`patches=(str(patch),)` 表示启动时在指定 Profile 上叠加配置。本项目只显式关闭 `session-log-deepseek` 将 Session 事件作为附加请求字段提交到 DeepSeek API 的功能。

需要分清三种数据流：

1. 用户 Prompt 及必要工具反馈仍然会随正常模型请求发送到配置的模型端点。
2. JSONL Session 仍会保存在本地。
3. 被关闭的是额外的 Session 日志附加传输，而不是所有出站网络或所有模型数据传输。

因此，**这份补丁不是“隐私完全隔离”开关。** 而且本项目目前没有在实际网络请求层验证补丁是否已正确生效，严格场景还需要检查对应 DSH 版本和网络日志。

---

## 九、测试代码在验证什么？又没有验证什么？

[`tests/test_phase0.py`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/tests/test_phase0.py) 可以分成两组。

### 9.1 SessionLogTests：验证日志统计器

它人为创建小型 JSONL 文件，检查：

- `classify()` 可以识别 `kind`、嵌套 `type` 等事件标签。
- 统计结果不会输出人为放在 `data` 里的测试秘密字符串。
- 无效 JSON 行被计数。
- Session 目录存在但没有任何 JSONL 时返回非零退出状态。

这证明的是**分析器对于这些人为构造输入的行为**，不是证明 DSH 当前真实 JSONL 的事件 Schema 一定完全兼容。

### 9.2 SDKRunnerTests：为什么创建 `FakeHarness`？

测试中用一个模拟对象替换 `deepseek_harness.DeepSeekHarness`：

```python
class FakeHarness:
    def run(self, prompt, session_id):
        return SimpleNamespace(
            session_id=session_id,
            finish_reason="completed",
            events=[
                {"kind": "turn/start"},
                {"kind": "turn/end"},
            ],
            notifications=[{"type": "session/event"}],
            final_response="完成了模拟测试",
        )
```

这样做是为了在**不依赖 API Key、不花模型 Token、也不启动真正 Runtime** 的条件下验证我们自己的胶水代码：参数是否传对、元数据是否能保存、无凭据时是否拒绝、工作区与 Home 相同是否拒绝。

它没有验证模型会不会调用 Shell，也没有验证真实 DSH Profile、SDK 与 JSONL 版本是否兼容。

### 9.3 GitHub Actions 为什么绿了也不能代表 Agent 成功？

[`.github/workflows/phase0-offline.yml`](https://github.com/leecolin2023/job-agent/blob/70326a48b85ef813642f8e5298f44465fa98166e/.github/workflows/phase0-offline.yml) 执行三类检查：

```bash
bash -n scripts/run-docker.sh
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

这只是 Bash 语法、Python 语法和离线单元测试。它**没有执行 `docker build`、`docker run`、`harness.run()`，也没有真实模型请求**。

[已有成功的离线 CI 记录](https://github.com/leecolin2023/job-agent/actions/runs/41429202897) 是代码质量的一条证据，但不是 Agent 能够完成任务的证据。

这里要建立一个以后一直使用的判断规则：

> **代码可以通过测试，却无法证明整个 Agent 任务成功；任务能输出最终文本，也无法证明它实际执行过工具；工具执行成功，还不能直接证明业务结论正确。**

---

## 十、这套架构当前最需要注意的边界

这里不是要求立即重构，而是帮我们建立对现有工程的正确判断。

### 10.1 Shell 权限与容器隔离

当前 `sdk-minimal` 是高权限执行配置，而 `run-docker.sh` 使用只读根文件系统、能力裁剪、独立挂载目录和资源配额。它减少了宿主暴露面，但**没有实现只能执行 `pwd` 和 `ls` 的工具白名单**。

而且 API Key 通过 `--env DEEPSEEK_API_KEY` 进入容器。即使 Prompt 要求模型“不要读取环境变量”，模型侧 Shell 仍有可能访问进程可见的凭据。应使用单独的低额度测试 Key，并在以后把真正的模型凭据放到隔离环境之外的受控网关。

### 10.2 Docker 网络没有默认做到只访问模型 API

脚本使用 `--network bridge`（可以通过环境变量指定其他网络）。它不等于“只允许访问指定模型服务器”；若使用不受信任的任务内容，就需要额外控制出站网络。

### 10.3 当前监控偏向“数量”，不等于 Agent Trace

`session_report.py` 统计事件类型，没有建立按 `session_id`、事件时序和 `tool_call_id` 的因果关系，也未核对输出文本与真实工具结果是否一致。

这足以作为第一步的结构观察，却不足以做完整 Agent Loop 分析。

### 10.4 当前成功条件较弱

`run_phase0.py` 接受 `finish_reason=None`，只检查 SDK 返回值，并没有明确断言“必须真的出现 Bash 调用和成功返回”。因此“命令退出码为 0”不代表阶段 0 的全部教学目标已实现。

### 10.5 可重复性尚未闭环

Docker 支持 `DSH_SDK_VERSION`，但默认没有锁版本；模型通过端点和模型 ID 动态选择；没有仓库内可回查的真实执行记录。未来做前后对照实验前，应先固定数据、SDK、镜像和模型条件。

这些都是从当前代码可以识别的**工程边界**，不必因此把项目扩展成多租户 Agent 平台。第一轮只需先拿到一个可信、可重放的执行样本。

---

## 十一、如何用这个项目真正理解 Agent Loop？

读完代码后，下一步最值得做的不是新增复杂工具，而是回答：

> **一次 `harness.run()` 内部到底发生了多少轮模型调用？哪个事件代表模型请求工具？工具什么时候执行、什么时候返回？**

建议按以下顺序观察真实实验：

| 步骤 | 查看哪里 | 要回答的问题 |
| --- | --- | --- |
| 1 | `scripts/run-docker.sh run` 的启动输出 | 本次 Session ID、模型、Home 是什么？ |
| 2 | `.local/results/<id>.json` | Python 得到什么 `RunResult`？终止原因是什么？ |
| 3 | `scripts/run-docker.sh inspect` | 是否生成 JSONL？有哪些事件类型？ |
| 4 | **只在安全环境中**读取对应 JSONL | 是否存在工具调用、工具返回和它们的关联？ |
| 5 | 检查 `pwd`、`ls` 的真实返回 | 最终回答是否准确反映工具结果？ |
| 6 | 对照 DSH Runtime 的对应源码 | 哪一层负责工具分发和下一轮模型请求？ |

这时可以把第一次真实 Trace 整理为：

```text
用户要求观察目录
  ↓
[模型请求 #1：实际内容待记录]
  ↓
[工具调用：工具名称、参数、调用 ID 待记录]
  ↓
[执行反馈：是否成功、输出是什么待记录]
  ↓
[模型请求 #2：是否真的发生待记录]
  ↓
[最终回答及结束事件待记录]
```

**方括号中的内容是待填项，不是本文虚构的一次执行日志。**

通过这条链，我们才能从“SDK 很方便”走到真正的机制理解：

- **SDK** 把应用和 Runtime 连接起来。
- **Runtime** 调度模型与工具、管理任务进度。
- **模型** 提出下一步操作的意图。
- **执行环境** 实际执行操作并产生可观察结果。
- **Session** 保留历史供排错与后续恢复。
- **业务应用** 应独立判定是否真的完成了目标。

---

## 十二、未来怎样从最小示例演进为真正的 JD Research Agent？

现在项目能做的，是让 Agent 观察一个隔离目录。要实现最初的业务问题：

> 统计岗位职责或任职要求涉及 RAG 的职位，其相关技术要求是什么？

仍缺少几层明确的业务能力。

| 下一阶段要加的能力 | 为什么需要 | 与当前代码的衔接点 |
| --- | --- | --- |
| 固定的完整 JD 样本 | 避免直接在真实岗位库上做不可重复实验 | 挂载只读数据到 `workspace`，不修改主数据 |
| 岗位查询工具 | 让 Agent 按条件检索与读取证据，而非把所有 JD 塞进 Prompt | 扩展 DSH 工具 / 插件 / MCP 接入 |
| 岗位技术要求结构化 | 区分“岗位提及”“必备”“加分”和统计分母 | 明确业务输出 Schema 与证据规则 |
| 报告与结果验证 | 区分“生成回答”与“交付可核对的研究报告” | 在应用层检查产物、职位 ID、引用 |
| 可解释的 Trace 与评测 | 判断遗漏、错误归类是检索、模型还是工具的问题 | 扩展 Session 分析与业务测试 |
| 更长任务的 State 和恢复 | 多批次 JD 可能需要中断后继续处理 | 将业务进度与 Session 历史分开设计 |

这里尤其要注意：**并不是先把 `src/run_phase0.py` 改成几千行、自己实现 Agent Loop。** 它可以继续作为薄入口，把新的工具和验证能力通过明确接口引入；真正需要自定义编排或运行策略时，再判断改动应用层还是扩展 DSH Runtime。

---

## 十三、读完之后，应当能够讲清楚什么？

不用记住所有命令。能够解释下面这段话，就表示你已经建立了整体理解：

> job-agent 当前是一个基于 DeepSeek Harness 的最小 Agent 实验工程。Bash 脚本准备 Docker 容器和三种不同的宿主目录；Python 入口检查参数，再通过 `DeepSeekHarness` 启动 Runtime 并提交一个简单任务。模型调用、Agent Loop 和 Bash 工具执行主要由 DSH Runtime 负责；运行结束后，Python 取得 `RunResult`，Runtime 把 Session 历史写成 JSONL。另一个 Python 脚本只分析 JSONL 的事件结构。离线测试检查的是应用包装代码，不代表已经完成真实的模型或工具调用。后续必须拿到可核对的 Trace，才能真正研究 Agent Loop，然后再接入 job-rag 的岗位研究场景。

从这里再去读 DeepSeek Harness 的 Agent Loop、Tool Calling、Context、Session 和插件源码，你才不会把“框架内部提供的能力”和“job-agent 已经自己实现的功能”混淆。

---

## 代码依据与延伸阅读

- [job-agent 的本次代码基准提交](https://github.com/leecolin2023/job-agent/tree/70326a48b85ef813642f8e5298f44465fa98166e)
- [HarnessLab｜Agent Runtime 基础原理](../README.md)
- [HarnessLab｜从应用到机制的学习路线](../LEARNING_PATH.md)
- [DeepSeek Harness 官方 Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/main/python/sdk/README.md)
- [DeepSeek Harness 官方 sdk-minimal 说明](https://github.com/deepseek-ai/deepseek-harness/blob/main/packages/bundle/sdk-minimal/README.md)
- [DeepSeek Harness 安全说明](https://github.com/deepseek-ai/deepseek-harness/blob/main/SAFETY.md)

> 维护原则：代码更新后，以最新的 job-agent 提交重新核对本文具体实现；有真实 Session 后再补充实测轨迹，不得把“理论上的 Agent Loop”假冒成项目已经运行出的 Trace。
