# Implementation Profiles · 框架实现方案

本目录解决“**同一份已明确的产品需求，在不同技术栈下怎样实现？**”而不是重新定义业务需求。

## 路线

- [DeepSeek Harness](./deepseek-harness/)：当前 IntraMate 的 DSH Fork，优先原生功能、Cordis 插件 / Profile patch、必要时最小 Fork 改动。
- [LangGraph](./langgraph/)：LangChain 生态中的 Agent 工作流/有状态编排路线；**并非一套开箱即用的完整桌面 Harness**，需要单独界定模型、工具、安全、会话、应用壳和交付能力。
- 以后如选择其他运行框架，再新增并列的实现目录，不改原 SRS。

## 最小实现方案内容

为每条候选路线按 [implementation-profile-template.md](./implementation-profile-template.md)记录：目标 SRS ID 与版本、框架版本/commit、原生覆盖、缺口、适配层、风险、验证案例及迁移/回滚路径。

**要求：** 框架选择可以变化，但功能需求、非功能约束和验收项仍由 [specifications](../specifications/)管理。若技术限制迫使产品需求降级，必须把差异暴露为待批准的偏差，而不是默默修改 SRS。

对应的性能实验放在 [04-experiments](../../04-experiments/)；选型理由与正式决定放在 [06-engineering-decisions](../../06-engineering-decisions/)。

> 当前仅创建方案入口和模板，不代表任何实现已经完成。
