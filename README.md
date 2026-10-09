# HarnessLab

**Agent Harness Engineering Lab · 智能体运行框架工程学习与实践实验室**

> 以 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 为主研究对象，结合源码追踪、机制复现、跨框架比较和实验评测，为 [dsh-intramate](https://github.com/leecolin2023/dsh-intramate) 提供有证据的工程决策依据。

## 仓库边界

- **HarnessLab**：研究问题、机制解释、源码定位、对比、可复现实验与工程决策记录。
- **dsh-intramate**：产品代码、具体集成、构建和发布；不在此仓库重复搭建一个 Harness。
- **[AgentGuide](https://github.com/adongwanai/AgentGuide)**：学习资源与技术图谱的参考，不将资源清单当作已完成学习。

## 知识分类与导航

| 分类 | 核心问题 | 内容 |
| --- | --- | --- |
| [01 · Agent 核心机制](./01-agent-mechanisms/) | Agent 为什么能完成任务？ | Agent Loop、Tool Calling、Context Engineering |
| [02 · DeepSeek Harness 源码](./02-deepseek-harness/) | DSH 如何实现这些机制？ | Architecture、Cordis、Agent Runtime、Desktop、插件体系 |
| [03 · Harness 横向比较](./03-harness-comparison/) | 为什么其他框架设计不同？ | Claude Code、Codex、OpenCode、Pi |
| [04 · 实验与评测](./04-experiments/) | 实际行为与性能能否验证？ | Tool Calling、长程任务、Benchmarks |
| [05 · 企业 Agent 场景](./05-enterprise-agent/) | 企业内网有哪些特殊要求？ | 离线部署、Office 能力、银行 Skills |
| [06 · 工程决策](./06-engineering-decisions/) | 哪些能力该复用、适配或自建？ | Build vs Reuse、IntraMate 集成决策 |

## 推荐学习顺序（可随时改变）

默认建议：**核心机制 → DSH 实现 → 横向比较 → 实验验证 → 企业场景 → 工程决策**。

这只是初始导航，不是强制阶段门禁。可以从任何真实问题进入：例如分析 Desktop 数据隔离时，先研究 `02` 与 `05`，设计验证实验放在 `04`，最后在 `06` 记录决策。

**编号约定**：

1. 一级目录的两位数字是**稳定的知识分类位置**，不是任务优先级、学习进度或执行先后约束。
2. 子主题按语义命名，原则上不编号；新增主题直接放入对应领域。
3. 如果只是学习顺序改变，修改此 README 导航即可，**不要批量重命名目录**。
4. 如果分类边界确实变化，再采用 `git mv` 调整路径，并同步检查相对链接、引用和历史笔记；已有材料保留 Git 历史。
5. 如未来目录变动频繁，可去掉一级目录数字，以 README 导航顺序作为唯一顺序来源；分类的含义比数字更重要。

## 研究产物规则

- **机制理解**：记录问题、入口、实际调用链、关键边界、源代码或文档证据。
- **实验验证**：记录版本 / commit、环境、模型、任务输入、指标、执行过程与失败样本；没有跑过的实验只能标为“计划”。
- **跨框架比较**：尽量保证相同任务、模型与评价口径，并区分文档陈述、推断和实测。
- **工程决策**：依据证据明确“复用 / 薄适配 / 自建 / 暂缓”，注明适用条件与需要重新评估的触发条件。
- **企业适配**：只在此讨论需求、约束与证据，真实产品变更在 `dsh-intramate` 实施。

当前状态：**仓库结构已初始化，以下主题均为研究入口，不代表相关研究已经完成。**
