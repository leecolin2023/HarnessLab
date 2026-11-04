# Model Platform 学习路线：从 Qwen 小模型、Qwen3.8-27B 到 DeepSeek V4 Flash 与 OCR

> **核心目标**：围绕同一个可验证的企业模型服务场景，逐步理解模型权重如何变成可调用的推理服务，服务怎样处理并发和资源约束，多种模型怎样经统一入口发布、治理、监控与升级。
>
> **实验主线**：**Qwen3-0.6B / 4B → Qwen3.8-27B → DeepSeek-V4-Flash-0731 → PaddleOCR-VL-1.5 → 统一模型服务入口**。先从小模型学习请求、服务和并发，再用 27B Dense 模型真正学习显存、W8A8、TP 与副本；随后将这些经验带入大型 MoE 的专家并行与通信问题，最后用 OCR 验证平台是否能管理不同类型的服务。
>
> **工程原则**：使用成熟的推理框架和部署组件，不把自研 CUDA/昇腾算子、推理引擎或模型训练当作本路线的前置任务。重点是**选型、配置、部署、故障定位、容量判断、API 兼容、质量回归和平台治理**。
>
> **现有材料**：[模型服务平台总论](./README.md) 已介绍平台职责；[01 · vLLM 推理服务机制](./01-vllm-inference-serving.md) 解释 KV Cache、PagedAttention、Continuous Batching、Chunked Prefill；[02 · 模型服务容量规划](./02-model-serving-capacity-planning.md) 以 Qwen3.8-27B 与昇腾 910B4 为例研究卡数、精度、TP 和副本。**保留这两篇，不重新编号或替换**；本路线说明何时阅读、如何用真实实验验证。
>
> **状态说明**：这是学习与实验的建设规划。仓库已有原理文章，但并不表示 Qwen 小模型、27B、DeepSeek 或 OCR 已经完成实际部署、性能测试或平台接入。每阶段完成情况只能根据实际运行记录确认。

## 一、为什么先 Qwen 小模型，再 Qwen 27B、DeepSeek 和 OCR？

假设企业需要处理一份扫描版的岗位 JD 或其他脱敏文档：

1. 文档服务把 PDF 页面转成图片，完成版面解析、文字识别和表格恢复。
2. 轻量模型对已识别内容做低成本的辅助分类或字段整理，确定是否值得进入更复杂的分析。
3. 大型语言模型分析复杂岗位条件，区分“必须”“优先”“或关系”“否定”等表述，形成有原文依据的结论。
4. 业务程序校验身份、来源、字段、证据和报告，而不是把全部正确性责任交给模型。

这是一条**可选的完整业务链**，不是说每条请求都必须依次调用所有模型：纯文本 JD 应跳过 OCR，明确的字段与数值规则优先交给普通程序。Qwen3.8-27B 在这条路线中首先是**模型服务能力与复杂文本任务的中间基准**，可与小模型、DeepSeek 做独立的质量—性能对照，并非每次都必须先经过 27B 才能调用 DeepSeek。

~~~text
业务应用 / Agent Runtime
          ↓
      模型服务 Gateway
          ├── 轻量文本服务：Qwen3-0.6B / Qwen3-4B
          ├── 中大型 Dense 服务：Qwen3.8-27B
          ├── 大型 MoE 服务：DeepSeek-V4-Flash-0731
          └── 文档解析服务：PaddleOCR-VL-1.5
          ↓
鉴权、限流、路由、监控、版本与资源治理
          ↓
GPU / 昇腾 NPU / CPU 等实际推理资源
~~~

**主线不是让每个模型都参与同一次业务请求，而是通过递进的模型规模与负载，逐步暴露模型服务平台必须解决的问题。**

- Qwen 小模型让我们先看清一次模型请求从加载到返回的全过程。
- **Qwen3.8-27B** 让我们在结构相对直接的 Dense 模型上研究多卡、W8A8、混合注意力、长上下文、TP 与副本，不必同时处理 MoE 专家路由。
- DeepSeek Flash 在这一基础上增加大型 MoE 权重、专家并行、通信负载和更复杂的长上下文问题。
- OCR 让我们意识到平台不能把所有模型都当作纯文本 Chat Completion：文档预处理、页面与版面、结构化输出、异步队列和质量标准都会不同。

## 二、各实验模型具体选择什么版本？

| 学习角色 | 固定的首轮实验对象 | 为什么选择它 | 需要特别注意 |
| --- | --- | --- | --- |
| 最小文本模型 | `Qwen/Qwen3-0.6B` | 权重较小，适合低成本理解加载、Tokenizer、请求与返回 | 低端 CPU 可以探索正确性，但不预设吞吐或低延迟 |
| 正式单实例 Serving | `Qwen/Qwen3-4B` | 在同类文本任务上自然加入 GPU/NPU、流式 API、并发、KV Cache | 官方模型存在思考/非思考行为差异，测试条件需固定 |
| **中大型 Dense / 多卡 Serving** | **`Qwen/Qwen3.8-27B`**，昇腾优先评估官方支持的 W8A8 权重 | 从小模型的单实例走向 27B 权重规模、量化、长上下文、TP 与 DP/多副本 | 约 27B 总参数；BF16 权重理论约 54GB，W8A8 理论主权重约 27GB，但不能据此断定单卡可用 |
| 大型 MoE | `DeepSeek-V4-Flash-0731` 的已验证昇腾 W8A8 权重 | 引出 284B 总参数、13B 激活参数、专家并行与多卡调度 | 不能用激活参数量计算权重存储；不得直接沿用 NVIDIA 的部署命令 |
| 文档 OCR | `PaddlePaddle/PaddleOCR-VL-1.5`，辅助对照 `PP-OCRv5` | 引出页面预处理、版面与结构、视觉推理及不同服务契约 | 完整 PaddleOCR-VL Pipeline 不等于只启动 VLM 推理接口 |

### DeepSeek“0730”版本如何处理？

最初希望研究的是“DeepSeek V4 Flash-0730”。经核查，官方可验证的是 **`DeepSeek-V4-Flash-0731`** 及其官方发布、量化和部署资料；未找到可明确确认的同名 `0730` 公开权重。因此课程将“7 月底 Flash”落到 **0731** 上，不把 `0730` 当作已确认发布的模型。

同时需要区分三类标识：

- **权重版本**：本地下载的准确模型仓库、修订号、量化版本与文件校验和。
- **推理服务名称**：部署时暴露给客户端的 `served-model-name`，可由平台配置，不等同于真实权重版本。
- **云 API 别名**：例如 DeepSeek 官方早期 `deepseek-v4-flash` 已被临时路由到更新一代 V4.1 Flash；**调用同名云 API 不能证明本地正在运行 0731 权重**。

这一差别贯穿之后所有模型升级、A/B 对比和回滚实验。参见 [DeepSeek 官方更新日志](https://api-docs.deepseek.com/updates/) 与 [vLLM-Ascend 的 DeepSeek V4 Flash 部署指南](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html)。

### 为什么 OCR 选 PaddleOCR-VL-1.5？

这是一个**版本固定的实验基线**，不是宣称它永远是最新或最好。选择它是因为文档解析 Pipeline、模型权重、官方部署与评测资料较完整，适合讲清“单个视觉模型”和“完整 OCR 服务”的区别。后续可将 PaddleOCR-VL-1.6、PP-StructureV3 或其他 OCR 模型加入对照，但先不改变基准版本。

## 三、学习之前先分清三种硬件路线

不要为每个阶段都准备一套相同的昂贵设备。

| 环境 | 优先做什么 | 不该假定什么 |
| --- | --- | --- |
| **普通 x86 机器 / 小型云主机** | Qwen3-0.6B 量化推理、Tokenizer、协议与客户端基准、Gateway 模拟 | CPU 推理速度可代表 GPU/NPU Serving；这种资源能加载 284B MoE |
| **单卡 NVIDIA GPU**（如可获得） | Qwen3-4B 的 vLLM Serving、流式请求、并发和缓存；OCR 完整 Pipeline 的 NVIDIA 方案 | CUDA 命令与性能可以直接迁移到昇腾 |
| **昇腾 910B4 / A2 八卡节点**（有可用权限时） | **Qwen3.8-27B 的 BF16/W8A8 与 TP/副本实验**、DeepSeek V4 Flash W8A8、多卡性能和资源治理 | 标称 64GB HBM 就一定能使用全部 64GB；NPU 版本、权重、算子与拓扑天然兼容 |

若没有 GPU/NPU 权限，前面的小模型与服务协议阶段仍能独立完成；大型模型可以先做**权重与软件支持矩阵审查 + 托管 API 语义验证**，但不能将此写成“完成私有化部署或八卡性能测试”。

**910B4 属于具体硬件交付和驱动环境的约束。** vLLM-Ascend 的 A2 参考文档提供重要依据，但仍需在目标服务器上确认设备枚举、CANN、驱动、镜像、互联拓扑与版本组合。

## 四、现有文章与完整知识版图怎样衔接？

这份路线采用 **00—11 的知识主题**，对应 **阶段 0—12 的实践链**。**知识文章 00—11 已全部成稿**；具体 Qwen、27B、DeepSeek、OCR 和 Gateway 的实验仍须按真实运行证据逐步验证。现有 01、02 原文保留，03—11 在本次补齐。

| 知识主题 | 必须弄清的问题 | 首个实践阶段 |
| --- | --- | --- |
| [00 · 模型服务平台是什么](./README.md) | 模型运行为什么不等于可长期交付的服务？ | 0 |
| [01 · vLLM 推理服务机制](./01-vllm-inference-serving.md) | Prefill、Decode、KV Cache、PagedAttention 与批处理为什么影响吞吐？ | 2—3 |
| [02 · 模型服务容量规划](./02-model-serving-capacity-planning.md) | 以 Qwen3.8-27B 为核心案例，学习显存、量化、TP、副本、流量与冗余怎样决定卡数 | **4—5**，6—7 对照 |
| [03 · 模型工件与运行环境](./03-model-artifacts-and-runtime-environment.md) | 权重、Tokenizer、量化文件、驱动、引擎版本怎样组成可复现配置？ | 0—1 |
| [04 · 从本地推理到统一模型 API](./04-local-inference-to-model-api.md) | 如何从一次 `generate()` 变成可调用、可流式、可观测的常驻服务？ | 1—2 |
| [05 · 单实例并发与推理调度](./05-single-instance-concurrency-scheduling.md) | 请求增加后，慢在哪里，改 Batch/Context/Cache 为什么有效？ | 3 |
| [06 · MoE 与多卡推理](./06-moe-and-multi-device-inference.md) | 用 Qwen 27B 的 TP/副本作为对照，理解 DeepSeek 的专家路由、EP/TP/DP、通信与容量 | 5—7 |
| [07 · 多模态 OCR Serving](./07-multimodal-ocr-serving.md) | 文字识别模型与完整 PDF Pipeline 的执行边界如何划分？ | 8—9 |
| [08 · 模型 Gateway 与能力路由](./08-model-gateway-capability-routing.md) | 多个后端如何以稳定 API 接入业务，又不抹平能力差异？ | 10 |
| [09 · 性能与质量评测](./09-performance-and-quality-evaluation.md) | TTFT、TPOT、P95、吞吐和 OCR 质量怎样构成有效验收？ | 3—11 |
| [10 · 发布、回滚与资源治理](./10-release-rollback-resource-governance.md) | 模型更新、限流、鉴权、日志与资源争用怎样长期管理？ | 11 |
| [11 · 端到端业务调用与工程决策](./11-end-to-end-business-inference.md) | 一份文档如何经多模型服务处理，并形成可追踪结果？ | 12 |

03—11 现在已有独立正文，**但原理文章完成不意味着对应实验已经执行**。按阶段运行小规模、可复核的实验，再对照文章中已有机制解释，必要时更新文章和技术结论；不必等待整条实践链全部建成才开始测试。

## 五、实践阶段 0—2：先把 Qwen 小模型从文件变成服务

### 阶段 0｜先调查运行环境，而不是直接复制部署命令

**首要问题：为什么别人的启动命令能运行，我的机器却连模型都加载不了？**

先采集 CPU/GPU/NPU 型号、实际可用内存或 HBM、驱动、CUDA/CANN、Python、推理框架及镜像版本、容器运行能力、磁盘与网络条件。

同时明确模型工件：

- 模型仓库、精确 revision、权重摘要、权重格式；
- Tokenizer 与对话模板版本；
- 推理引擎、设备后端、量化方式和关键启动参数；
- 模型下载与缓存、许可证及商业使用限制；
- 真实部署目标：CPU、NVIDIA GPU 或 Ascend A2。

**观察与验收**：形成一份 `environment-manifest.json`（逻辑产物名），说明机器有什么资源、为什么先选某个模型与引擎。没有运行证据时，状态只能是 `planned` 或 `blocked`，不能写成已部署。

### 阶段 1｜Qwen3-0.6B：一次文本生成真正经历了什么？

先在低成本环境用成熟推理工具加载 `Qwen3-0.6B`；可考虑 llama.cpp/Ollama 处理量化 CPU 推理，或在符合条件的 GPU 上直接使用 vLLM。首轮不要求自己实现推理循环。

实验固定几组简短中文输入，观察：

- 模型下载与首次加载时间；
- Tokenizer 如何把输入映射为 Token；
- 权重常驻内存与每次请求新增的运行时开销；
- 输出长度、生成参数、首字时间和总耗时；
- 相同输入重复请求是否完全一致，哪些条件会改变结果。

**验收**：保留真实权重与配置、三次以上可复现的输入输出和运行元数据。区分“模型在 CPU 上能回答”与“它已具备服务能力”，不要预设 CPU 的 P95 性能。

**核心理解**：权重只定义计算对象，Tokenizer、对话模板、推理实现和生成参数共同决定实际行为。

### 阶段 2｜Qwen3-4B：为什么一次推理正常，变成 HTTP 服务就有新问题？

使用 vLLM（NVIDIA）或经版本确认的 vLLM-Ascend（A2）部署 `Qwen3-4B`，通过正式 Serving 端口提供 OpenAI-compatible 的文本接口。

同一组测试至少检查：

- 服务是否成功加载且 `/health`、`/v1/models` 或相应就绪检查符合当前引擎支持范围；
- Chat Completions 的非流式与流式结果；
- 模型名称、Token 用量、停止原因、超时与错误码；
- 客户端取消时服务实际如何处理；
- 多轮输入是否需要由调用端维护历史；
- 模型本身的 thinking/non-thinking 设置与模板是否匹配。

**验收**：两种服务模式都能由独立客户端调用；能观察请求日志和模型信息。不要因为采用“兼容 API”就假定所有推理引擎支持相同的 Tool Calling、JSON Schema 或流式事件格式。

读 [01 · vLLM 推理服务机制](./01-vllm-inference-serving.md)，把表面上的“HTTP 变慢”追到实际计算和请求调度。


## 六、实践阶段 3—4：Qwen 已经能服务，怎样知道它的容量在哪里？

### 阶段 3｜同一实例接入多用户后，为什么吞吐和延迟没有一起变好？

**首要问题：模型能返回答案，为什么增加并发后首 Token 延迟和完整响应时间反而上升？**

沿用阶段 2 的同一模型、同一权重和引擎版本，不先更换更大的模型。

建立可重复的压测输入，至少包含短输入短输出、长输入短输出、短输入长输出三组；在单并发、少量并发和逐渐升高的请求到达速率下比较。

观察这些事实：

- **TTFT**：请求发出到首 Token 返回的时间，包含排队与 Prefill 等阶段；
- **TPOT / ITL**：后续输出 Token 的间隔，需要明确采用的统计口径；
- **端到端 P50 / P95**：用户实际等待多久；
- **输入/输出 Token 吞吐**：单位时间系统真正处理多少工作；
- **KV Cache / HBM、队列与活跃请求**：资源先在哪个环节达到限制；
- **取消与超时**：请求断开后是否仍继续占用推理资源。

然后再理解 Continuous Batching、PagedAttention、Prefix Cache、Chunked Prefill 为什么能够改变资源利用方式。不要因为开启某项优化后吞吐提升，就宣称其内部机制已由本实验独立证明。

**验收**：生成一份与输入负载对应的延迟—吞吐曲线，能说清楚“容量最大值是在哪种请求组合和质量前提下测得的”。不得只公布“并发 100”却不说明输入与输出长度。

### 阶段 4｜同一个 Qwen，应该优先量化、加卡，还是增加副本？

**首要问题：权重理论上放得进显存，为什么一加长上下文或并发就 OOM？**

先阅读 [02 · 容量规划](./02-model-serving-capacity-planning.md) 中的显存预算方法，将其用于当前 Qwen 4B 部署，而非立即切换更大的模型。

区分四部分内存：

~~~text
模型权重 + 运行时请求状态（如 KV Cache）
        + 计算工作区 + 框架/通信/其他保留
~~~

从同一组请求出发，逐步调整上下文上限、`max-num-seqs`、批处理预算及支持的缓存设置，再观察显存和吞吐变化。

如果已有可用的量化权重，在软件支持矩阵确认后比较 BF16 与对应量化格式。注意 **W8A8、FP8、GGUF、AWQ 不是可以不经适配直接互换的标签**；比较之前应确认量化实现、校准过程、算子与精度影响。

再研究：

- **TP（Tensor Parallel）**：跨多卡拆分一个模型实例；
- **DP/副本**：多个实例分别服务不同请求；
- **扩容取舍**：当单请求内存或延迟不足，可能考虑模型分片；当单实例已达标而队列积压，更可能增加副本。

**验收**：同一模型输出一个可复核的资源预算及配置决策，明确“为什么这时选择调整上下文/并发，而不是盲目扩大 TP”。已有 [Qwen3.8-27B 与 910B4 容量文章](./02-model-serving-capacity-planning.md) 可作为进阶案例，其数值不得直接当作本轮 Qwen4B 的实测。

## 七、实践阶段 5—7：先完成 Qwen3.8-27B 多卡 Dense，再进入 DeepSeek MoE Serving


### 阶段 5｜Qwen3.8-27B：为什么 4B 的部署经验不能直接放大到 27B？

**首要问题：小模型可以单卡运行，为什么 27B 必须先同时核查权重规模、运行时状态、软件适配和目标负载？**

将 **`Qwen/Qwen3.8-27B`** 设为正式的**独立部署实验对象**，不再只作为容量规划文章的附带案例。先通读 [02 · 模型服务容量规划](./02-model-serving-capacity-planning.md)，把其中的模型卡数判断用于真实环境核验。

**第一步：区分静态权重与动态运行占用。**

- 27B Dense 参数在 BF16 下的**理论基础权重**约为 `27×10⁹×2=54GB`；还未包括视觉编码器、框架、计算工作区和请求运行状态等实际开销。
- W8A8 的主要 8 位权重理论量级约为 **27GB**，但实际文件、非量化模块、元数据与执行峰值需测量；这不是“单卡必能运行”的证明。
- Qwen3.8-27B 使用混合注意力/状态机制，并不应该把传统全注意力每层都保存 KV 的公式机械套到全部模型层；必要时分别分析 Full Attention 的 KV 与其他状态缓存。

**第二步：以昇腾 910B4 / Atlas A2 为重点核查软件支持，而不是先猜卡数。**

[vLLM-Ascend 官方 Qwen3.8-27B 说明](https://docs.vllm.ai/projects/ascend/en/latest/tutorials/models/Qwen3.8-27B.html) 提供 BF16 与 W8A8 在 Atlas 800I A2（64GB × 8）节点上的参考路径，涉及 vLLM-Ascend、CANN、NPU 设备绑定、量化后端和多卡参数。应固定其文档所用的软件版本与权重来源，再核对目标 910B4 机器。

在 A2 参考部署中，**W8A8 的 TP=2 / TP=4 是有文档依据的测试候选**；即使从理论容量看 27GB 小于单卡 64GB，也不能据此断言 TP=1 在具体模型、权重与引擎组合上可用。尤其不要照抄仅面向昇腾 950 系列的 MXFP8/C8 参数到 A2。

**第三步：建立真正的多卡与多副本对照。**

在同一精确模型权重、输入分布和相同软件版本下，先验证能否成功加载、提供流式 API，并记录每卡 HBM 与错误。再根据支持情况比较：

| 方案 | 研究问题 | 先决条件 |
| --- | --- | --- |
| BF16 / W8A8 | 精度变化实际降低多少 HBM？质量有无退化？ | 准确权重和引擎实现 |
| TP=2 / TP=4 | 更多卡用于一个实例，单请求延迟和吞吐是否改善？ | 拓扑、通信与引擎支持 |
| TP=2 × 2 副本 | 同样四卡，是增大 TP 还是增加副本更能降低排队？ | 两个独立实例都稳定运行 |
| 不同 Context / 并发 | 长上下文和活跃请求如何改变 HBM、TTFT 与 P95？ | 固定请求长度与压测条件 |

Qwen3.8-27B 的模型能力不限于纯文本，但本阶段**先固定文本请求作为 Serving 基线**；图像/视频路径、额外预处理与视觉质量另行验证，不与 OCR Pipeline 的实验结论混用。

**验收**：至少得到一份真实的 `Qwen3.8-27B` 部署工件清单（仓库/revision、量化格式、软件及设备版本）、一次加载与 API 正确性证据，以及在可用的 TP/副本配置下可复核的 TTFT、TPOT、P95、吞吐与每卡 HBM。若没有八卡访问，只能标记为**兼容性方案已核查、实际部署待验证**。

**进入 DeepSeek 的条件**：能够解释 Dense 模型的权重容量、TP 与副本为什么是不同策略；然后才研究大型 MoE 的“总参数与激活参数分离、专家路由、EP 和跨卡通信”这些新增问题。

### 阶段 6｜DeepSeek-V4-Flash-0731 为什么不能按“13B 小模型”部署？

**首要问题：官方写着 13B 激活参数，为什么仍需要认真评估八卡 HBM？**

DeepSeek V4 Flash 是 **284B 总参数、约 13B 激活参数**的 MoE。激活参数量主要帮助理解每个 Token 参与计算的参数规模；模型权重存储仍需要考虑**完整模型、精度、分片和专家分布**。

因此，不可以写成：

~~~text
错误估算：13B 激活参数 × 1 字节 ≈ 13GB 权重
正确思路：284B 总参数 × 各模块实际量化精度
         + 路由/索引/通信/缓存/工作区
         → 再由软件支持的并行拓扑分配到多卡
~~~

官方 [vLLM-Ascend V4 Flash 指南](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html) 列出 **`DeepSeek-V4-Flash-0731-w8a8`** 在 Atlas 800I A2（64GB × 8）或 A3 参考服务器上的部署候选。对有昇腾 910B4 资源的实验，应以此为**软件兼容性和硬件验证的起点**。

此阶段先形成兼容矩阵：

| 必须确认 | 为什么不能略过 |
| --- | --- |
| 准确的 0731 W8A8 权重及来源 | Preview、0731、云 API 别名不是同一个版本 |
| A2 节点 NPU 实际型号、互联、HBM | 文档列出的 A2 参考环境不自动等同任何安装方式 |
| 驱动、固件、CANN、PyTorch NPU、vLLM-Ascend 镜像 | 推理引擎实际支持取决于版本组合 |
| 量化方法和模型算子 | NVIDIA 原生 FP4/FP8 方案不能直接当成昇腾 W8A8 配方 |
| TP/EP/DP 及对应脚本 | 多卡工作不是简单求和显存 |
| 设备绑定、HCCL 通信、容器挂载和网络 | 不通的多卡集体通信会阻止模型启动 |
| 目标上下文和单实例资源上限 | 官方宣称 1M 能力不等于每次都要配置 1M 生产上下文 |

**验收分层**：先证明**环境与镜像就绪**，再证明**模型权重实际加载成功**，然后证明**固定文本请求和流式/工具调用等所需接口行为正确**。这三个 Gate 不能因为启动进程存在就合并成“部署成功”。

**边界**：无八卡资源时，这一阶段可以完成文档核查、预算与路由兼容性检查；不能宣称已经实测了 910B4 上的 V4 Flash。

### 阶段 7｜大型 MoE 服务慢在哪里？什么时候要调 TP、EP 或分离 Prefill/Decode？

**首要问题：八张卡已经成功加载权重，为什么仍可能无法满足业务高峰？**

针对固定 DeepSeek 权重和同一套业务请求，先在官方支持的聚合式单节点 Serving 路径上测试，再考虑更复杂的设计。

需要理解：

- **Prefill 与 Decode**：长输入计算和逐 Token 生成对资源的压力不同。
- **MoE 与专家分布**：不同请求可能激活不同专家，专家并行需要设备间通信。
- **TP / EP / DP**：模型参数分片、专家分布和请求复制解决的不是同一问题。
- **混合注意力与 KV 状态**：不能直接把传统全注意力模型的 KV Cache 估算套到 V4 的全部层。
- **缓存和调度**：Prefix Cache、请求批处理和长上下文上限会改变延迟与容量。
- **跨卡通信**：卡数增加还带来通信与同步成本。

在固定上下文和负载下记录 TTFT、TPOT、P95、吞吐、HBM 峰值、队列、HCCL/设备报错、恢复行为。再决定是否值得比较不同并行策略、MTP/推测解码或 Prefill-Decode 分离。

**不要在还没有基本压测结果时，直接把 PD 分离、KV Pool、多副本和复杂推测解码全部打开。** 官方有些 PD 组合是参考设计，有些性能数据带有特定镜像、算子或实验修改条件；应先核实它们适用的版本。

**验收**：在同样的总设备数、输入输出分布和质量要求下，能解释一次性能差异具体来自排队、计算、通信、缓存还是资源限制。没有对照数据时，不声称“TP=4 一定比 TP=2 快”。

## 八、实践阶段 8—9：把 OCR 引入同一个模型服务体系

### 阶段 8｜一个 OCR 模型接口，为什么不能直接等同于整份 PDF 解析？

**首要问题：模型已经能够识别一张图片中的文字，为什么复杂表格、跨页标题和扫描偏斜仍然处理不好？**

选择 `PaddleOCR-VL-1.5` 作为首轮固定版本，再以 `PP-OCRv5` 等传统 OCR 路径作为可选基线。

真实的文档解析至少涉及：

~~~text
PDF / 图片输入
       ↓
页面渲染、方向调整、分辨率和质量检查
       ↓
版面分析：段落、表格、标题与图片区域
       ↓
OCR / 视觉语言模型识别内容
       ↓
表格、阅读顺序、跨页结构与坐标整理
       ↓
Markdown / JSON + 页码、位置与证据
       ↓
业务字段校验或后续语言模型分析
~~~

不同 OCR Pipeline 会组合不同组件；此图用于解释职责，不声称 PaddleOCR-VL 的所有步骤都使用独立模型。

**重点认识：只启动 VLM 的 OpenAI-compatible 端点，并不等于已经提供完整 PaddleOCR-VL 文档解析服务。** 应使用官方 Pipeline 或经验证的完整部署流程。

### 硬件路径不要混淆

- **NVIDIA 路线**：PaddleOCR 官方高性能服务将 FastAPI Gateway、Triton 及 vLLM 等组件组合，实现多请求处理；该方案目前明确标注为 NVIDIA GPU 路径。
- **昇腾路线**：PaddleOCR 提供独立的 [华为昇腾 NPU 部署教程](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL-Huawei-Ascend-NPU.html)，已描述 910B 上的验证，但应针对 910B4、所用版本与实际硬件再次确认。
- **低成本起步**：可先在符合要求的机器上运行传统 OCR 或小样本的 Pipeline 正确性测试，不能把它的性能指标冒充 GPU/NPU Serving。

**实验文档**：固定一组合法脱敏的单页/多页图片和 PDF，覆盖清晰文本、低清晰度、旋转、表格、跨页以及空白页。保存每页文字、区域坐标、结构化结果、失败页及耗时。

**验收**：不只验证“能输出文字”，还需人工核对文字内容、页面位置、表格行列和可供回查的证据；尤其不能把表格展平后仍然返回 HTTP 200 视为解析成功。

### 阶段 9｜同一个 OCR 模型，为什么 PDF 服务还需要自己的队列和 API？

**首要问题：一份 30 页 PDF 和一张普通图片能否按同一条“单次推理请求”限流？**

OCR 服务的一个业务请求可能产生几十次页面渲染、版面检测和视觉推理。它的“文档请求数”并不等于“模型推理次数”。

需要设计适合文档的接口契约，例如：

~~~text
POST /v1/document-parses
  → 接收已授权文件或受控文件引用
  → 返回 document_job_id

GET /v1/document-parses/{document_job_id}
  → queued / running / completed / failed / needs_review

GET /v1/document-parses/{document_job_id}/result
  → 页面、块、表格、文本、位置与模型版本
~~~

这是建议的**业务接口设计**，不是 PaddleOCR 官方端点的逐字复刻。

实现时分别关注：

- 文件类型、大小、页数与解析权限；
- 不可信 PDF 的解析隔离、渲染资源预算；
- 长文档异步队列与单页并发上限；
- 失败页重试、部分结果、取消与幂等；
- 图片尺寸、页面复杂度与 OCR 实际吞吐；
- 文本、表格和版面结果的质量回归；
- 原文件保留、输出脱敏、审计及访问控制。

评测不仅包含 CER/WER 或字段准确率，还应关注表格单元格与行列结构、跨页关联、阅读顺序、页面覆盖和业务字段证据定位。

**验收**：提交固定多页文档后，可查询进度、核查每页结果与失败原因；一份文档的个别页面失败时，系统明确记录，不伪造“全文解析成功”。


## 九、实践阶段 10—12：从各项独立服务走向统一模型平台

### 阶段 10｜统一 Gateway：为什么不能只把四类服务端点放进配置？

业务应用需要 `qwen-small`、`qwen-27b`、`deepseek-flash-0731` 和 `document-parse`，却不应该直接知道每台服务器的设备、IP 和部署端口。

Gateway 应承担**模型注册、版本映射、鉴权、授权、路由、限流、审计和可观测性**，并将服务错误、取消与超时以明确契约返回。

例如：

~~~yaml
# 模型注册表的逻辑示意，不是某款网关可以直接加载的配置
routes:
  qwen-small:
    capability: chat
    pinned_weight: Qwen/Qwen3-4B
    backend: qwen-serving
  qwen-27b:
    capability: chat
    pinned_weight: Qwen/Qwen3.8-27B
    backend: qwen27b-ascend-serving
  deepseek-flash-0731:
    capability: chat
    pinned_weight: DeepSeek-V4-Flash-0731-w8a8
    backend: deepseek-ascend-serving
  document-parse:
    capability: document-parse
    pinned_pipeline: PaddleOCR-VL-1.5
    backend: paddleocr-serving
~~~

必须区分**业务模型别名、实际权重版本和部署实例**，避免云 API 别名悄悄变更底层模型而造成评测失真。

文本服务可以优先实现经验证的 OpenAI-compatible Chat Completions 接口，但不强制 OCR 复用文本聊天协议：文档解析通常是文件提交、异步作业、页级结果与表格结构等不同契约。

需要验证：错误码与重试语义、流式行为、模型访问权限、调用配额、路由到的真实模型版本，以及后端不可用时的明确失败。若用已有 API Gateway 或 AI Gateway 能满足需求，就不必自行开发新网关。

**验收**：同一业务调用方在不知道后端地址的情况下，能调用授权的模型能力；拒绝未授权模型、记录实际路由，且 OCR 和文本 API 不会因为“统一入口”而丢失各自所需的结构。

### 阶段 11｜版本发布和容量治理：模型返回 HTTP 200 就能上线吗？

模型更新后可能仍然正常响应，但输出格式、推理速度、工具调用或 OCR 识别准确性已经改变。因此发布至少需要检查：

| 发布关卡 | 需要证明什么 |
| --- | --- |
| 工件 | 准确权重、量化文件、Tokenizer、引擎与软件版本 |
| 运行 | 冷启动、就绪、显存/HBM、通信、超时与错误处理 |
| API | 模型别名、流式输出、响应字段、OCR 任务契约 |
| 性能 | 固定请求分布下的 TTFT、TPOT、P95、吞吐、队列和资源 |
| 质量 | 固定文本问题、条件分类、OCR 文字/表格/版面回归 |
| 安全 | 模型权限、文档访问、日志脱敏、出站与凭据边界 |
| 恢复 | 灰度、新旧实例切换、失败回滚、长期运行稳定性 |

对大模型可先在脱敏固定请求上离线验证，再逐步放行受控流量；NPU 资源不足时，先做可回滚的发布演练，而非在没有冗余的前提下宣称生产高可用。

**验收**：有新旧版本的对照记录，能展示一次升级失败后的回滚。性能必须带输入输出长度、并发与版本信息；不能只写“吞吐提升 30%”却没有可比较的负载。

### 阶段 12｜让 OCR、Qwen3.8-27B 与 DeepSeek 串起来，怎样验证整个平台？

选取一份**固定、合法、脱敏、含表格的 PDF 或图像文档**，构造端到端任务：

~~~text
业务应用提交文档
       ↓
PaddleOCR-VL-1.5：页面、版面、文本和表格识别
       ↓
程序校验：页码、表格结构、源文件证据和权限
       ↓
Qwen 小模型：简单分类/字段整理（确有必要时）
       ↓
程序规则：可确定字段直接校验或计算
       ↓
Qwen3.8-27B：完成中等复杂度的全文条件分析（可选路由）
       ↓
DeepSeek-V4-Flash-0731：仅对需要更强模型的困难样本生成解释或报告草稿
       ↓
业务 Checker：验证结论、原文证据和报告
       ↓
统一 Gateway：请求关联、模型版本、耗时、成本和审计
~~~

这是一条**用于检验平台的可选路由图**，不是说每份文档必须串行调用所有模型；尤其 **Qwen3.8-27B 与 DeepSeek 是优先做选择性路由与 A/B 对照，而非默认两次连续生成**。文本输入可绕过 OCR，简单规则不需要调用模型；如果 Qwen 的某项中间处理没有实际收益，也应该允许删除这一环节。

需要回答以下工程问题：

- OCR 漏了一行或错乱了表格，错误怎样传递到最终分析？
- 一份扫描文档变得模糊后，平台怎样区分 OCR 质量问题与语言模型判断问题？
- 大型模型占满 NPU 时，OCR 是否会被资源争用拖慢？
- 同一批文档分别由 Qwen3.8-27B 与 DeepSeek 处理，复杂条件准确率、延迟、显存和成本有何变化？
- 只有在什么可验证的条件下，才值得把请求从 Qwen 小模型升级到 27B、再升级到 DeepSeek？
- 某项服务超时或失败，最终业务是否如实说明未完成，还是输出看似完整的错误结果？

**验收**：不仅要三个服务各自能响应，更要做到最终结构化结果和报告可回查，业务与模型错误能定位到具体服务，版本和成本有记录，出现问题可以回滚。

这一阶段可用普通 Workflow 编排，不需要为了演示模型平台而自研 Agent Runtime。两者的职责边界见 [Agent Runtime 总论](../agent-runtime/README.md)：模型平台负责交付稳定推理与解析服务，Agent Runtime 负责决定任务如何多轮行动、调用工具、维护上下文和判断完成。

## 十、每个阶段怎样留下可复核的证据？

建议为所有模型服务实验建立统一记录契约，避免每个 Lab 都另造一套不可比较的指标。

| 记录 | 为什么必须保留 |
| --- | --- |
| 实验 ID、任务假设和运行日期 | 说明本次想验证什么判断 |
| 模型仓库、revision、权重/量化文件哈希 | 证明实际用了什么模型 |
| 硬件、驱动、CANN/CUDA、镜像、推理引擎 | 保证环境与软件版本可回溯 |
| `served_model_name` 到权重的映射 | 防止 API 别名与真实权重混淆 |
| 输入/输出 Token、图片大小或 PDF 页数分布 | 性能数据有明确负载口径 |
| Batch、并发、上下文、TP、EP、副本、缓存配置 | 支持解释性能差异 |
| TTFT、TPOT、P50/P95、吞吐、HBM 峰值及错误 | 定位容量瓶颈与可靠性 |
| 固定正确性样本、实际输出、人工核查 | 防止为了提升吞吐牺牲业务质量 |
| 失败、超时、取消、回滚及运行记录 | 证明故障时行为可解释 |

### 文件如何组织？

现在已存在的主要文件为：

~~~text
model-platform/
├── README.md
├── LEARNING_PATH.md
├── 01-vllm-inference-serving.md
├── 02-model-serving-capacity-planning.md
├── 03-model-artifacts-and-runtime-environment.md
├── 04-local-inference-to-model-api.md
├── 05-single-instance-concurrency-scheduling.md
├── 06-moe-and-multi-device-inference.md
├── 07-multimodal-ocr-serving.md
├── 08-model-gateway-capability-routing.md
├── 09-performance-and-quality-evaluation.md
├── 10-release-rollback-resource-governance.md
└── 11-end-to-end-business-inference.md
~~~

后续在实验**确实开始时**，再增量建立 `labs/qwen-small-serving/`、`labs/qwen27b-serving/`、`labs/deepseek-flash-0731/`、`labs/ocr-serving/`、`labs/unified-gateway/` 等目录。它们是规划名称，**目前并未创建**。

每个 Lab 至少包含运行配置或代码、输入样本、环境约束、测试和实际运行证据；大型权重、机密文档、私有 API Key 与未脱敏日志不得直接提交公开仓库。

模型 Serving 实验属于 `model-platform/`；Agent 机制实验属于 `agent-runtime/`；真实职位库与岗位研究业务数据继续由 job-rag 等业务仓库负责。

## 十一、应该按什么节奏推进？

| 里程碑 | 形成的真实闭环 | 要理解的核心机制 |
| --- | --- | --- |
| **M1：一个模型** | Qwen3-0.6B 推理和 Qwen3-4B Serving | 权重、Tokenizer、API、Prefill/Decode |
| **M2：中大型 Dense Serving** | Qwen3.8-27B 的 BF16/W8A8、TP、实例副本、长上下文与容量实测 | 先理解 Dense 多卡和 HBM，再为 MoE 建立对照基线 |
| **M3：DeepSeek 大型 MoE** | DeepSeek 0731 的八卡兼容验证与有条件的部署、压测 | 总/激活参数、专家并行、跨卡通信、请求吞吐 |
| **M4：OCR 文档服务** | PaddleOCR-VL 完整 Pipeline 与文本 Serving 共存 | 视觉输入、页面队列、结构化输出、OCR 质量 |
| **M5：一个受控平台** | Gateway、权限、限流、版本发布、回滚及端到端业务实验 | 控制面、数据面、服务治理与质量回归 |

**第一轮优先完成阶段 0—2**：先让低成本 Qwen 小模型有稳定的运行记录，再借助单实例 Serving 验证真正的 API 与并发。

有八卡 NPU 权限后，**先完成 Qwen3.8-27B 的 W8A8 / TP / 副本验证**，形成 Dense 模型的可测容量基线；再核对 DeepSeek 0731 的**软件/权重/硬件兼容矩阵**并部署 MoE 实验。暂时无法实测时明确标注待验证，不能拿官方性能或云 API 结果冒充本机成果。

OCR 可以在固定文档上先验证功能和质量，再决定 CUDA/NPU 的 Serving 组合；最后把三类能力交给 Gateway 治理。

现有 [01 · vLLM 原理](./01-vllm-inference-serving.md) 应在 Qwen 正式 Serving 后反复对照阅读；[02 · 容量规划](./02-model-serving-capacity-planning.md) 的 **Qwen3.8-27B** 正是阶段 5 的主要参考，应在部署与卡数实验中重点使用，并在 DeepSeek 多卡阶段对照复用。它们不是学完后就不再回看的教材。

## 十二、最终应形成怎样的工程判断能力？

学习的结果不是掌握几份启动命令，而是在实际模型服务问题面前能够解释：

**为什么选这版模型和权重？哪些资源决定能否加载？慢在 Prefill、Decode、排队还是设备通信？何时应量化、增大 TP、增加副本或收紧上下文？为什么 OCR 需要独立 Pipeline/API？多模型共同运行时怎样治理权限、限流、监控与发布？**

整条因果链应当连贯：

~~~text
业务能力和质量要求
       ↓
准确权重版本 + 成熟推理框架
       ↓
核对目标硬件、驱动和算子支持
       ↓
单实例正确性与 API 验证
       ↓
固定负载下的性能、显存和稳定性观测
       ↓
按瓶颈决定量化、并行、缓存、路由和副本
       ↓
加入 OCR 等不同类型的推理服务
       ↓
统一认证、监控、发布和回滚
       ↓
在真实业务结果中证明平台提供了可靠能力
~~~

我们研究模型服务平台的价值，是**理解并管理成熟模型/引擎的运行边界、做出可验证的部署与容量判断**；不以重新实现推理引擎、训练模型或自研 GPU/NPU 算子为前置条件。

## 官方资料与版本依据

- [Qwen3 官方仓库](https://github.com/QwenLM/Qwen3)
- [Qwen3 Dense：vLLM-Ascend 部署](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/Qwen3-Dense.html)
- [Qwen3.8-27B：vLLM-Ascend 官方 BF16/W8A8 部署与调优](https://docs.vllm.ai/projects/ascend/en/latest/tutorials/models/Qwen3.8-27B.html)
- [Qwen3.8-27B：官方模型权重与规格](https://huggingface.co/Qwen/Qwen3.8-27B)
- [vLLM 文档](https://docs.vllm.ai/)
- [vLLM-Ascend 支持矩阵](https://docs.vllm.ai/projects/ascend/en/main/user_guide/support_matrix/supported_models.html)
- [DeepSeek 官方更新日志：Flash 0731 与云 API 别名](https://api-docs.deepseek.com/updates/)
- [vLLM DeepSeek V4 Flash 推理配方](https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4-Flash)
- [DeepSeek V4 Flash：昇腾 A2/A3 官方部署指南](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html)
- [PaddleOCR 官方仓库](https://github.com/PaddlePaddle/PaddleOCR)
- [PaddleOCR-VL 完整 Pipeline](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [PaddleOCR-VL 昇腾 NPU 部署指南](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL-Huawei-Ascend-NPU.html)
- [PaddleOCR-VL 高性能服务参考（NVIDIA）](https://github.com/PaddlePaddle/PaddleOCR/blob/main/deploy/paddleocr_vl_docker/hps/README.md)
