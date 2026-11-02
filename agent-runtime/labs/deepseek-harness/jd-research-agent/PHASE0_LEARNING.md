# 实验 00｜从 Python SDK 到真正运行的 Agent：构建、观察与解释

> 对应 [Agent Runtime 学习路线：阶段 0](../../../LEARNING_PATH.md)。  
> **当前状态：隔离启动方案、Python 实验脚本、Session 统计器和离线测试代码已入库；尚无真实模型调用结果。** 实验完成与否必须根据你运行后的文件和日志核实，不能因为代码已提交就标记完成。  
> SDK 参考版本：以 2026-11-02 查阅的 DeepSeek Harness 官方 `python/sdk/README.md`、`docs/user/guide/python-sdk.md` 为依据。其处于 Developer Preview，实际运行时需要保存版本号。

## 一、我们到底要回答什么问题？

此前我们定义 Agent Runtime 为让模型能够持续决策、调用工具、接收反馈、推进任务的执行层。

但光看一句定义，我们还不能回答：

1. Python 代码调用一次 `harness.run()`，究竟谁负责执行 Agent Loop？
2. 模型发出工具调用请求之后，谁真正运行工具？
3. SDK 返回的最终回答，与 Session 里保存的执行历史有什么不同？
4. Runtime 退出后，为什么仍然能够找到刚才执行的记录？
5. 只设 `cwd` 为什么不能保证 Agent 不访问其他文件？

本实验只验证最小的“一次任务 → 可观察的工具执行 → 最终回答 → 持久化 Session”。不引入 MCP、RAG、多 Agent、Checkpoint 或 Office 能力。

**最小验收标准：** 在真实隔离容器里调用一次模型，至少拿到 SDK 返回值、Session JSONL 文件，以及可以回查的工具调用事件；如果模型没有调用工具，也必须记录为“未观察到工具调用”，而不是声称已通过。

## 二、先看整个执行链：SDK 不是 Agent Loop 本身

```text
我们写的 Python 程序
  src/run_phase0.py
         │
         │ DeepSeekHarness(...).run(prompt, session_id)
         ▼
DeepSeek Harness Python SDK
  客户端：负责生命周期及 stdio JSON-RPC
         │
         │ 启动 dsh --profile sdk-minimal
         ▼
dsh Runtime（独立进程，Cordis 插件组合）
         ├── 模型适配器 → DeepSeek 兼容 API
         ├── Agent Loop：模型输出、下一步决策
         ├── Bash 工具：真正执行命令
         └── Session Store：落盘 JSONL
         │
         ├── RunResult：通过 SDK 返回 Python 程序
         └── $DSH_HOME/sessions/：完整的原生记录
```

这段调用链是理解后续所有模块的前提。

- **Python SDK** 让应用以 Python 接口启动与控制运行过程，接收执行结果。
- **`dsh` Runtime** 才是组织模型、工具、Session、插件和工作循环的运行主体。
- **模型** 根据上下文决定回答或请求调用 Bash 工具。
- **工具执行环境** 真正执行 Bash 命令，再把结果送回 Runtime。
- **Session Store** 保留历史事件；它不等于本次模型实际看到的完整 Context，更不是一个自动恢复所有外部进程的业务 Checkpoint。

`harness.run()` 从 Python 看像一次调用，但在 Runtime 内部可以对应多次模型调用和工具执行。它们不是同一个粒度。

---

## 三、搭建前，先决定什么才叫“隔离”

官方 `sdk-minimal` profile 默认采用 `danger-full-access`；持久 Shell 可以访问运行进程可见的文件。**`cwd` 是工作目录，不是访问控制或安全沙箱。**

因此实验只允许在单独的 Linux Docker 环境或更严格的专用 VM 中进行；本项目提供 Docker 方案。注意容器只能降低风险，**不是绝对安全边界**。实验需要访问远端模型 API，所以容器仍需要网络出站；默认 Docker bridge 网络并没有限定“只能访问 DeepSeek API”。如果需要严格的出站限制，应在宿主防火墙或专门的代理层控制目标域名、IP 和端口。

本实验的容器限制：

| 机制 | 解决的具体问题 | 还不能解决什么 |
| --- | --- | --- |
| `--read-only` | 防止修改镜像中的根文件系统 | 已挂载的工作目录和 Home 仍可写 |
| 独立 `workspace` | 与正式仓库、工作文件隔离 | 本身不是权限边界 |
| 独立 `dsh-home` | 将 Profile、日志、缓存与日常配置分离 | 日志仍可能包含敏感内容 |
| `--cap-drop=ALL`、`no-new-privileges` | 限制容器进程权限提升 | 不能代替宿主的容器安全配置 |
| `--pids-limit`、内存及 CPU 配额 | 限制部分资源滥用 | 不限制模型 API 调用成本 |
| 不挂载 `docker.sock` | 防止直接控制宿主 Docker Daemon | Docker 守护进程本身仍具很高权限 |
| 只读挂载实验代码 | 防止 Agent 修改实验脚本 | 可以修改独立的 writable workspace |
| 单独的模型 API Key | 缩小泄露后的影响范围 | Key 仍存在容器进程环境，Shell 可能读取到 |

**尤其重要：** 在容器里提供 `DEEPSEEK_API_KEY`，就意味着拥有 Shell 的 Agent 可能通过环境变量读取它。请使用专门、限额、可撤销的测试 Key，配置模型侧用量限制，并避免对不受信任的外部提示词开放这个实验。完整消除这一风险需要把模型凭据保留在容器外，通过鉴权网关转发，属于以后“安全与模型网关”阶段的研究内容。

## 四、准备条件

### 4.1 基础软件

- Linux x86_64 或 arm64，推荐独立测试机器或 VM。
- Docker Engine（CLI 和 Daemon 可用），Dockerfile 会使用 Python 3.12。
- 可以访问 Python 包仓库以构建镜像；能够访问你配置的 DeepSeek 兼容 API。
- 一个测试用的 API Key。**不要提交到 GitHub，也不要粘贴到聊天或项目文件中。**

以下命令在仓库根目录启动：

```bash
git clone https://github.com/leecolin2023/HarnessLab.git
cd HarnessLab/agent-runtime/labs/deepseek-harness/jd-research-agent

bash scripts/run-docker.sh check
bash scripts/run-docker.sh test
```

`check` 只检查环境状态，不执行 Agent；`test` 是使用模拟 SDK 的**离线单元测试**，它不需要模型 API、Docker 或真实 SDK。测试通过不能证明真实 Agent 可以运行。

### 4.2 构建 SDK 镜像

```bash
bash scripts/run-docker.sh build
```

Dockerfile 在镜像里安装 `deepseek-harness-sdk`，它会依赖匹配版本的 `deepseek-harness-runtime-bin`。普通 SDK 运行不需要额外安装 Node.js，也不会自动下载完整 Office 工具链。

**重复实验必须锁定 SDK 版本。** 第一次运行可以先构建最新可安装版本，随后从输出的版本记录中确认具体版本，然后固定：

```bash
# 示例：请填写实际已经确认发布、能够安装的版本。
export DSH_SDK_VERSION="已核实的版本号"
bash scripts/run-docker.sh build
```

不要仅凭其他项目 Node 包的版本号推断 Python wheel 也有同名发布版本。

### 4.3 设置模型凭据

Linux Bash 下使用不进入历史命令的输入方式：

```bash
read -rs -p 'DeepSeek 测试 API Key: ' DEEPSEEK_API_KEY
echo
export DEEPSEEK_API_KEY

# 如果使用的是与官方不同的兼容 API endpoint，可以额外设置：
# export DEEPSEEK_BASE_URL='https://your-model-endpoint.example/v1'

# 模型 ID 必须是该 endpoint 实际提供的 ID
# export DSH_MODEL='deepseek-v4-flash'
```

脚本不会显示 Key，也不会把 Key 写进仓库。不过 Docker 守护进程管理员可以检查容器环境，因此不要将它视作高强度密钥保护机制。没有 Docker/Key 时请停在检查和单元测试，**不直接在宿主机以高权限执行**。

## 五、执行一次真实 Agent

```bash
bash scripts/run-docker.sh run
```

默认任务很简单：要求 Agent 通过 Bash 依次执行 `pwd`、`ls -la .`，然后用中文报告它实际看到了什么，不允许修改文件。

这刻意选择一个可以用确定性命令核对的任务，而不是开放式写作：当模型说“我已经查看目录”，我们可以根据日志判断它是否真的调用过 Bash，而不是只看最终答案。

**预期行为，不是已实测结果：**

```text
1. 脚本启动 dsh --profile sdk-minimal
2. Runtime 接收用户请求，准备模型可见的 Context 和工具 Schema
3. 模型可能调用 Bash 执行 pwd
4. Runtime 执行命令并接收工具结果
5. 模型可能继续调用 Bash 执行 ls -la .
6. 模型返回最终回答
7. Runtime 保存 Session 事件，SDK 返回 RunResult
```

模型不一定严格分两次调用工具；也可能把两条命令合并、拒绝工具调用或出错。后续学习应该以真实记录为准。

终端会打印：

- `SESSION_ID`：本次会话 ID。
- `FINISH_REASON`：例如 `completed` 或其他结束原因。
- `ROOT_EVENTS`、`NOTIFICATIONS`：SDK 报告的根会话事件和通知数量。
- `METADATA`：一份不含原始对话内容的 JSON 元数据路径。
- `FINAL_RESPONSE`：模型最终文本（可能包含用户数据，因此只在本地查看）。

文件通常存放在：

```text
jd-research-agent/
├── .local/                          # 已被本目录 .gitignore 忽略
│   ├── workspace/                   # Agent 可写的实验目录
│   ├── dsh-home/
│   │   ├── profiles/                # 运行 Profile 与补丁装配产物
│   │   └── sessions/                # 原生 JSONL 历史
│   └── results/
│       └── phase0-....json          # 不含原始 prompt 与工具参数的元数据
└── ...
```

如果运行失败，应保留错误类别并停止，不要因为创建了 `sessions/` 目录就认为任务成功。

## 六、怎样真正阅读 Session？

### 第一步：先只看事件结构

```bash
bash scripts/run-docker.sh inspect
```

`session_report.py` 扫描隔离 Home 下的 JSONL，仅统计每个文件的字节数、记录数、无效 JSON 行数和事件类型数量；它**不会输出原始 Prompt、工具参数、工具返回值或模型回复**。

根据官方 SDK，`RunResult.events` 仅包含根 Session 的事件，`RunResult.notifications` 还可能包含已知子 Agent 的树状通知。当前最小 Profile 无需引入子 Agent；后面研究多 Agent 时不能用根事件数代表整棵执行树。

注意事件的原生 JSON Schema 可能随 DSH 版本演进；本工具只读取常见 `kind/type/event_type` 字段，不能识别的类型显示为 `unknown`。这不是错误报告，也不能据此断言“没有工具调用”。

### 第二步：针对一条实际执行研究因果链

只在隔离环境、确认日志内容不涉及敏感数据时，打开对应 JSONL，查找下面四种信息：

| 观察对象 | 问题 |
| --- | --- |
| 用户输入事件 | Runtime 实际收到的任务是什么？ |
| 模型生成的工具调用 | 模型要求执行什么工具，参数是什么？ |
| 工具返回事件 | 真正执行后返回了什么？命令成功还是失败？ |
| 最终回答和 Turn 结束 | 模型是否根据刚才的工具结果作答？为什么结束？ |

**注意不能以“模型最终回答里提到 Bash”替代工具调用事件。**

本阶段最重要的观察结果，应该能够复述为：

```text
用户请求
  → 模型请求工具（Tool Call）
  → Runtime 执行工具（Execution）
  → 工具反馈（Tool Result）
  → 模型继续决策或回答
  → Session 落盘（Persistence）
```

### 第三步：对比三个容易混淆的概念

| 概念 | 本实验中怎样观察 | 它不代表什么 |
| --- | --- | --- |
| `RunResult` | 本次 `run()` 返回的 `final_response`、`finish_reason`、事件 | 不等于完整持久化执行历史 |
| Session JSONL | `dsh-home/sessions/` 下持久化的原生事件 | 不等于模型每一轮看到的完整 Context |
| Context | Runtime 为某轮模型请求组织的信息和工具 Schema | 不等于所有长期业务 State 或 Checkpoint |

接下来研究 Context、State 与恢复时，必须沿用这些区别。

## 七、为什么要显式禁用日志附加上传？

`config/disable-session-upload.patch.yml` 中设置：

```yaml
- id: session-log-deepseek
  config:
    enabled: false
```

该配置仅关闭 `session-log-deepseek` 插件将**未接受的 Session 事件作为附加字段**发送到 DeepSeek API 的行为。

它**不意味着**：

- 普通模型请求不再上传用户 Prompt（模型 API 必然需要输入）；
- 模型发起的工具调用与相应的后续模型请求不传输工具结果；
- 本地 `sessions/*.jsonl` 不再保存原始记录；
- 网络出站、遥测、其他插件或第三方 API 统统被禁用。

因此，这项补丁减少了额外的日志传输，并不解决所有隐私和网络风险。Profile 在启动时应用补丁，不应只编辑文件却继续复用旧进程。完成真实运行后还需检查当前 SDK 版本是否正确应用此补丁；如需严格证明未上传，要结合受控代理的实际请求记录核对，而不能把“配置存在”当作网络实测证据。

## 八、实验失败时怎样定位？

| 现象 | 优先检查 |
| --- | --- |
| `Docker daemon unavailable` | Docker 服务是否启动、账户是否有使用权限 |
| `DEEPSEEK_API_KEY missing` | 是否使用了单独的测试 Key，是否真正 `export` |
| 安装 SDK wheel 失败 | Linux 架构、Python 版本、PyPI 可用性、版本是否发布 |
| SDK 启动超时 | Runtime/profile 初始化、挂载目录是否可写、镜像依赖 |
| Provider 或 model 不支持 | 模型 ID 是否与配置端点一致；`deepseek-official` 路由是否可用 |
| Shell 或 PTY 初始化失败 | 容器权限限制、`/tmp`、PTY 支持；不要直接取消隔离并在宿主重试 |
| `finish_reason=error` | 实际终止原因和原生 Session 事件 |
| 没有任何 Session JSONL | 本次是否确实完成了 Runtime 初始化与持久化 |
| 只有最终答复、没有工具调用 | 模型可能未调用工具；基于原始事件判断，不能据此声称执行成功 |
| 无法解析部分 JSONL 事件 | 检查 DSH 版本与原生 Schema；统计器可能需要更新 |

**排错优先保证隔离完整。** 不要为了让 SDK 能跑，就直接删掉 `--read-only`、关闭所有权限限制，或将宿主用户主目录挂入容器。确实需要修改隔离选项时，应先定位具体失败原因并说明调整带来的风险。

## 九、实验报告模板与完成判定

实际运行后，复制下面这个模板，记录到本地实验报告中；只把审查过的脱敏结果提交仓库。

```markdown
# Phase 0 运行记录

- 实验日期：
- Linux / Docker 版本：
- DeepSeek Harness SDK / runtime 版本：
- 使用的模型 ID / endpoint 类型：
- 容器隔离配置：
- Session ID：
- 完成状态：已运行 / 失败 / 尚未运行

## 1. 实际观察

- SDK 返回 finish_reason：
- 最终回答摘要：
- Session JSONL 是否存在：
- 工具调用是否有真实事件证据：
- 工具执行的结果及错误（仅脱敏说明）：

## 2. 从执行轨迹看到的 Agent Loop

用户输入 → 模型决定 → 工具执行 → 工具结果 → 再次决策 / 最终响应

## 3. 能解释的机制

- Python SDK 和 dsh Runtime 各负责什么？
- Model Tool Call 与真正命令执行的分界点在哪里？
- RunResult 和 Session JSONL 的关系是什么？
- 哪些事实已经验证，哪些仍然只是预期？

## 4. 失败与改进

- 当前尚未解决的问题：
- 下个实验需要改变什么：
```

**阶段 0 完成的四个条件：**

1. 有明确版本、配置及隔离范围。
2. 至少一次模型请求真实完成，`RunResult` 可观察。
3. 存在对应 Session 的 JSONL 持久化事件。
4. 从事件中核实真实工具调用与返回，能说明一次循环中每个角色的职责；没调用工具就记录未达标。

如果只有脱离真实 API 的 FakeHarness 单元测试，属于**代码自测**，不属于 Agent 实验完成。

## 十、下一步：为什么不是直接加 MCP？

完成阶段 0 后，再进入阶段 1：给 Agent 提供 5～10 条固定、脱敏的完整 JD，让它读取文件并生成带证据的 `report.md`。届时可以实际比较：

- “仅在聊天里说报告完成了”与“工作目录真实存在报告”；
- “模型生成的技术要求”与“确实能够回查到职位原文”；
- “Agent 进行了工具调用”与“工具结果真的满足业务目标”。

有了这些差异，再引入受控岗位查询工具、Workflow、MCP，才能理解新组件究竟解决了什么问题。

---

## 主要依据

- [DeepSeek Harness：Python SDK 官方文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)
- [DeepSeek Harness：Python SDK 入门](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/python-sdk.md)
- [DeepSeek Harness：sdk-minimal 组合包说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/sdk-minimal/README.md)
- [DeepSeek Harness：Session-log DeepSeek 插件说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-log-deepseek/README.md)
- [DeepSeek Harness：安全声明](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md)

> 源码与配置会继续更新。关于安全和 Session 的具体判断，应同时对照运行时版本与实际事件，不要将本文的教学解释当作已经验证的生产保障。
