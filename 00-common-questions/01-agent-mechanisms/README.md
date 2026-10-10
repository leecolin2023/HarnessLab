# 01 · Agent 核心机制｜常见问题

对应研究：[HarnessLab / 01-agent-mechanisms](../../01-agent-mechanisms/)。

## 初始候选题单

- Agent 与普通 LLM Chat、预设 Workflow 的本质区别是什么？什么场景不应使用 Agent？
- 一次完整的 Agent Loop 如何串起模型输出、Tool Call、工具结果和下一轮推理？
- Function Calling 与工具实际执行是什么关系？参数 Schema、工具权限分别由谁保证？
- 什么是 Context Engineering？为什么长会话需要截断、摘要或 Compaction？
- 工具调用失败、输出不可信或发生循环时，Harness 应怎样处理？
- Agent 的规划、记忆、任务持久化分别在哪一层实现？哪些不是模型本身的能力？

## 讨论侧重点

先给面试可用的最小机制解释，再用具体消息或工具执行链进行验证；需要读源码时在原研究目录留证据。本页仅为候选题，不表示已有答案。
