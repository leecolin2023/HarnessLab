# 00 · 常见问题与面试讨论

**定位：** 以问题为入口组织知识，初期聚焦技术面试高频题，同时容纳日常工程疑问、项目复盘和跨主题讨论。

本目录回答“这个问题怎样讲清楚、怎样被追问、还有哪些没有弄懂”；仓库原有 01–06 目录负责**机制研究、源码、实验和工程证据**，避免复制一套深度研究材料。

## 分类导航

| 分类 | 面试 / 讨论范围 | 对应深度研究 |
| --- | --- | --- |
| [01 · Agent 核心机制](./01-agent-mechanisms/) | Agent Loop、Tool Calling、Context Engineering | [01-agent-mechanisms](../01-agent-mechanisms/) |
| [02 · DeepSeek Harness](./02-deepseek-harness/) | 具体 Harness 架构、源码实现、个人项目追问 | [02-deepseek-harness](../02-deepseek-harness/) |
| [03 · Harness 横向比较](./03-harness-comparison/) | Claude Code / Codex / OpenCode / Pi / DSH 技术取舍 | [03-harness-comparison](../03-harness-comparison/) |
| [04 · 实验与评测](./04-experiments/) | 如何设计评测、判断 Agent 是否可靠 | [04-experiments](../04-experiments/) |
| [05 · 企业 Agent](./05-enterprise-agent/) | RAG、离线部署、Office、权限、银行业务场景 | [05-enterprise-agent](../05-enterprise-agent/) |
| [06 · 工程决策](./06-engineering-decisions/) | Build vs Reuse、可靠性、架构权衡、技术债 | [06-engineering-decisions](../06-engineering-decisions/) |
| [07 · 后端开发](./07-backend-development/) | 通用基础、Python、Java | 独立补充 |
| [08 · LeetCode 算法](./08-leetcode/) | 数据结构、算法思想、复杂度、手写代码 | 独立补充 |

> 01–06 **编号对应，不意味着每一个问题都要同时写两份**。对于还没有研究资料的问题，保留待验证状态即可。

## 一道问题如何沉淀

1. **提出问题**：用面试官或实际工作中的原始问法，不先写假设结论。
2. **简要回答**：先尝试 30–60 秒清楚解释，必要时补充 3–5 分钟深入版。
3. **机制与边界**：说明为什么成立、关键过程、反例、适用前提和追问。
4. **证据与实践**：引用代码、文档、实验，或记录尚未验证的假设。
5. **回链深读**：需要源码与真实实验时，链接到对应 01–06 研究目录；反过来也可链接回来。

## 文档约定

- 一道值得反复讨论的问题单独一个 Markdown 文件；起步先维护各分类 README 中的**候选题单**，按需拆分，不批量创建空文章。
- 使用 [QUESTION_TEMPLATE.md](./QUESTION_TEMPLATE.md) 作为单题模板；可按问题类型删减小节。
- 文件名采用简洁的小写英文短横线（如 `how-tool-calling-works.md`）；LeetCode 题解优先采用 `0001-two-sum.md`。
- 状态使用 **待讨论 / 讨论中 / 已验证**。写出“参考答案”不等于已经通过源码、测试或实践验证。
- 对具有时效性的框架实现与模型表现，标注版本、日期或 commit；不把推断当作事实。

当前状态：**完成目录与候选题单初始化，题目尚不代表已完成解答。**
