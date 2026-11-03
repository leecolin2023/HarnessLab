# job-agent｜代码阅读与架构理解

此目录只保存 **job-agent 工程的学习解读**。运行代码、Docker 配置、实验脚本及 CI 统一维护在 [leecolin2023/job-agent](https://github.com/leecolin2023/job-agent)，不在 HarnessLab 复制。

## 阅读顺序

**[01｜读懂 job-agent：项目整体架构与核心代码](./01-project-architecture-and-code.md)**

第一篇文章完整分析 job-agent 目前的工程边界、目录职责、系统架构、一次任务的调用链，以及每份核心代码为何存在、如何配合、实际验证到了哪一步。

阅读后应能回答：

- job-agent 与 DeepSeek Harness Python SDK、dsh Runtime、模型 API 的关系是什么？
- `scripts/run-docker.sh`、`src/run_phase0.py` 和 `src/session_report.py` 分别做什么？
- 为什么一次 `harness.run()` 看不到 Agent Loop 的内部实现？
- `RunResult`、原生 Session JSONL、元数据摘要之间的区别是什么？
- 为什么离线 CI 通过还不能说明 Agent 已经执行工具或完成岗位分析？

## 后续写作原则

先解释 **现有代码是什么、怎样工作、为什么这样分层**，再依据真实的执行记录讨论 Agent Loop、工具调度、Context、State 和异常恢复。所有声称“已运行”的结论必须能对应到真实 Session 或测试日志；还没实现的岗位检索、RAG、MCP、报表和多 Agent 协作必须明确标注为未来规划。

通用原理参见 [Agent Runtime 总入口](../README.md)；完整进阶课程参见 [学习路线](../LEARNING_PATH.md)。
