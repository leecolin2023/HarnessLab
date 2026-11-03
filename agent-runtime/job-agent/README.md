# job-agent 工程解读入口

从现在起，**本目录只保留跨仓库导航**，不再维护 job-agent 的逐行代码解读；避免工程代码更新后两边产生不同版本。

- **项目架构、源码调用链、逐行代码解读**：[job-agent/docs/01-project-architecture-and-code.md](https://github.com/leecolin2023/job-agent/blob/main/docs/01-project-architecture-and-code.md)。
- **通用 Agent / Runtime 原理**：[agent-runtime/README.md](../README.md)。
- **Agent Loop 深入运行机制**：[agent-runtime/01-agent-loop-execution-mechanism.md](../01-agent-loop-execution-mechanism.md)。
- **学习路线和实验边界**：[agent-runtime/LEARNING_PATH.md](../LEARNING_PATH.md)。

分工原则：**具体代码的“这一行做什么、参数从哪里来、实际调用谁”放 job-agent；“为什么需要这个机制、换框架是否成立”放 HarnessLab。**
