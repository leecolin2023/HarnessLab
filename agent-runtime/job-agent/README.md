# job-agent｜代码阅读与架构理解

此目录只保存 **job-agent 工程的学习解读**。运行代码、Docker 配置、实验脚本及 CI 统一维护在 [leecolin2023/job-agent](https://github.com/leecolin2023/job-agent)，不在 HarnessLab 复制。

## 阅读顺序

**[01｜读懂 job-agent：项目整体架构与核心代码](./01-project-architecture-and-code.md)**

第一篇文章将 [Agent Runtime 的五种能力](../README.md#二为了完成工作任务agent-需要具备哪些能力) 与 job-agent 的**真实实现**逐项对应：哪些来自应用代码，哪些来自 DSH Runtime，哪些仅是能力接口，哪些尚未实现。然后再分析工程边界、核心函数与调用链。

| 原理能力 | 当前项目情况 | 代码解读入口 |
| --- | --- | --- |
| 任务规划 | **未实现显式 Planner / Plan Mode** | [为什么当前没有独立规划](./01-project-architecture-and-code.md#1-任务规划当前没有独立实现) |
| 行动决策 | DSH 提供模型决策与工具调用路径，未完成真实运行验证 | [模型和 Runtime 在哪里选择行动](./01-project-architecture-and-code.md#2-行动决策发生在模型与-dsh-runtime不在-python-入口) |
| 工具执行 | DSH 装配 Bash 与 Tool Executor，容器提供边界 | [工具如何执行](./01-project-architecture-and-code.md#3-工具执行项目提供环境dsh-提供工具及执行器) |
| 反馈调整 | Runtime 有反馈通道，应用未实现独立重规划 | [反馈与修正区别](./01-project-architecture-and-code.md#4-反馈调整有工具结果通路但还没验证自我纠错) |
| 结果验证 | 只检查运行状态，没有业务成功 Checker | [运行完成不等于任务成功](./01-project-architecture-and-code.md#5-结果验证只有运行状态检查没有业务成功判定) |

以上是**依据当前源码和官方组件说明的实现判断**，不是基于真实模型 Session 的实测结果。

阅读后应能回答：

- job-agent 与 DeepSeek Harness Python SDK、dsh Runtime、模型 API 的关系是什么？
- `scripts/run-docker.sh`、`src/run_phase0.py` 和 `src/session_report.py` 分别做什么？
- 为什么一次 `harness.run()` 看不到 Agent Loop 的内部实现？
- `RunResult`、原生 Session JSONL、元数据摘要之间的区别是什么？
- 为什么离线 CI 通过还不能说明 Agent 已经执行工具或完成岗位分析？

## 后续写作原则

**先按通用原理提出的能力逐项核对现有实现**，再解释代码怎样协作；当发现通用原理把可选机制误写成必备步骤时，同步修订原理文章。后续再依据真实执行记录研究 Agent Loop、工具调度、Context、State 和异常恢复。所有声称“已运行”的结论必须能对应到真实 Session 或测试日志；还没实现的岗位检索、RAG、MCP、报表和多 Agent 协作必须明确标注为未来规划。

通用原理参见 [Agent Runtime 总入口](../README.md)；完整进阶课程参见 [学习路线](../LEARNING_PATH.md)。
