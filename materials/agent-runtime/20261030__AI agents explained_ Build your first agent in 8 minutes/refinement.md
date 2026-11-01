# AI Agent 详解：8 分钟构建你的第一个 Agent

> 来源：Google Cloud Tech，Smitha Kolan，**Modern AI Agents: From Theory to Production**（6/6）  
> 时长：08:29｜原始语言：英语｜处理方式：英文字幕忠实翻译与表达整理（Transcript Refinement）  
> [原视频](https://www.youtube.com/watch?v=Zqno_vux6d8)｜[英文转写底稿](https://github.com/leecolin2023/ingest2md/blob/main/output/20261030__Modern%20AI%20Agents%20-%20From%20Theory%20to%20Production/20261030__AI%20agents%20explained_%20Build%20your%20first%20agent%20in%208%20minutes/content.md)
>
> 说明：中文稿保留原讲解顺序、组件名称、数量和示例；章节时间戳沿用字幕原稿，不代表逐句精确对齐。原始字幕未包含屏幕上的完整代码和命令，本文不补造代码。

## [00:00 什么是 AI Agent？](https://www.youtube.com/watch?v=Zqno_vux6d8&t=0s)

这期视频不仅介绍 AI Agent 的概念，还会使用 Google 的开发工具包，一步步构建第一个 Agent。看完之后，你将理解 Agent 如何推理、采取行动和调整策略，并获得一套可以自己运行的示例代码思路。

最简单地说，**Agent 是一种不仅能够回答问题，还能决定采取什么行动并实际执行的软件**。传统聊天机器人通常生成一次回答，而 Agent 会检查用户的请求，判断需要哪些步骤，可能调用 API、运行代码、查看结果，然后决定下一步做什么。

关于这种工作方式，一个经典来源是研究论文《ReAct: Synergizing Reasoning and Acting in Language Models》。其基本思想是：语言模型不一定只进行一次性文本生成，也可以逐步推理，执行调用工具或 API 等动作。

## [01:05 ReAct 框架如何工作？](https://www.youtube.com/watch?v=Zqno_vux6d8&t=65s)

模型采取行动之后，观察执行结果，再决定下一步。这种**推理、行动、观察、调整**的循环，是许多现代 Agent 的基础。它也符合 Agent 的一个常见特征：系统通过推理、规划和记忆获得一定程度的自主性，能够适应变化，并代表用户作出决定。

不过，并不是所有 Agent 都采用相同的执行方式。可以将它们概括为三种常见模式：

- **顺序型（Sequential）**：像流水线一样依次执行步骤一、步骤二、步骤三，可预测，但不够灵活。
- **反应型（Reactive）**：根据当前状态决定下一步，这次可能使用工具 A，下次改用工具 B；适应性较强，但不一定提前规划。
- **规划型（Planning / Deliberative）**：先拟定计划，再按计划执行。

例如安排旅行时，往往需要先确定日期，再考虑航班与酒店，而不是随机订一张机票。

哪种方式更好，取决于问题本身。简单、可预测的流程可以使用顺序执行；不断变化的场景适合反应式决策；存在步骤依赖的多阶段目标，则可能需要先进行规划。

## [02:15 三种执行模式与博客写作示例](https://www.youtube.com/watch?v=Zqno_vux6d8&t=135s)

接下来通过一个实际例子理解这些概念：构建**博客写作 Agent**。

用户提供一个主题，Agent 先生成结构化大纲，再根据大纲完成文章，最后提出备选标题和开头引语。

在代码中，负责规划和写作的 Planner Agent 与 Writer Agent 都是由大模型驱动的 **LLM Agent**。它们被封装进 Google Agent Development Kit（ADK）的 **Loop Agent** 中。Loop Agent 属于 ADK 的工作流 Agent，在验证不通过时可以重新尝试执行。

如果内置工作流能力还不够，ADK 也允许通过继承基础 Agent 类，实现自定义 Agent。

首先需要准备开发环境：安装 `uv`，再安装 Google ADK。在 IDE 中建立 Agent 相关文件并导入所需库，就可以开始逐步实现。

## [03:30 第一个组件：Blog Planner](https://www.youtube.com/watch?v=Zqno_vux6d8&t=210s)

第一个组件叫作 **Blog Planner**，职责只有一个：接收文章主题，生成结构化大纲。

创建时指定容易识别的名称 `blog_planner`，指定从环境配置读取的模型名称，并添加人类可读的说明。

最关键的是指令要明确规定输出内容：

- 一个文章标题；
- 一段简短引言；
- **4～6 个章节**，各章节包含要点；
- 一个结论部分。

规定清楚这些要求，可以让输出更加稳定。

最后设置输出键（`output_key`）为 `blog_outline`。这样，Planner 生成的内容会被保存到共享状态的对应字段，后续 Agent 可以读取。

## [04:15 使用 Google ADK 与 uv 搭建工作流](https://www.youtube.com/watch?v=Zqno_vux6d8&t=255s)

下一步添加第二个 Agent：**Outline Validation Checker**，用于检查大纲，而不是生成新内容。

它的指令非常严格：如果共享状态中的大纲包含标题、引言、4～6 个章节和结论，就回答 `OK`；如果缺少内容，就回答 `retry`，并指出存在的问题。

这样，系统就能根据检查结果决定接受大纲还是重新生成。

## [04:50 将 Planner 与 Checker 放进循环](https://www.youtube.com/watch?v=Zqno_vux6d8&t=290s)

我们把 Planner 和 Checker 封装到一个名为 **Robust Blog Planner** 的 Loop Agent 中。

循环先执行 Planner，再执行 Checker。Checker 返回 `OK`，表示这一步完成；如果返回 `retry`，就再执行 Planner。这个示例最多尝试**三次**，相当于为模型偶尔遗漏要求的情况增加一道补救机制。

接下来创建 **Blog Writer**，读取保存在 `blog_outline` 中的大纲，将其扩展为完整 Markdown 文章。

Writer 的指令要求面向软件工程师读者，不必重复过多基础知识，应聚焦实用见解；既解释“怎么做”，也解释“为什么”，有帮助时加入简短代码片段，并使用清晰标题遵循原定大纲。

生成的正文保存在共享状态的 `blog_post` 字段中，供下一步处理。

## [05:40 加入正文检查器与自动修正](https://www.youtube.com/watch?v=Zqno_vux6d8&t=340s)

接下来再添加一个检查器 **Blog Post Validation Checker**。

它负责判断成稿是否具有引言、与大纲对应的章节、结论，以及清楚的解释。满足条件就返回 `OK`；否则返回 `retry`，并列出需要修正之处。

与大纲生成一样，把 Writer 和正文检查器组合成 **Robust Blog Writer** 循环，验证未通过就重新执行，最多**三次**。

随后，将 Robust Blog Planner 与 Robust Blog Writer 分别封装成工具，供根 Agent 直接调用。这样，根 Agent 不必处理每个内部步骤。

最后创建名为 **Blogger** 的 **Root Agent**。它收到用户主题后，先调用规划工具生成大纲，再调用写作工具完成文章，最后补充**三个备选标题**和**两个适合推文长度的开头引语**。

Root Agent 只能访问暴露给它的规划和写作两个工具，因此执行路径较为明确、可控。整个流程就是：接收主题、规划、写作、检查，再交付文章。

## [06:50 运行 Blog Writer 与 Root Agent](https://www.youtube.com/watch?v=Zqno_vux6d8&t=410s)

完成 Agent 脚本后，就可以在终端使用 `adk web` 启动，并通过本地 Web UI 与 Agent 交互。

视频中的测试问题是：“请写一篇关于 AI Agent 十大应用场景的博客文章。”

提交主题后，可以看到各个子 Agent 协作，依次完成规划、写作和最终交付。

到这里，你已经使用 Google ADK 构建并运行了第一个 AI Agent：从基本概念开始，逐步完成代码组织，并在终端和界面中观察工作流程。相关资源与完整代码请参看原视频的说明区。
