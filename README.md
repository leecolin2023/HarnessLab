# HarnessLab

**Agent Harness Engineering Lab · 智能体运行框架工程学习与实践实验室**

> 以 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 为当前主要研究对象，通过源码追踪、机制复现、跨框架比较和真实任务评测，为企业内网 Agent 产品（目前为 [dsh-intramate](https://github.com/leecolin2023/dsh-intramate)）提供有证据的技术依据。具体框架可更换，稳定需求不依附于某个框架。

## 仓库边界

- **HarnessLab**：机制研究、源码定位、对照实验、企业需求规格、框架实现方案以及工程决策记录。
- **dsh-intramate**：基于 DeepSeek Harness 的具体产品源码、实现、构建、测试和发布。
- **[AgentGuide](https://github.com/adongwanai/AgentGuide)**：学习资源与技术图谱参考，不将资源列表视为已完成的学习成果。

## 知识分类与导航

| 分类 | 核心问题 | 内容 |
| --- | --- | --- |
| [01 · Agent 核心机制](./01-agent-mechanisms/) | Agent 为什么能完成任务？ | Agent Loop、Tool Calling、Context Engineering |
| [02 · DeepSeek Harness 源码](./02-deepseek-harness/) | DSH 如何实现这些机制？ | Architecture、Cordis、Agent Runtime、Desktop、插件体系 |
| [03 · Harness 横向比较](./03-harness-comparison/) | 为什么其他框架设计不同？ | Claude Code、Codex、OpenCode、Pi |
| [04 · 实验与评测](./04-experiments/) | 实际行为与性能能否验证？ | Tool Calling、长程任务、Benchmarks |
| [05 · 企业 Agent 场景与规格](./05-enterprise-agent/) | 企业内网需要什么？如何跨框架实现？ | 业务场景、[需求规格 SRS](./05-enterprise-agent/specifications/)、[框架实现方案](./05-enterprise-agent/implementation-profiles/) |
| [06 · 工程决策](./06-engineering-decisions/) | 哪些能力该复用、适配或自建？ | Build vs Reuse、IntraMate 集成决策 |

## 需求与框架解耦

同一份产品需求可以由多个技术栈实现，**不要在 SRS 中把当前 DSH 实现写成业务需求**：

1. [企业场景](./05-enterprise-agent/)：定义问题、用户、环境、风险、外部约束。
2. [技术无关 SRS](./05-enterprise-agent/specifications/)：固定需求 ID、功能/非功能要求、验收标准、变更历史。
3. [不同框架实现方案](./05-enterprise-agent/implementation-profiles/)：按 DSH、LangGraph 等分别映射 SRS，记录框架版本、原生能力、缺口、扩展点及验证方法。
4. [实验](./04-experiments/)：验证技术选择是否达到相同的验收标准。
5. [工程决策](./06-engineering-decisions/)：记录复用、薄适配、自建和选型的依据。
6. 产品仓库：按已确认的实现方案开发，并用 Issue / PR / 测试链接回溯到 SRS 及验收项。

切换框架时应优先保留 SRS 和验收语义；**若实际业务目标、约束或产品范围改变，则仍须修订 SRS**。

## 推荐学习顺序（可随时改变）

默认建议：**核心机制 → DSH 实现 → 横向比较 → 实验验证 → 企业场景 → 工程决策**。

这只是初始导航，不是强制阶段门禁。可以从真实问题进入任意模块，需求澄清与实验也可以并行迭代。

**编号约定**：

1. 一级目录的两位数字是**稳定的知识分类位置**，不是任务优先级、学习进度或实施先后约束。
2. 子主题按语义命名，原则上不编号；正式需求文件则使用**独立、稳定的需求 ID**。
3. 仅学习顺序改变时，更新 README 导航即可，**不批量重命名目录**。
4. 分类边界确实变化时，可使用 `git mv`，同步核对相对链接和产品仓库引用。
5. 如果未来目录频繁重排，可取消一级目录编号，以 README 顺序作为导航来源。

## 研究产物规则

- **机制理解**：记录问题、入口、实际调用链、关键边界、源码或文档证据。
- **实验验证**：记录版本 / commit、环境、模型、任务输入、指标、执行过程与失败样本；未运行的实验只标记“计划”。
- **跨框架比较**：尽量保持任务、模型、预算与指标一致，区分已证实事实、推断与实测。
- **需求规格**：描述“应具备什么、在何种约束下、怎样判定完成”；明确状态、ID、证据和变更历史。
- **实现方案**：记录同一需求在不同框架的实现路径、偏差、验证结果和升级风险。
- **工程决策**：明确复用 / 薄适配 / 自建 / 暂缓的依据及重新评估条件。
- **产品交付**：实际实现与发布在对应产品仓库，不将建议或设计稿标记为已交付。

当前状态：**研究入口与规格模板已初始化，不代表实验、需求批准或产品实现已经完成。**
