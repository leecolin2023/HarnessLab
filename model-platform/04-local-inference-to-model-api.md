# 04 · 从本地推理到统一模型 API：为什么 `generate()` 能跑，还不等于模型服务可用？

> **学习目标**：理解一次进程内生成如何演进为常驻推理服务；掌握模型初始化、请求协议、Chat Template、流式响应、取消、错误、鉴权与观测的责任边界。
>
> **贯穿实验**：Qwen3-0.6B 先本地生成，Qwen3-4B 在兼容设备上通过 vLLM / vLLM-Ascend 提供 HTTP 服务。此时先不引入跨模型 Gateway；网关另在 [08](./08-model-gateway-capability-routing.md) 研究。
>
> **与前文的关系**：[03 · 模型工件](./03-model-artifacts-and-runtime-environment.md) 确认加载什么、在哪运行；本篇解决怎样让一次推理变成长期、稳定、可调用的能力；[05 · 并发与调度](./05-single-instance-concurrency-scheduling.md) 再研究请求增加后的计算与排队问题。
>
> **事实边界**：文中的示例命令仅展示 vLLM Serving 的基本接口形态，部署前应固定权重、软件版本与真实硬件支持；没有宣称当前 HarnessLab 已部署 Qwen 服务或完成压测。

## 一、既然 Python 可以调用模型，为什么还要启动 HTTP Server？

最早的实验可以是：

~~~python
# 结构示意：model、tokenizer 的加载方式取决于选定版本
inputs = tokenizer("请分析该岗位的技术要求", return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=128)
print(tokenizer.decode(outputs[0]))
~~~

这段代码最大的便利是简单。但它也隐藏了服务化时必须回答的问题：

**如果十个业务进程分别运行这段代码，究竟有几份权重被加载？**

如果每个进程各自加载一次 4B 模型，同一套权重和运行缓存可能被重复占用；进程更新或退出又触发重新加载。业务代码与推理框架也会被绑在同一个发布周期。

常驻推理服务改变的是生命周期：

~~~text
调用者 A ─┐
调用者 B ─┼── HTTP → 常驻 Serving 进程 → 已加载权重 + 推理调度器 → GPU/NPU
调用者 C ─┘
~~~

只需在服务启动时加载权重，后续请求共享模型实例及其调度能力。业务侧只负责提交输入与消费输出。

但“独立 HTTP 进程”并非绝对必须：对于低负载、专用进程、容错要求简单的程序，进程内推理仍有合理性。选择独立 Serving，是因为**复用权重、隔离生命周期、统一调用和集中调度**已经产生具体价值。

## 二、客户端的一段文字怎样真正变成模型的输入？

设想调用：

~~~json
{
  "model": "qwen4b-lab",
  "messages": [
    {"role":"system","content":"只依据给定原文分类"},
    {"role":"user","content":"有 Milvus 经验者优先。"}
  ],
  "max_tokens": 128,
  "stream": false
}
~~~

这是 OpenAI-compatible 风格的 Chat Completions 请求示例。

服务端至少完成：

1. 检查 HTTP 身份、参数与模型名；
2. 根据 `model` 找到已加载实例；
3. 利用该模型的 Chat Template 将消息、特殊 Token、可选工具定义组装成 Prompt；
4. Tokenizer 编码并检查上下文、输出限制；
5. 请求进入等待队列；调度器分配 Prefill / Decode 计算；
6. 采样产生 Token，按约定编码返回内容、使用量与结束原因。

客户端传入 JSON，并不意味着模型真的“读到了 JSON”。模型接收的是**经过模板处理后的 Token 序列**。因此，`generate(prompt_string)` 和 `chat(messages)` 即使文字类似，输出也可能不同。

Qwen3 的思考模式、停止 Token、工具调用解析方式还需要在本机实际版本中单独验证。不要把“API 兼容”误认为“行为完全兼容”。

## 三、如何搭建第一个能够被其他进程调用的 Qwen API？

对具备相应 NVIDIA GPU 和受支持版本的环境，vLLM 有 OpenAI-compatible Serving。命令可以表达为：

~~~bash
# 仅示意 CLI 形态；先确认软件和模型版本，再决定显存/上下文参数
vllm serve Qwen/Qwen3-4B \
  --served-model-name qwen4b-lab \
  --host 127.0.0.1 \
  --port 8000
~~~

生产中需要额外确定 Tokenizer 模板、设备参数、模型上下文上限及访问保护。**在昇腾 910B4 上不能照抄普通 CUDA 命令**，应按 vLLM-Ascend 对当前模型、驱动和 CANN 版本的支持指南装配。

请求示例：

~~~bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen4b-lab","messages":[{"role":"user","content":"你好"}],"max_tokens":32}'
~~~

只有收到有效的模型输出还不够。首次成功后还应查看：

- `/v1/models` 是否列出预期服务名；
- 一次请求的实际模板和 Token 用量是否符合预期；
- 不存在的模型名称是否被明确拒绝；
- 超出上下文的输入如何报错；
- 服务重启后多久真正就绪，而不仅是端口已监听。

vLLM 的服务端点与参数会随版本演进，以 [官方 Serving 文档](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/) 为准。

## 四、为什么流式响应不是“模型计算得更快”？

用户看到聊天产品通常是逐字出现答案。后台可以采用两种模式：

~~~text
非流式：
请求 → 等待模型完整生成 → 一次返回全部文本

流式：
请求 → Prefill → 首批 Token → 后续 Token 片段 → 完成事件
~~~

常见协议是 Server-Sent Events（SSE）：服务器在同一个 HTTP 连接上持续发送数据片段。客户端接收增量后，把它们拼成可展示的内容。

流式主要改善**用户看到首次有效输出的等待体验**；它未必减少模型的总计算量，也不保证总完成时间更短。

因此至少区分：

- **TTFT（首 Token 时间）**：用户多久看到第一次模型输出；
- **完整响应时间**：最后一个 Token 或结束事件何时到达；
- **TPOT / 输出 Token 间隔**：首 Token 后的生成节奏。

长输入可能使 TTFT 上升；长输出可能使完整响应时间上升。这是后续 [05](./05-single-instance-concurrency-scheduling.md) 和 [09 · 评测](./09-performance-and-quality-evaluation.md) 要处理的不同指标。

还要注意**流式消息不必等于按词或句子切分**。中文、JSON、工具调用参数都可能跨片段边界出现。客户端应使用协议事件重组，不能对每一个 Chunk 都尝试当作完整 JSON。

## 五、用户断开连接时，推理是不是立即停止？

不一定。

客户端超时、浏览器关闭、网络中断，是 HTTP 连接事件；推理后端是否收到取消信号、是否及时从调度队列移除请求，取决于 Serving 版本与具体代码路径。

对持续输出或长上下文请求，应该验证：

1. 客户端主动取消；
2. 服务端是否记录请求结束、取消或异常；
3. 对应计算资源多久被释放；
4. 其他请求是否能够继续正常处理。

错误也需要分层：

| 现象 | 可能的根因 | 应首先检查 |
| --- | --- | --- |
| 连接拒绝 | 进程未监听或端口映射错误 | 监听地址、容器网络、进程状态 |
| HTTP 400 | 参数、模型名或长度不符合接口要求 | 输入与实际 API 契约 |
| HTTP 401/403 | 鉴权或访问策略拒绝 | 身份、权限及代理配置 |
| HTTP 429 | 当前请求被限流或过载拒绝 | 配额与并发预算 |
| HTTP 5xx / 中途断流 | 引擎、驱动、设备或上游异常 | 请求 ID、设备日志和引擎状态 |

这些状态码是典型含义，并非某个版本保证严格按此分类。业务端要区分参数永久错误、可恢复暂时故障与实际结果未知，不能只写一个“重试所有失败”的装饰器。

## 六、有了 `--api-key`，为什么还可能存在未受保护的服务入口？

一个常见误解是：模型服务配置了 API Key，就能够安全暴露到公网。

[vLLM 官方 Serving 文档](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/) 明确提醒，`--api-key` 只覆盖特定 API 路径前缀，不能保证整个 HTTP 服务的所有端点都经过认证。例如某些版本的其他推理入口可能不受这项 Key 保护。

因此应当在模型服务前使用**受控的网络边界/反向代理**，明确允许公开的路径，并在 Gateway 实施身份、权限、配额、审计和出口策略。

同时，服务内部可以有专用管理和健康检查入口，但不能无条件将其向公共网络暴露。

**模型 API 的服务成功与平台授权是两件事。** vLLM 负责模型执行，企业模型 Gateway 则负责跨用户、跨服务的访问治理。

## 七、为什么服务端监控不能只记录“请求成功次数”？

想知道模型是否适合持续使用，至少需要三种不同的证据：

**启动状态**：模型有没有加载、进程是否存活、是否达到真正可服务状态。

**每次请求**：请求 ID、路由到的权重版本、输入输出 Token、TTFT、总耗时、结束/错误类型。

**资源与排队**：活跃请求数量、等待队列、GPU/NPU 利用、HBM、KV/状态缓存、错误与吞吐。

vLLM 提供 Prometheus 风格的生产指标，但**指标名称和可用字段以部署版本为准**；可参考 [vLLM Metrics 文档](https://docs.vllm.ai/en/latest/usage/metrics/)。

以一组固定、脱敏 JD 条件分类请求比较时，应该同时记录正确性，不能因为 HTTP 200 占比高就认为“模型理解准确”。这是业务质量与模型服务可靠性的区别。

## 八、本篇最小验收：从脚本到常驻服务，需要留下什么？

建议建立同一输入集的双路径对照：

~~~text
路径 A：Qwen3-0.6B 本地推理 → 原始输出
路径 B：Qwen3-4B Serving → 非流式/流式输出
                                       ↓
                           输入、模板、版本、Token、耗时、错误记录
~~~

注意 A/B 使用的模型规模不同，不用于直接判断“Serving 比本地 `generate()` 性能更好”；这组实验的目标是**分别证明本地推理和服务接口契约**。要评价同模型不同推理方式，必须固定相同的权重与负载。

最低限度应证明：服务能独立启动、返回可解析的响应、流式片段能够完整重组、错误与取消可被观察、模型别名能映射到准确的权重版本，并有明确的访问边界。

接下来 [05 · 单实例并发与推理调度](./05-single-instance-concurrency-scheduling.md) 将保持模型与 API 不变，研究更多请求进入后，队列、Prefill、Decode 与缓存怎样共同决定容量。

## 参考资料

- [03 · 模型工件与环境](./03-model-artifacts-and-runtime-environment.md)
- [01 · vLLM 的推理原理](./01-vllm-inference-serving.md)
- [模型平台学习路线](./LEARNING_PATH.md)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/)
- [vLLM Production Metrics](https://docs.vllm.ai/en/latest/usage/metrics/)
- [vLLM-Ascend Qwen3 Dense](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/Qwen3-Dense.html)
