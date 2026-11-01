# MCP 的工作原理：Client、Server、Tools、Resources 与 Prompts

> 来源：Google Cloud Tech，Smitha Kolan，**Modern AI Agents: From Theory to Production**（4/6）  
> 时长：07:58｜原始语言：英语｜处理方式：英文字幕忠实翻译与表达整理（Transcript Refinement）  
> [原视频](https://www.youtube.com/watch?v=cGuyrANVi4A)｜[英文转写底稿](https://github.com/leecolin2023/ingest2md/blob/main/output/20261030__Modern%20AI%20Agents%20-%20From%20Theory%20to%20Production/20261030__How%20Model%20Context%20Protocol%20(MCP)%20actually%20works/content.md)
>
> 说明：本文忠实呈现讲者的解释和示例，不将视频中的简化表述视为完整的 MCP 协议规范。时间戳为原稿章节起点，未核听音视频。

## [00:00 AI 与传统 API 集成时遇到的问题](https://www.youtube.com/watch?v=cGuyrANVi4A&t=0s)

如果你尝试过让 AI 模型访问自己的工具或数据，可能已经发现，集成过程往往很繁琐。每个 API 的行为都不同，每个集成需要编写专门代码；模型发生变化时，连接方式也可能受到影响。

**Model Context Protocol（MCP，模型上下文协议）**就是为缓解这类问题而提出的。这期视频将逐步解释 MCP 是什么、为什么需要它、它与传统 API 有何不同，以及这些变化对 Agent 和 AI 应用开发者意味着什么。

## [00:48 什么是模型上下文协议？](https://www.youtube.com/watch?v=cGuyrANVi4A&t=48s)

从根本上说，MCP 是一种开放标准，让模型能够以一致、结构化的方式连接外部工具、数据和上下文。

可以把它理解成模型与周围系统之间的通用语言。它规定如何发现可用工具、请求信息和执行操作，而不需要调用方预先了解每个工具的内部实现细节。

这个协议最初由 **Anthropic** 提出，随后逐渐被行业采用。它针对的是 AI 开发中的一个常见难题：如何让模型更加安全、可靠地使用外部资源。

## [01:26 MCP 究竟连接哪些外部资源？](https://www.youtube.com/watch?v=cGuyrANVi4A&t=86s)

传统 API 主要面向已经知道自己要做什么的程序。程序可以构造明确、确定的请求。语言模型的工作方式不同：它以概率方式生成内容，面对模糊输入时可能需要先提问、澄清或探索，才能判断接下来该采取什么操作。

MCP 尝试弥合这种差异。它通过统一接口，让系统描述并提供函数、数据集、文档或提示词等资源。

开发者不必把每个集成的全部细节都硬编码在模型调用逻辑中；Agent 系统可以动态了解有哪些能力可以使用，按任务需要调用，还可以串联多个工具。

要理解 MCP 的运行过程，可以先认识协议通信的两端：**Client 和 Server**。

## [02:43 MCP Client 与 MCP Server 如何交互？](https://www.youtube.com/watch?v=cGuyrANVi4A&t=163s)

讲者把 Client 描述为希望执行任务的语言模型或 Agent 系统，例如使用 Claude、Gemini 或基于 OpenAI、Google 框架开发的 Agent。

Server 则负责向调用方提供能力与资源，例如数据库、文件系统、企业内部工具，或者文档搜索引擎。

当 Client 建立连接时，Server 不仅能返回数据，还可以声明自己支持哪些能力、提供哪些资源、允许哪些操作，以及调用时需要哪些输入。

这意味着，Agent 不必事先写死所有 API 或 Endpoint 的调用细节，可以通过协议发现可用能力。

两端通过定义清晰的结构化消息通信。Client 可以提出类似以下请求：“列出可用资源”“调用这个操作”或者“读取这些数据”。Server 则用结构化内容告诉 Client 可执行的能力和实际结果。视频主要以 JSON 格式说明这种交互。

MCP 的基本价值，就是为 Agent 与外部环境之间的沟通提供统一方式。

## [04:03 MCP 的组成：Tools、Resources、Prompts 与 Context](https://www.youtube.com/watch?v=cGuyrANVi4A&t=243s)

接下来进一步理解 MCP 提供的不同内容。

**Tools（工具）**是可调用的操作。例如搜索数据库、发送邮件，或分析文件。

**Resources（资源）**是可以读取的数据或状态，例如文本文档、数据库记录或图片。

**Prompts（提示词）**是可复用的模板，描述特定任务的提示方式。

视频还用 **Context（上下文）** 表示模型在推理中可能用到的外部信息，例如近期聊天记录、企业数据或用户偏好。这里的 Context 是讲解用的宽泛概念，并不等同于与 Tools、Resources、Prompts 平级的独立协议能力类型。

MCP Client 连接 Server 后，可以根据服务器支持的能力请求工具、资源或提示词清单。这些对象携带相应元数据，例如名称、用途、输入要求和返回内容描述，便于 Agent 判断如何使用。

例如，无论连接 GitHub、CRM 还是日历系统，Agent 都可以通过统一的 MCP 接口与它们交互，而不必每次学习完全不同的集成协议。

## [05:20 MCP 与 API 的区别是什么？](https://www.youtube.com/watch?v=cGuyrANVi4A&t=320s)

既然已经有 API，为什么还需要 MCP？讲者认为，关键区别在于这些接口主要面向谁。

传统 API 主要为人编写的程序提供服务；MCP 则提供一层更适合 Agent 使用的工具描述与调用抽象。

底层的 MCP Server 仍然可能调用原有 REST 或 GraphQL API。Agent 系统通过结构化的 MCP 接口了解工具、构造调用并接收结果，不必直接面向每一个后端 API 编写不同的适配方式。

例如，要构建一个能查看日历、读取会议笔记并起草跟进邮件的个人助理，以前需要分别集成 Google Calendar、Notion 和 Gmail API。开发者必须为每个服务编写代码，处理认证、限流和各种边界情况，并在提示词或程序中说明如何调用。

使用 MCP 时，可以为日历、笔记和邮件系统分别部署或接入 MCP Server。各个 Server 对外声明能力，Agent 便能发现“列出事件”“获取会议摘要”“发送邮件”等工具。

## [06:43 案例：通过 MCP 构建个人助理](https://www.youtube.com/watch?v=cGuyrANVi4A&t=403s)

当需要完成一个复杂任务时，Agent 可以判断先调用哪种工具、采用什么顺序，以及如何在不同工具之间传递数据。

一致的协议减少了针对每个新增工具编写专门连接代码的需求。开发者仍需要提供相应服务器、权限和实际实现，但不必让 Agent 为每个服务学习完全不同的交互形式。

讲者将这种标准化与 HTTP 推动 Web 互操作的过程作类比：MCP 正在帮助统一模型与工具之间的通信方式。因此，理解 MCP 的基本概念和接口，对正在构建 Agent 的开发者具有现实价值。

视频说明区提供了 Google Cloud 相关 MCP Server 的资源，以及进一步了解 MCP 工作原理的文章和后续视频。
