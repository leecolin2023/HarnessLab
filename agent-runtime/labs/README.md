# Agent Runtime 实践区（Labs）

这里存放**具体 Agent 框架及其应用案例**，与上一级 `agent-runtime/` 的通用原理文章分开维护。

学习顺序请先阅读 [Agent Runtime 完整学习路线](../LEARNING_PATH.md)。

## 目录职责

```text
agent-runtime/
├── README.md                  # 通用原理：Agent 与 Runtime
├── LEARNING_PATH.md           # 实践与原理的学习路线
├── <其他原理文章>.md
└── labs/
    ├── README.md              # 本文件
    ├── deepseek-harness/
    │   └── jd-research-agent/
    │       └── README.md      # 第一个贯穿案例
    └── <未来其他框架>/
        └── <对应Agent项目>/
```

本目录不是“第二套 Agent Runtime 理论”，而是对上级原理进行**具体实现、观察、比较和验证**的地方。

## 新建一个案例的原则

- 一个 Agent 应用占一个独立目录，同一个框架下可以有多个 Agent 项目。
- 框架特定的配置、SDK 示例、工具实现和实验记录留在应用目录。
- Context、State、Agent Loop、Workflow、MCP 等一般机制以根目录原理文章为准；实验 README 引用它们，不重复维护通用理论。
- 执行结果与实验报告必须标注真实使用的 SDK、模型、Profile、数据和代码版本，不把规划视为已实现。
- 严格处理凭据、原始 Session 日志、业务数据和命令执行权限；不上传敏感内容。

## 当前案例

**[DeepSeek Harness · JD Research Agent](./deepseek-harness/jd-research-agent/README.md)**

从受控本地 SDK 任务开始，逐步引入工具、任务规划、校验、MCP、上下文、恢复与评测。后续加入其他框架（例如 AgentScope）时，可以重新实现相同任务并对照 Runtime 机制，而不是复制根目录的知识文章。

> 当前仅建立学习路线与项目说明；尚未提交应用代码、自动化测试或实测结果。
