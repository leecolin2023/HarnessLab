# 08 · 模型 Gateway 与能力路由：四类后端怎样统一接入，又不丢失各自的能力？

> **学习目标**：理解 Model Gateway 在模型服务平台中的位置，以及模型注册、访问权限、配额、路由、协议兼容、流式转发、故障切换和请求审计怎样协作。
>
> **贯穿场景**：企业已经拥有 Qwen3-4B、Qwen3.8-27B、DeepSeek-V4-Flash-0731，以及 PaddleOCR-VL-1.5 完整文档解析服务。业务程序不应知道它们的设备和端口，但应能明确选择需要的能力、版本与质量级别。
>
> **关联路线**：[阶段 10](./LEARNING_PATH.md)，承接 [04 · 模型 API](./04-local-inference-to-model-api.md) 与 [07 · OCR Serving](./07-multimodal-ocr-serving.md)；发布与运行治理在 [10](./10-release-rollback-resource-governance.md) 深入。
>
> **实现边界**：示例注册表与路由代码用于解释设计职责，不是当前 HarnessLab 已部署的网关配置，也不是任何具体厂商 Gateway 的可直接运行 YAML。

## 一、四个模型服务都已有 HTTP 地址，为什么还需要 Gateway？

假设一项企业办公任务要完成扫描件解析与复杂条件判断：

~~~text
业务应用
  ├── http://qwen4b-host:8000/v1/chat/completions
  ├── http://qwen27b-host:8000/v1/chat/completions
  ├── http://deepseek-host:8000/v1/chat/completions
  └── http://ocr-host:8080/...
~~~

初期在业务配置里写四个 URL 完全可行。但随着模型迁移、驱动升级、实例重启和权限需求变化，业务程序必须反复修改地址、认证方式、超时配置和回滚逻辑。

更麻烦的是，每个模型后台可能使用不同资源：Qwen 27B 占用部分 A2 NPU，DeepSeek 使用整组八卡，OCR 服务可能有 CPU/PDF 处理和 NVIDIA/Triton/VLM 多层流水线。

如果每个应用都自行访问后端，就很难统一回答：

- 某个用户有权访问哪些模型？
- 哪个服务名对应实际哪个权重版本？
- 同一模型有两个实例时，请求分配给谁？
- 当某类请求超额时，是排队、拒绝还是降级？
- 发生故障时，该如何知道这次调用经过了哪个后端？

这就是 Gateway 的价值：**把稳定的访问契约和变化的模型部署隔离开**。它不是“再训练一个判断模型”，也不一定是从头开发的新产品。

## 二、“统一接口”到底要统一什么？为什么不必统一所有请求类型？

最容易想到的是把四个服务全部包装成 `/v1/chat/completions`。

但不同任务的调用契约本来就有差别。

| 后端能力 | 常见输入 | 常见返回 | 与文本聊天 API 的关系 |
| --- | --- | --- | --- |
| Qwen3-4B | 消息与生成参数 | 流式/非流式文本 | 可验证 OpenAI-compatible Chat |
| Qwen3.8-27B | 消息、可能还包括多模态请求 | 文本或受支持的结构化输出 | 要按具体引擎验证兼容字段 |
| DeepSeek V4 Flash | 长上下文、推理/工具调用请求 | 文本流、可选工具调用语义 | 格式支持依赖权重、模板和后端 |
| PaddleOCR-VL Pipeline | 文件/文档引用、页数与解析选项 | 页级布局、表格、坐标与任务状态 | 不能只当作一次文本生成 |

所以应该优先统一**调用治理**：身份、授权、模型/能力注册、请求 ID、流式/错误语义、配额、审计、指标和版本标识。

至于能力接口，可分别定义：

~~~text
/v1/chat/completions        具有已验证文本 Chat 契约的模型
/v1/embeddings              仅当真实部署了 Embedding 能力
/v1/document-parses         文档解析业务接口
/v1/document-parses/{id}    解析任务查询
~~~

后两项是应用层示意，而不是 PaddleOCR 官方路径。

**统一模型平台不要求消除能力差异；它要求把差异显式表达，使客户端不会调用错误的能力。**

## 三、`model=qwen-27b` 与真正的权重版本是什么关系？

假设客户端调用：

~~~json
{
  "model": "qwen-27b",
  "messages": [{"role":"user","content":"识别岗位必备技术"}]
}
~~~

`qwen-27b` 是一个业务服务名。它可能指向一个 Qwen3.8-27B W8A8 实例；升级后又指向另一版权重。仅凭这个字符串，客户端无法证明实际生成来自哪一个 revision。

网关需要一份受控注册关系：

~~~yaml
# 设计示例：非任何具体网关可直接部署的语法
models:
  qwen-small:
    capability: chat
    artifact: Qwen/Qwen3-4B
    backend_pool: qwen-small-pool
  qwen-27b:
    capability: chat
    artifact: Qwen/Qwen3.8-27B
    quantization: w8a8
    revision: "<冻结后填写>"
    backend_pool: qwen27b-a2-pool
  deepseek-flash-0731:
    capability: chat
    artifact: DeepSeek-V4-Flash-0731-w8a8
    revision: "<冻结后填写>"
    backend_pool: deepseek-a2-pool
  document-parse:
    capability: document-parse
    pipeline: PaddleOCR-VL-1.5
    backend_pool: paddleocr-pool
~~~

在一次请求记录里，至少要关联：

~~~text
用户 / 应用身份 → 业务模型名 → 注册版本
                            ↓
                    实际后端实例
                            ↓
                  模型工件、推理引擎、硬件
~~~

这与 [03 · 模型工件](./03-model-artifacts-and-runtime-environment.md) 是同一条因果关系。**网关负责可变服务名，工件 Manifest 负责真实模型身份**；两者必须能相互追溯。

## 四、只要求用户带 API Key，能否保证所有模型调用都安全？

不够。

API Key 只能帮助识别某类请求，仍需判断**谁有权调用哪一模型、哪个租户、哪类文档，以及能消耗多少资源**。

以一个部署在内部网络的 Gateway 为例，至少考虑：

- **认证**：识别真实调用用户或业务服务，而非相信模型/客户端自行声明；
- **授权**：财报文档的 OCR、专门的高成本 DeepSeek 模型可能需要不同权限；
- **配额**：限制单用户的请求速率、Token 预算、文档页数、并行任务数；
- **网络隔离**：模型 Serving 的内部端口不要绕开 Gateway 直接暴露；
- **审计**：记录必要的请求主体、模型、版本和拒绝原因，而不是无条件保存敏感原文。

[vLLM Serving 文档](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/) 已指出 `--api-key` 并非保护所有服务端点的完整安全机制。因此 Gateway 前后的网络路径仍应限制可达地址和 HTTP 路由。

鉴权不是“模型自己决定这位用户可不可以”；应由执行前的程序策略和真实业务系统强制执行。

## 五、路由怎样判断该给小 Qwen、27B 还是 DeepSeek？

先区分**能力选择**与**质量/成本策略**。

### 第一层：能力匹配

如果请求是多页 PDF 的版面、表格和坐标解析，应交给 Document Parse Pipeline；不能因为 DeepSeek 是大型模型就默认它具有相同的 OCR 接口与质量。

如果请求是短文本分类，Qwen3-4B 可能已经足够；要不要升级到 Qwen27B 或 DeepSeek，必须根据固定质量集、成本和延迟证据判断。

### 第二层：版本与授权

即使用户请求一个模型，Gateway 也要判断它是否被允许、当前哪个权重版本处于稳定发布状态。

### 第三层：后端选择

同一能力有多个等价实例时，可按健康度、容量、队列或其他有证据支持的规则分发请求。

~~~text
请求进入
   ↓
验证身份与模型授权
   ↓
检查请求类型与能力契约
   ↓
按照注册表定位真实权重 / Pipeline
   ↓
选择健康且有容量的后端实例
   ↓
转发、记录请求状态、返回响应
~~~

这里**不默认让一个 LLM 再调用另一 LLM 决定路由**。多数模型名映射、权限和流量分配都可以用确定性程序实现；对于语义难度分级，才可能另行研究分类器或分层路由。

## 六、请求失败时，Gateway 应该自动换一个更大的模型吗？

不能无条件如此。

例如调用 Qwen3.8-27B 时服务返回暂时错误，网关可能考虑在**相同权重版本和相同接口保证**的健康副本之间切换。

但换到 DeepSeek 即使返回格式类似，也会改变：

- 语义质量和输出风格；
- 模型权重及可追溯版本；
- 请求成本、Token 行为和上下文能力；
- 工具调用/结构化输出兼容性；
- 某些情况下的数据驻留和访问权限。

所以“自动回退到另一模型”必须是**业务授权、质量验收和版本路由策略的一部分**，而不是出错时把模型名随便换掉。

尤其流式响应已发送部分内容后，失败时客户端可能收到半个答案。不能直接再从另一个模型开始一个新的流，并假装是同一次完整输出。

应显式处理：

~~~text
尚未开始执行 → 可判断是否重新路由
已执行但未返回 → 判明可否安全重试
已向客户端流式发送 → 返回中断状态；不得静默拼接两份模型内容
有副作用工具/文档任务 → 根据幂等键核查实际执行结果
~~~

故障恢复与“模型 API 可调用”是两套不同责任，不能靠无限重试掩盖真实失败。

## 七、限流为什么不能只用“每秒 10 次请求”？

十个长度为 100 Token 的请求，与十个输入 100K、输出 2K Token 的请求，可能给同一个文本 Serving 带来完全不同的计算负载。

同样，一次单页图片解析与一次五十页 PDF 解析也不能都当作等价的“一个请求”。

因此不同能力可设置不同配额维度：

| 能力 | 可以考虑的预算 | 为什么 |
| --- | --- | --- |
| 文本 Chat | 请求速率、输入/输出 Token、并发数 | Token 规模决定计算与状态消耗 |
| Qwen27B/DeepSeek | 模型级容量、租户权重、长 Context 限制 | 大型常驻实例与稀缺 NPU |
| OCR 文档 | 文件大小、页数、页面并发、总任务数 | PDF 渲染与视觉推理多阶段运行 |
| Gateway | 连接、流式请求、错误预算 | 保持入口稳定并施加背压 |

限流不仅是防止滥用，也是避免模型后端无限排队。系统接近容量时应让客户端得到**可解释的排队或拒绝结果**，而不是所有请求都接受后在引擎内部无限等待。

## 八、怎样证明 Gateway 真正比直接访问四个 URL 更可靠？

建立四类服务的模拟或实际后端；没有模型硬件时可以先用**明确标识的 Mock** 验证鉴权、模型注册、错误与路由，不得将模拟吞吐作为真实 NPU 结果。

逐项验证：

1. 已授权请求找到正确能力与版本。
2. 未授权模型及其他租户的文档被强制拒绝。
3. 模型后端地址变更后，客户端仍能按稳定名称调用。
4. SSE 片段完整转发，客户端取消不会无限消耗计算。
5. 同名服务的不同版本有可回查的真实权重记录。
6. 后端故障时不会错误标记成功或偷偷换掉质量标准。
7. 配额超限有清晰的错误和观测记录。
8. 多页 OCR 任务保留页级状态，而不是被压平为聊天文本。

**模型 Gateway 的本质不是一个“更大的反向代理”，而是把业务访问和不断变化的模型能力之间的契约管理好。**

后续 [09 · 性能与质量评测](./09-performance-and-quality-evaluation.md) 将解决：网关的所有调用都返回 200 后，怎样证明服务满足 TTFT、P95、质量和容量要求？

## 参考资料

- [03 · 模型工件](./03-model-artifacts-and-runtime-environment.md)
- [04 · 模型 API](./04-local-inference-to-model-api.md)
- [07 · OCR Serving](./07-multimodal-ocr-serving.md)
- [模型服务学习路线](./LEARNING_PATH.md)
- [vLLM OpenAI-Compatible Server 与 API Key 边界](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/)
- [PaddleOCR 高性能服务架构](https://github.com/PaddlePaddle/PaddleOCR/blob/main/deploy/paddleocr_vl_docker/hps/README.md)
