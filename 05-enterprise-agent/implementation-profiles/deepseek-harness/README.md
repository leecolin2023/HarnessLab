# DeepSeek Harness Implementation Profile

**目标：** 将 [IntraMate SRS](../../specifications/intramate/) 映射到 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 上的企业级实现。

## 研究重点

- DSH 的 Agent Loop、工具、Session、Cordis Plugin / Profile、Desktop、权限与 Sandbox，哪些能力已原生覆盖？
- 面对需求缺口，是配置、扩展插件、独立服务，还是不得不修改 Fork？
- 原生 Desktop 的应用标识、配置、数据路径和离线构建如何相互隔离？
- 上游更新后的版本兼容、回归测试和升级成本如何控制？

每个具体 SRS 使用 [Implementation Profile 模板](../implementation-profile-template.md)单独写映射方案，引用目标 `SRS-xxx` 及 `REQ/AC`。

**代码交付位置：** [leecolin2023/dsh-intramate](https://github.com/leecolin2023/dsh-intramate)。

> 仅为方案入口，尚未验证任何需求覆盖结论。
