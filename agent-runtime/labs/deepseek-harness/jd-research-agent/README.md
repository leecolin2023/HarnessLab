# JD Research Agent｜DeepSeek Harness 实践案例

> 目的：先使用 DeepSeek Harness Python SDK 构建一个可以运行的岗位研究 Agent，再根据真实执行轨迹理解 Agent Loop、Tool Calling、Workflow、Context、Session、恢复、安全与评测。
>
> 状态：**阶段 0 的 Docker 隔离启动脚本、最小 SDK 调用、Session 结构分析器、离线单元测试和学习文档已入库；当前运行环境缺少 Docker 守护进程及模型 API Key，尚未完成真实 SDK/模型实测。**

## 学习入口

- **[实验 00：隔离运行 SDK、观察 Agent Loop 与 Session 日志](./PHASE0_LEARNING.md)** — 本阶段具体操作与原理互动教学
- [Docker 运行入口](./scripts/run-docker.sh) · [SDK 调用代码](./src/run_phase0.py) · [Session 观察工具](./src/session_report.py) · [禁用附加日志上传的补丁](./config/disable-session-upload.patch.yml)

- [完整学习路线：从应用到运行机制](../../../LEARNING_PATH.md)
- [Agent Runtime：什么是 Agent，为什么需要 Runtime？](../../../README.md)
- [现有原理：Harness 中的上下文管理](../../../01-harness-context-management.md)
- [DeepSeek Harness 官方 Python SDK 入门](https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk)
- [DeepSeek Harness 官方架构参考](https://deepseek-harness.github.io/deepseek-harness/reference/)

## 最终业务任务

用户提出：

> 统计岗位职责或者任职要求出现 RAG 的岗位中，相关的技术要求是什么？

逐步把任务扩展为：检索完整岗位、按职位 ID 去重、区分必备与加分技术、统计具体技术要求、保留原文证据、生成可复核的 Markdown 报告，并在失败时能记录原因、修复或停止。

**先使用少量脱敏完整 JD 的固定快照，不直接操作 job-rag 的主数据库或私有数据。** 第一阶段只做单 Agent，不预先搭建多 Agent 平台。

## 分阶段构建

| 阶段 | 应用侧增加什么 | 本轮需要解释什么 | 必须留下的证据 |
| --- | --- | --- | --- |
| 0 | 在隔离环境运行 SDK 最小任务 | SDK、Profile、Runtime、Session 的关系 | 配置、版本、返回文本、Session 日志 |
| 1 | 读取固定小样本并输出 `report.md` | 模型回答与真实任务完成的区别 | 实际文件、对应证据、调用记录 |
| 2 | 加入岗位查询与原文读取工具 | Tool Calling 与真正执行的边界 | 参数、返回值、错误记录 |
| 3 | 加入 Planner、Checker、有限修复循环 | Workflow Loop 与 Agent Loop 的区别 | 规划、校验、重试记录 |
| 4 | 将查询能力以 MCP 接入 | MCP、API、工具注册与权限 | 工具发现和调用对照 |
| 5 | 处理更大 JD 集与历史压缩 | Context、选择、压缩、信息损失 | 同一数据上的上下文对照 |
| 6 | 运行跨 Session 与中断恢复实验 | State、Session、Checkpoint、Resume | 中断点与恢复后的状态 |
| 7 | 注入故障并设置权限 | Retry、幂等、Sandbox、审批 | 明确的失败或拦截证据 |
| 8 | 建立真实 JD 评测 | 任务级结果与执行轨迹评价 | Gold 样本、指标、错误分析 |
| 9 | 通过受控服务入口提供能力 | 本地 Agent 与在线服务的区别 | 访问控制、日志、任务隔离 |
| 10 | 迁移到另一 Agent/框架 | 通用机制与框架私有设计 | 同一任务的机制对照 |

以上所有阶段的**完整教学内容、原理追问、实验设计和验收规则**都在上级 `LEARNING_PATH.md` 中，本文件只维护本案例自身的进度及运行入口，避免重复。

## 当前阶段 0 已建立的目录与文件

```text
jd-research-agent/
├── README.md
├── PHASE0_LEARNING.md                # 阶段 0 完整教程：实践、观察、原理、验收
├── docker/Dockerfile                 # Python 3.12、DeepSeek Harness SDK 和匹配 runtime
├── config/
│   └── disable-session-upload.patch.yml
├── scripts/run-docker.sh            # check / test / build / run / inspect
├── src/
│   ├── run_phase0.py                # 真实 SDK 运行入口
│   └── session_report.py            # 仅分析 Session 事件结构
├── tests/test_phase0.py             # 离线 Fake SDK 与日志分析测试
├── .gitignore
└── .local/                           # 只在真实运行后本地生成，不入库
    ├── workspace/
    ├── dsh-home/
    └── results/
```

未来阶段需要完整 JD 样本、工具实现、实验评测时，再按需新增 `fixtures/`、`experiments/` 等目录。本次没有创建这些空目录。**本阶段的完整教程见 `PHASE0_LEARNING.md`。**

## 第一轮实际任务：先完成阶段 0，再进入阶段 1

1. 按 [实验 00](./PHASE0_LEARNING.md) 在 Linux + Docker 中执行 `bash scripts/run-docker.sh check`、`test`、`build`、`run`、`inspect`。仅指定 `cwd` 不等于沙箱。
2. 用 Docker 镜像安装匹配的 `deepseek-harness-sdk` 与 Runtime，记录版本、模型 ID 和容器隔离措施；`sdk-minimal` 不等于多 Agent 产品配置。
3. 在隔离环境内先执行一项无需真实 JD 的只读演示任务，观察返回内容与 `dsh_home/sessions/` 的 JSONL。
4. 提供 5～10 条脱敏、完整的 JD 样本（含稳定 ID），让 Agent 在一次工作任务中输出一个真实存在的 `report.md`。
5. 检查报告是否引用了对应样本、是否误把“加分”写成“必备”；记录模型实际访问过的文件和工具调用。
6. 写一份运行记录，说明哪些事实是从日志、文件与工具返回中看到的，哪些只是推测；然后再完善 Agent Loop 原理文章。

### 安全说明

DeepSeek Harness 官方 `sdk-minimal` 当前采用 `danger-full-access`，Shell 访问不限制在 `cwd`。官方还说明部分未接受的 Session 日志事件默认可能随模型请求上传。不能在含有敏感文件、登录凭据或企业数据的宿主环境中直接运行未经隔离的实验。参考 [官方 SDK 文档](https://deepseek-harness.github.io/deepseek-harness/guide/python-sdk) 配置及禁用相关日志上传；要使用真实数据须先核查模型端点、权限和合规边界。

## 阶段记录模板

每轮实验应写明：

- 本次希望完成的业务任务及数据快照。
- 实际所用 SDK/Runtime、模型、Profile 和代码版本。
- 执行动作、工具输入输出和脱敏后日志位置。
- 实际生成的文件和是否通过检查。
- 从本次现象引出的一个机制问题，及通用原理文章的链接。
- 未验证的部分、失败原因和下一个改动。

**不要因为示例代码已写好，就把阶段标记为通过；必须等到实际运行并保存证据。**
