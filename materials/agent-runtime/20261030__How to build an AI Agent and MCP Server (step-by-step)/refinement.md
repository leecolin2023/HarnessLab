# 实战：一步步构建 AI Agent 与 MCP Server

> 来源：Google Cloud Tech，Smitha Kolan，**Modern AI Agents: From Theory to Production**（5/6）  
> 时长：07:54｜原始语言：英语｜处理方式：英文字幕忠实翻译与表达整理（Transcript Refinement）  
> [原视频](https://www.youtube.com/watch?v=wBnnA8aIxUs)｜[英文转写底稿](https://github.com/leecolin2023/ingest2md/blob/main/output/20261030__Modern%20AI%20Agents%20-%20From%20Theory%20to%20Production/20261030__How%20to%20build%20an%20AI%20Agent%20and%20MCP%20Server%20(step-by-step)/content.md)
>
> 说明：保留原视频的讲解顺序和操作步骤；章节时间戳来自字幕稿，未核听视频。原始稿没有完整代码片段，下文只翻译讲者解释，不凭空补写代码。

## [00:00 什么是 MCP，为什么要把 Agent 连接到 MCP Server？](https://www.youtube.com/watch?v=wBnnA8aIxUs&t=0s)

这期视频要做的是把一个 AI Agent 连接到 MCP Server。你将了解什么是 MCP Server，它为什么重要，以及怎样让 Google ADK Agent 使用它。完成后，Agent 不再只负责写作和规划，还能通过 MCP 获取外部工具的数据。

**MCP** 是 **Model Context Protocol（模型上下文协议）** 的缩写。可以把它理解成 Agent 和外部工具之间的一种标准沟通方式。

一端是由大语言模型驱动的 Agent，另一端是完成特定工作的工具，例如查询 Google Trends、访问数据库或运行代码。

## [00:49 MCP 在底层怎样工作？](https://www.youtube.com/watch?v=wBnnA8aIxUs&t=49s)

Agent 本身无法凭空完成这些外部操作，MCP 在两者之间提供标准接口。

这个示例中的工具以独立程序的形式运行，通常拥有独立进程。Agent 通过**标准输入和标准输出（stdio）**与其通信，先询问：“你提供哪些工具？”

MCP Server 返回工具名称、参数等描述。随后，Agent 选择某个工具，传入相应参数；工具执行后，将结果返回。视频使用 JSON 作为工具参数和结果的示例格式。

这里的重要原则是**接口与内部实现分离**。Agent 不需要知道工具由什么语言编写、使用了哪些库或内部如何工作。只要能够通过 MCP 接口通信，就可以使用它。

讲者认为这种设计有四个优势：

- **隔离**：工具独立运行，工具进程出错不必然导致 Agent 进程一起退出。
- **互操作**：工具可以使用 Python、Go 或 Node.js 编写。
- **可发现**：工具通过 Schema 描述自己，Agent 可以在运行时了解如何调用。
- **可扩展**：可以添加、替换或升级工具，而不必重写整个 Agent。

如果把 Agent 比作大脑，MCP 就是连接大脑与现实世界中手和眼睛的通路。大脑决定做什么，协议负责传递请求，工具执行操作，再把结果返回。

上一期视频已经做出一个博客写作 Agent：输入主题后，它会规划章节、起草正文并提出备选标题。但它主要依赖模型自身的信息，无法了解现实世界当前的热门趋势。

## [02:41 演示：让博客写作 Agent 使用 Google Trends](https://www.youtube.com/watch?v=wBnnA8aIxUs&t=161s)

这次要为博客 Agent 增加一个 MCP Server，用它获取 Google Trends 的实时数据，让文章能够依据当前的搜索趋势来写。

首先，在项目目录中创建一个 Python 文件。这个文件只负责一项工作：通过 MCP 暴露名为 **`trends`** 的工具，让 Agent 可以查询 Google Trends。

可以把它看成一个小型服务，只不过当前演示不是通过普通 HTTP 接口通信，而是通过 MCP 的标准输入与输出通信。

讲者将代码分成四个关键部分。

**第一部分：把普通 Python 函数包装成工具。**

原本只是一个接收 JSON 兼容参数、返回 JSON 兼容字典的 Python 函数。通过 ADK 的 `FunctionTool`，框架能够检查函数签名和文档字符串，形成工具名称与 Schema，减少手工编写工具定义的工作。

**第二部分：创建 MCP Server 对象。**

这个对象负责按照 MCP 协议与客户端通信。设置的名称是服务器标识，客户端在建立连接时可以看到相应元数据。

**第三部分：实现列举工具和调用工具两个处理过程。**

客户端连接后首先请求工具清单。服务器返回包含 `trends` 的列表，并通过 ADK 提供的转换辅助函数，把 `FunctionTool` 元数据转换成 MCP 客户端能够理解的工具 Schema。

客户端因此能够看到工具名称、参数、参数类型和说明，从而构造合法调用。

真正调用时，客户端发送工具名称以及 JSON 参数字典。服务端检查名称后，将参数传给对应的 Python 函数并异步执行。函数结果序列化为 JSON，再作为文本内容返回。

如果出错，就返回简短的 JSON 错误信息，并把详细日志写到标准错误输出。讲者概括这一流程为：输入工具名称和参数，输出 JSON 结果。

**第四部分：将 Server 绑定到标准输入和输出并启动。**

服务端通过 stdio 传输读写数据，初始化时声明元数据和支持的能力；在程序入口使用 `asyncio.run` 启动服务器。此后，ADK 可以启动这个脚本、发现工具，并像使用其他工具一样调用 `trends`。

## [06:22 在 ADK Web UI 中运行 Agent](https://www.youtube.com/watch?v=wBnnA8aIxUs&t=382s)

最后，修改 `main_agent.py`，把 `trends` MCP 工具加入 Root Agent 的工具列表，与已有的规划和写作工具放在一起。

从 Agent 的视角看，调用 `trends` 与调用本地函数工具相似。不同的是，这次它可以先获取 Google Trends 的真实热门查询，再开始撰写博客，而不必只凭模型猜测哪些话题正在流行。

随后，使用 `adk web` 启动 ADK Web UI，就可以与已经连接 MCP Server 的 Agent 交互。

## [07:10 回顾](https://www.youtube.com/watch?v=wBnnA8aIxUs&t=430s)

我们从上一期博客写作 Agent 出发，新增一个暴露 `trends` 工具的 MCP Server，再把它接入 Root Agent。这样，Agent 在写作之前，就能够使用 Google Trends 数据。

这种模式让 Agent 本体保持相对轻量，同时通过外部工具获取现实世界的信息。视频说明区还提供了相关资源和代码，下一期内容会继续介绍使用 ADK 构建多 Agent 系统。
