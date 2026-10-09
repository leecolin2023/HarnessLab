# LangGraph / LangChain Ecosystem Implementation Profile

**目标：** 分析同一套 [IntraMate SRS](../../specifications/intramate/) 能否在 LangChain 生态、尤其 LangGraph 的有状态编排能力上实现。

## 边界提醒

- **LangChain** 可用于模型、工具、检索及应用集成；**LangGraph** 更聚焦状态化编排、执行流程及持久化等能力。
- 与 DSH 这样的成熟 Harness/应用栈不是一一对应关系。需要明确由哪些其他组件补齐 Desktop、权限、Sandbox、模型路由、可观测性与发布能力。
- 在尚未选型或实现前，这里只保存候选方案和待验证问题，不把路线视为已批准架构。

每份方案按 [Implementation Profile 模板](../implementation-profile-template.md)建立到 `SRS / REQ / AC` 的映射，并标注组件缺口、集成成本和验证结果。

> 仅为候选技术路线入口；没有已批准的 LangGraph 实现。
