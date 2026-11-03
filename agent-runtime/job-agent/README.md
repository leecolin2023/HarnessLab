# job-agent｜代码阅读与架构理解

此目录只保存 **job-agent 工程的学习解读**。运行代码、Docker 配置、实验脚本及 CI 统一维护在 [leecolin2023/job-agent](https://github.com/leecolin2023/job-agent)，不在 HarnessLab 复制。

## 阅读顺序

**[01｜读懂 job-agent：项目整体架构与核心代码](./01-project-architecture-and-code.md)**

第一篇文章先对应 [Agent Runtime 的最基本执行循环](../README.md#二为了完成工作任务agent-需要具备哪些能力)，解释 **模型决策 → 工具执行 → 反馈 → 继续或结束** 分别由哪些代码承担，再讨论复杂工作中的显式规划、计划修订、业务验证与人工审批。

| 分层 | 原理能力 | job-agent 当前情况 |
| --- | --- | --- |
| **基本执行循环** | 模型决策 | DSH 的 Agent Loop 解析模型输出、识别 Tool Call；本项目尚无真实模型轨迹 |
| **基本执行循环** | 工具执行 | DSH 的 Tool Executor 与 Bash 工具执行；Docker 提供隔离环境 |
| **基本执行循环** | 反馈 | DSH 的工具结果与 Session 机制支持后续模型调用；本项目的日志脚本只做事后统计 |
| **基本执行循环** | 继续或结束 | DSH 控制 Step/Turn；job-agent 读取 `RunResult`，不负责内部循环 |
| **复杂任务增强** | 显式规划 | 没有独立 Planner，`sdk-minimal` 未装配 Plan Mode |
| **复杂任务增强** | 计划修订 | 没有计划数据结构、进度与修订控制器 |
| **复杂任务增强** | 业务结果验证 | 只检查运行状态，没有检查目标是否完成的 Checker |
| **复杂任务增强** | 人工审批 | 有部分容器隔离措施，没有独立的业务审批工作流 |

[查看第一篇文章中的完整原理—代码对照及源码依据](./01-project-architecture-and-code.md)。

以上是**依据当前源码和官方组件说明的实现判断**，不是基于真实模型 Session 的实测结果。

阅读后应能回答：

- job-agent 与 DeepSeek Harness Python SDK、dsh Runtime、模型 API 的关系是什么？
- `scripts/run-docker.sh`、`src/run_phase0.py` 和 `src/session_report.py` 分别做什么？
- 为什么一次 `harness.run()` 看不到 Agent Loop 的内部实现？
- `RunResult`、原生 Session JSONL、元数据摘要之间的区别是什么？
- 为什么离线 CI 通过还不能说明 Agent 已经执行工具或完成岗位分析？

## 后续写作原则

**先解释基本执行循环，再根据真实任务引出增强机制**；对应源码时明确应用代码、SDK、Runtime 各自承担什么。发现原理与实现事实冲突时同步修订原理，不将可选增强机制写成每次执行的必经步骤。后续再依据真实执行记录研究 Agent Loop、工具调度、Context、State 和异常恢复。所有声称“已运行”的结论必须能对应到真实 Session 或测试日志；还没实现的岗位检索、RAG、MCP、报表和多 Agent 协作必须明确标注为未来规划。

通用原理参见 [Agent Runtime 总入口](../README.md)；完整进阶课程参见 [学习路线](../LEARNING_PATH.md)。
