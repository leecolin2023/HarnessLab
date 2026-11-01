# 实战：一步步将 AI Agent 部署到 Google Cloud Run

> 来源：Google Cloud Tech，Smitha Kolan，**Modern AI Agents: From Theory to Production**（2/6）  
> 时长：13:44｜原始语言：英语｜处理方式：英文字幕忠实翻译与表达整理（Transcript Refinement）  
> [原视频](https://www.youtube.com/watch?v=bjZ2M7ThOBc)｜[英文转写底稿](https://github.com/leecolin2023/ingest2md/blob/main/output/20261030__Modern%20AI%20Agents%20-%20From%20Theory%20to%20Production/20261030__How%20to%20deploy%20an%20AI%20agent%20to%20Cloud%20Run%20(step%20by%20step)/content.md)
>
> 说明：保留讲者的步骤、产品名称、参数名称和权限说明；章节时间戳沿用原稿，未核听视频。原字幕没有完整显示屏幕上的命令和代码，因此下文不编造命令，实际复现请参照原视频及其说明区的 Codelab。视频中的公开访问设置仅用于教学演示。

## [00:00 把本地 AI Agent 部署到 Cloud Run](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=0s)

如果你的 AI Agent 只能在自己的笔记本电脑上运行，这期视频将介绍如何把它部署到 **Google Cloud Run**。

我们会结合 Cloud Run、**Agent Development Kit（ADK）**和与 MCP Server 的安全连接，让本地 Agent 成为可以通过互联网访问的应用。

最终要部署的是一个**动物园导览 Agent**：它在 Cloud Run 上运行，提供可以通过浏览器访问的 URL。

整个过程包括准备项目代码、配置服务账号与权限、使用一个部署命令构建并发布容器，以及在浏览器中进行快速测试。

## [00:52 Cloud Run 如何工作？](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=52s)

可以把 Cloud Run 想象成一家按需营业的快闪店。请求到来时，它会运行承载应用的容器；当流量增加时，它可以增加容器实例；没有访问请求时，可以缩减到零实例，从而避免为闲置实例持续付费。

开发者提供一个监听端口的容器，Cloud Run 则负责处理扩缩容、负载均衡、TLS、日志和身份等基础设施工作。

这很适合按需使用的 Agent：没人使用时可以保持空闲，有请求时提供服务，随后继续根据流量调整资源。

本次演示的计划是：

1. 使用 ADK 创建一个简单的 Python Agent 项目，并准备工具。
2. 让 Agent 连接 MCP Server。
3. 创建并配置合适权限的服务账号。
4. 执行部署命令。
5. 获取 Agent 的访问 URL。

开始之前需要准备两项内容：**Google Cloud 账号**以及对应的 **Project ID（项目 ID）**。

## [02:11 创建项目并安装依赖](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=131s)

先访问 [cloud.google.com](https://cloud.google.com/) 创建账号，再在 Google Cloud 中创建项目，取得 Project ID。

视频配套的 Codelab 名为 *Build and deploy an ADK agent that uses an MCP server on Cloud Run*，其中列出了相应步骤。原视频说明区提供了 Codelab 链接。

创建项目后，打开 Google Cloud Console 中的 **Cloud Shell**。可以点击控制台右上角的 Cloud Shell 图标，也可以在顶部搜索栏查找 Cloud Shell。

首先确认当前选择的是正确的 Google Cloud 项目。接下来，运行视频展示的命令设置项目，并启用部署所需服务。

相关服务包括 **Cloud Run API、Cloud Build、Artifact Registry**，以及 Agent 调用 **Vertex AI** 模型时需要的服务。启用这些服务是每个项目通常只需完成一次的配置步骤。执行成功后，终端会显示完成信息。

然后，在 Cloud Shell 中创建新的项目文件夹并进入该目录，建立 `requirements.txt`。

容器依赖应尽量精简，以控制镜像大小和冷启动时间。这个实验使用 Google ADK、Wikipedia 辅助工具和 LangChain 适配器。讲者建议明确固定依赖版本，减少后续库升级带来的不兼容问题。

如果跟随 Codelab 操作，应使用其中对应的命令。

## [03:36 环境变量与服务账号](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=216s)

接下来配置环境变量，让脚本和应用识别项目与身份信息。

还需要创建专门的 **Service Account（服务账号）**，供 Cloud Run 中的 Agent 在运行时使用。

这个身份必须拥有调用 Vertex AI 所需的权限。如果 MCP Server 受到访问保护，Agent 的服务账号也必须具备调用 MCP Server 的权限。

随后创建环境配置文件，例如 `.env`，指定模型和 MCP Server 的 URL。将配置从代码中分离可以减少硬编码。视频演示采用较简单的 `.env` 方法；在 Cloud Run 正式环境中，敏感信息应结合环境变量或 **Secret Manager** 管理，而不是把密钥直接写进代码仓库。

先添加模型配置，再为服务账号授权调用 MCP Server。

这一步很容易遗漏，结果就是请求返回 **403** 权限错误。讲者演示给服务账号授予适当的 **Cloud Run Invoker** 权限，使其能够调用受保护的 MCP Server。

配置完成后，将 MCP Server 的 URL 写入环境文件，开始组织 Agent 代码。

## [04:53 使用 ADK 构建 Agent](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=293s)

首先建立 Agent 的 Python 包。通过 `__init__.py`，目录可以作为 Python 包被导入，同时为 ADK 的 Agent 模块定位提供基础。然后添加导入，让包暴露相应 Agent 模块。

接下来创建 `agent.py`。

讲者按小步骤组织这个文件：先导入依赖与日志组件，再读取环境变量、声明模型名称，随后配置工具。

在实际演示中，可以直接将视频或 Codelab 提供的代码复制到 `agent.py` 中。

## [06:53 MCP 与 Wikipedia 工具的配置](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=413s)

这个动物园导览 Agent 具有三种能力：

第一，一个简单的辅助函数，把访问者最初的提问写入**共享状态**，供后续其他 Agent 读取。

第二，一组 **MCP 工具**，负责连接受保护的动物园 MCP Server。

第三，一个 **Wikipedia 查询工具**，用于查找常识性资料。

开始时先完成导入与环境设置。这里启用 Cloud Logging 不只是为了让日志整洁，而是为了在 Google Cloud Console 的 **Logs Explorer** 中查看 Agent 的输出、警告和调试信息。

## [07:34 创建 Researcher 与 Presenter Agent](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=454s)

先加入一个小型辅助工具，保存访问者的第一条消息。这个工具相当于 Greeter（接待 Agent）与 Researcher（研究 Agent）之间的连接：它把内容写入共享 Tool State 字典，供后续 Agent 使用。

然后配置 MCP 工具。从先前的环境文件读取 MCP Server URL。

如果 MCP Server 需要身份验证（生产环境通常应该如此），就为 Cloud Run 服务对应的目标受众（Audience）取得签名 **ID Token**，并在调用时以 **Bearer Token** 方式提供。讲者使用 ADK 的 **Streamable HTTP** 连接参数来完成这项配置。

最后，通过 LangChain 适配器包装 Wikipedia 查询工具。这样，`agent.py` 可以主要处理执行编排，而不必把外部搜索客户端的实现都写在同一个文件中。

工具准备好后，定义两个专门的 Agent。

**Researcher Agent** 从共享状态读取用户问题，判断应该使用动物园 MCP Server、Wikipedia 工具，还是两者都用。其指令应简短、具体，重点说明行为要求而不是修饰输出风格，并通过输出键保存研究结果。

**Presenter Agent** 不调用工具，它读取原始研究结果，将其整理成友好的回答：先说明动物园特定的内容，再补充相关的通用知识。

## [08:48 Root Agent 与执行流程](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=528s)

将两个专门的 Agent 放入 **Sequential Workflow Agent（顺序工作流 Agent）**，先执行 Researcher，再执行 Presenter，执行期间共享状态会按流程传递。

未来如果需求更复杂，还可以考虑 Loop Agent 或 Parallel Agent 等模式。

最后定义 **Root Agent（根 Agent）**，作为新会话的入口，也是 ADK 需要识别的顶层 Agent。

Root Agent 负责向访问者问好，使用辅助工具保存第一条消息，再把相关上下文传给前面定义的工作流。

把问候和研究流程分开，可以让日志中的执行顺序更清楚，也更便于排查问题。

## [09:30 将 Agent 部署到 Cloud Run](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=570s)

代码准备完毕后，还需要确保部署环境拥有调用模型的权限。

先把环境文件中的配置加载到 Shell，确保部署期间能够读取模型名称。然后向运行 Agent 的服务账号授予 **Vertex AI User** 角色。

如果缺少这个权限，Cloud Run 服务本身可能正常启动，但在实际调用模型时会出现权限错误。

接下来开始部署。ADK 提供部署命令，能够从源码构建容器镜像，推送到 **Artifact Registry**，并创建具有默认配置的 Cloud Run 服务。

讲者使用 **`uvx`**，以免全局安装 CLI。部署时需要传入项目、区域、服务名称等参数，并打开 **Web UI** 选项，以便进行快速测试；同时指定运行时服务账号，并为服务添加标签，方便以后定位。

## [10:43 测试线上 Agent](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=643s)

部署期间，Cloud Run 可能询问是否在指定区域创建名为 `cloud-run-source-deploy` 的构建仓库；如果尚不存在，实验中可以确认创建。

还可能询问是否允许未经认证的访问。**讲者仅为教学演示选择允许公开访问**，便于直接点击链接。生产环境应尽量保持服务私有，通过认证代理或后端集成方式提供访问。

命令执行完成后，终端会输出 Cloud Run URL。打开这个地址，即可进入部署后的 Agent Web UI。

视频中演示打开右侧的 Token Streaming 选项，观察响应流式输出。然后先输入“Hello”，检查接待响应，再询问：

> “这里的北极熊在哪里？它们在野外吃什么？”

此时可以观察完整工作流：Researcher 调用动物园 MCP Server 获取园区展区位置，再调用 Wikipedia 工具查询北极熊的野外饮食信息，最后由 Presenter 组织回答。

## [11:26 后续改进与资源清理](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=686s)

测试结束后，应清理不再使用的资源，避免持续产生费用。

可以只删除 Cloud Run 服务；如果构建仓库仅用于这次实验，也可以一起删除。视频展示的清理命令会删除指定区域中的 Cloud Run 服务和默认 Source Deploy 仓库；需要省略交互确认时，可以使用相应的 `--quiet` 参数。

清理前应确认资源是否真的只供实验使用，避免误删其他项目仍需要的组件。

## [12:39 总结](https://www.youtube.com/watch?v=bjZ2M7ThOBc&t=759s)

至此，我们部署了一个能够使用 MCP Server 工具以及 Wikipedia 查询工具的 AI Agent。

Cloud Run 为它提供自动扩缩容、按需启动、日志记录和身份管理等能力，开发者不必自行管理底层服务器。

使用 MCP 暴露工具，也让后续增加新能力时更容易复用现有接入方式。

视频说明区提供了实验对应的 Codelab 资源与链接，可用于回看具体操作命令及代码。
