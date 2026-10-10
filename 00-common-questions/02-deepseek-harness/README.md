# 02 · DeepSeek Harness｜常见问题

对应研究：[HarnessLab / 02-deepseek-harness](../../02-deepseek-harness/)。

**范围说明：** 这里以个人项目技术深挖、框架源码面试追问为主，不把 DSH 特有机制当成所有 Agent 的通用事实。

## 初始候选题单

- 为什么选择 DeepSeek Harness 作为 IntraMate 的实现基座，而不是自己写 Agent Loop？
- 一条工具调用从 Agent Runtime 到实际执行和 Observation 的调用链是什么？
- Cordis 在 DSH 架构中承担什么职责？与 Runtime、插件有什么边界？
- Desktop 层与底层 Agent 执行层如何交互？在哪里隔离用户数据和应用配置？
- 引入新工具或企业内网能力，优先使用哪些扩展点？什么情况下必须修改核心代码？
- 跟随上游更新时，怎样降低 Fork 的维护和回归风险？

研究入口：[architecture](../../02-deepseek-harness/architecture/)、[agent-runtime](../../02-deepseek-harness/agent-runtime/)、[cordis](../../02-deepseek-harness/cordis/)、[desktop](../../02-deepseek-harness/desktop/)、[plugin-system](../../02-deepseek-harness/plugin-system/)。

> 回答源码问题应记录对应仓库、版本和关键代码路径。
