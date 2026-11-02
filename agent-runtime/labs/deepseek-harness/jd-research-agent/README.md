# JD Research Agent｜DeepSeek Harness 实践案例

> 目的：先使用 DeepSeek Harness Python SDK 构建一个可以运行的岗位研究 Agent，再根据真实执行轨迹理解 Agent Loop、Tool Calling、Workflow、Context、Session、恢复、安全与评测。
>
> 状态：**项目规划已建立；尚未写入执行代码，亦未完成实测。**

## 学习入口

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

## 开发时逐步加入的目录

```text
jd-research-agent/
├── README.md
├── src/                    # 程序入口、任务与受控工具
├── configs/                # 可提交的非敏感配置示例
├── fixtures/               # 脱敏、固定的完整 JD 示例
├── experiments/            # 各阶段假设、运行记录和评测
└── outputs/                # 本地结果；必须检查后才可公开
```

上述子目录**尚未创建**；只有开始相应工作时才建立。真正执行前需要准备忽略规则，防止凭据、Session 原始日志或含敏感信息的结果进入公开 Git。

## 第一轮实际任务：只完成阶段 0—1

1. 准备一台容器或虚拟机等**真实隔离环境**，其可访问文件、凭据与网络范围可控。仅指定 `cwd` 不等于沙箱。
2. 按官方文档安装 `deepseek-harness-sdk`，记录 SDK 与运行时版本，选择与 API 端点匹配的模型；使用 `sdk-minimal`，不要假定它默认包含 MCP 或多 Agent 组件。
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
