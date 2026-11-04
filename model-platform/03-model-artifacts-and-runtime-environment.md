# 03 · 模型工件与运行环境：为什么同一份权重换台机器就跑不起来？

> **学习目标**：掌握从模型仓库到可重复部署的完整工件链，区分权重、配置、Tokenizer、Chat Template、量化格式、推理引擎、驱动与硬件之间的依赖。能够解释“下载成功”“加载成功”“正确生成”和“可复现服务”为什么是不同结果。
>
> **贯穿实验**：先用 Qwen3-0.6B 在普通机器上完成最小生成，再把 Qwen3-4B 转为 Serving，最后为 Qwen3.8-27B 的昇腾 910B4 W8A8 部署准备兼容矩阵。DeepSeek-V4-Flash-0731 和 PaddleOCR-VL-1.5 作为工件结构不同的对照。
>
> **关联路线**：[学习路线阶段 0—1](./LEARNING_PATH.md)，承接 [01 · vLLM 推理原理](./01-vllm-inference-serving.md) 之前的环境准备，后续进入 [04 · 从本地推理到模型 API](./04-local-inference-to-model-api.md)。
>
> **实施边界**：本文的命令、配置与结果是教学模板，尚未在 HarnessLab 对指定 910B4 服务器进行验证；软件和量化支持请以实际固定版本的官方文档为准。

## 一、模型仓库下载完成，为什么 `generate()` 仍可能失败？

我们要运行 Qwen3-0.6B，很容易想到“下载模型 → 调用推理函数”。

但真正的调用链至少是：

~~~text
模型仓库与 revision
       ↓
权重文件 + 模型结构 config + Tokenizer + Chat Template
       ↓
推理框架识别模型架构、权重格式与量化方案
       ↓
CUDA / CANN / 驱动 / 设备运行时准备资源
       ↓
内存/HBM 分配、算子与执行图初始化
       ↓
Tokenizer 编码 → Prefill → Decode → Tokenizer 解码
~~~

例如权重文件完整，却因 Tokenizer 版本不匹配而生成乱码；模型架构被 transformers 支持，但当前 vLLM 版本尚未注册相应执行实现；量化权重格式是特定后端的 W8A8，换到 CPU 或通用 CUDA 后端不能直接解释其算子。

因此**权重只是模型工件的一部分，不是一个可以脱离软件环境独立运行的程序**。

## 二、一个模型仓库里到底要固定哪些东西？

以 Hugging Face / ModelScope 风格的模型目录为例，常见的文件与作用如下。不同模型仓库的实际文件名并不相同。

| 工件 | 解决的问题 | 缺失或错配时会怎样 |
| --- | --- | --- |
| `config.json` | 层数、维度、架构类型、注意力/专家配置 | 引擎可能无法构建正确的模型结构 |
| `*.safetensors` 与权重索引 | 保存参数张量、分片与张量到文件的映射 | 加载缺失、张量尺寸不一致或权重错误 |
| `tokenizer.json` / 词表与特殊 Token | 文本怎样映射为 Token ID | 同样文字被编码成不同输入 |
| `tokenizer_config.json` 与 Chat Template | System/User/Assistant/Tool 消息怎样排成输入 | 对话角色边界、停止行为和工具调用异常 |
| `generation_config.json` 或部署生成参数 | EOS、采样、长度等默认行为 | 输出长度或停止条件不同 |
| 量化配置及对应权重 | 权重/激活精度、缩放系数、量化算子约束 | 推理内核不支持或质量偏差 |
| 许可证及使用说明 | 是否允许当前用途和再分发 | 工程可运行却不满足使用约束 |

**同一个模型名称可能同时对应 BF16、W8A8、GGUF 等多种工件；不是把“model=Qwen27B”写进日志就完成了版本固定。**

还要记住，模型文件中的 `model_type`、自定义代码与引擎的模型注册路径是兼容性的一部分。如果加载需启用 `trust_remote_code`，应先核查代码来源和风险，不要为解决兼容错误直接把任意仓库代码交给高权限运行进程。

## 三、Tokenizer 与 Chat Template 为什么会改变同一模型的回答？

假设业务给模型发送一句话：

> 分析这条 JD 中哪些是必备条件。

本地一次 `generate()` 如果直接把这句话编码成 Token，与 HTTP Chat API 把它包装成 System/User 消息，**实际输入 Token 序列未必相同**。

~~~text
业务消息列表
   ↓ Chat Template
角色标签、特殊 Token、工具定义与正文合成为模型输入
   ↓ Tokenizer
Token IDs
   ↓ 推理引擎
下一 Token 的概率分布与输出
~~~

模型不能直接理解 HTTP 的 `role=user` JSON 字段。是 Chat Template 约定了这套消息怎样进入模型。

对 Qwen3 系列，还应固定 thinking/non-thinking 相关模板设置与输出处理方式。比如某次测试允许内部思考，而另一次禁用或改写模板，即使模型权重相同，也不能把延迟和输出长度差异简单归结为推理框架。

### 最小验证该怎么做？

针对固定、脱敏输入，保存：原始消息数组、实际渲染后的模板输入（按数据保护需要脱敏）、Tokenizer revision、生成配置、最终输出与 Token 数量。

如果一次模型升级后 Tool Calling 格式发生变化，应先比对模板、特殊 Token、工具 Schema 和输出解析器，再讨论模型本身是否“退化”。

## 四、BF16、W8A8 与 GGUF 为什么不能当作同一个模型文件的不同后缀？

在 [02 · 容量规划](./02-model-serving-capacity-planning.md) 中已经用 Qwen3.8-27B 推导了 BF16 约 54GB 的**理论基础权重体积**。

但实际部署面对的是不同的**量化表达与执行后端**：

- **BF16**：通常每个权重参数约 2 字节；还需要运行时缓存、工作区与其他模块。
- **W8A8**：一般指权重与相关激活量化到 8 位，实际是否全部模块量化、采用哪种缩放粒度、如何处理异常值要查对应部署方案。
- **GGUF**：是一种模型文件封装/推理生态常用格式，里面仍可能有多种量化类型；不能把 GGUF 本身误当成一种固定精度。
- **AWQ、GPTQ、FP8 等**：属于不同量化方案或数值表达，涉及不同算子与软件适配。

拿到文件之后要回答三个问题：**它究竟量化了哪些张量？当前设备后端会用什么内核执行？相同任务的质量是否能接受？**

例如官方 [vLLM-Ascend Qwen3.8-27B 指南](https://docs.vllm.ai/projects/ascend/en/latest/tutorials/models/Qwen3.8-27B.html) 提供 A2 设备的 BF16/W8A8 参考方案，同时列出针对 Ascend 950 的其他量化路径。不能把 950 的 MXFP8 方案复制到 910B4 就认为软件已经支持。

**文件体积小，不等于端到端运行一定更快。** 解量化、算子支持、通信、缓存和质量损失都可能改变结果。

## 五、驱动、CANN、PyTorch NPU 与 vLLM-Ascend，究竟谁依赖谁？

把 910B4 想象成独立的一张“64GB 显存卡”是不够的。软件需要真正找到设备、建立运行上下文并执行兼容算子。

一个简化的环境依赖图是：

~~~text
操作系统 / 容器与设备节点
            ↓
NPU 固件 + 驱动 + 设备通信
            ↓
CANN / ACL / 算子与运行时库
            ↓
torch-npu / vLLM-Ascend 等适配层
            ↓
vLLM 模型执行器 + 模型架构与权重
            ↓
HTTP Serving 与业务请求
~~~

版本不兼容可能在不同阶段出现：容器看不到设备、Python 无法导入包、模型结构不受支持、算子缺失、多卡 HCCL 通信失败、权重能加载却首个请求崩溃。

因此要用**分层验证**定位失败：

1. 宿主机是否枚举实际 NPU？
2. 容器是否能访问获得授权的设备与驱动？
3. 运行时库、引擎和 Ascend 适配模块是否能导入？
4. 当前模型架构、权重/量化和目标 TP 是否在支持矩阵里？
5. 模型是否真正加载并完成一次 Prefill/Decode？
6. 多卡连续请求、长上下文和并发是否稳定？

阶段 3 成功不代表阶段 5 一定成功，阶段 5 成功也不代表吞吐已达生产标准。

## 六、怎样给 Qwen3.8-27B 制作一份可审计的部署清单？

避免以“同事上次这么部署过”作为唯一依据。建议把实际可复现的配置写成一个 Manifest。

~~~yaml
# 教学用 manifest：字段代表需要记录的信息，不是直接执行的引擎配置
experiment_id: qwen27b-a2-baseline
model:
  repository: Qwen/Qwen3.8-27B
  revision: "<经确认的 revision>"
  weight_variant: "<BF16 或指定 W8A8 权重仓库>"
  artifact_digest: "<权重校验和或快照哈希>"
  tokenizer_revision: "<对应版本>"
runtime:
  engine: vllm-ascend
  engine_version: "<固定版本>"
  torch_npu_version: "<固定版本>"
  cann_version: "<固定版本>"
  driver_version: "<固定版本>"
device:
  type: Ascend-910B4
  visible_devices: "<实际分配的设备列表>"
serving:
  tp: 2
  max_model_len: "<本次测试值>"
  max_num_seqs: "<本次测试值>"
  served_model_name: "qwen27b-exp"
validation:
  sample_set_digest: "<脱敏测试集哈希>"
  status: planned
~~~

这里的 `tp: 2` 是**与官方参考配置对齐的候选起点**，不是任何机器都已实测成功的结论。

还要注意精确工件与“服务别名”不同：模型请求里写 `qwen27b-exp` 并不足以反推出底层正在运行哪个 revision。平台必须保存别名到实际部署实例的映射。

## 七、怎样验证“可复现”，而不是仅仅保存了一个版本号？

一份部署清单应该支持他人在可获得的等效设备上，重复以下检查：

~~~text
验证 1：下载的权重、Tokenizer 和配置与 Manifest 一致
验证 2：引擎和驱动可以运行，模型成功加载
验证 3：固定输入能生成符合接口契约的输出
验证 4：连续、流式与异常请求的行为符合预期
验证 5：同负载下的耗时、HBM 与质量在可解释范围内
~~~

对**输出完全一致**要谨慎：GPU/NPU 并行、不同算子、采样参数和服务端版本都可能使生成不完全逐字相同。可复现首先要求**工件、配置、过程与质量判据可回查**，不等于所有运行环境都会产生逐字一致的自然语言。

可以用三个标签跟踪状态：

- `planned`：版本与方法已规划；
- `compatible_checked`：已确认文档或配置支持，但未实际加载；
- `validated_on_hardware`：实际设备上有加载、请求、错误与质量记录。

不能把官方文档给出的参考吞吐冒充当前服务器自己的实测结果。

## 八、模型发布到平台，哪些文件属于部署责任，哪些属于业务责任？

模型平台需要管理工件、引擎镜像、设备、服务配置、鉴权、限流和模型版本；而业务应用负责确定“岗位职责中出现 RAG”的统计口径、读取哪些 JD、生成报告的证据与验收。

即使模型版本完全锁定，也无法代替业务 Checker 证明报告正确；反过来，业务 Prompt 再规范，也无法修复设备算子与权重不兼容。

**模型工件的可复现性，是下游 API 兼容、性能 A/B、质量回归和安全回滚的共同前提。** 如果实际权重版本都说不清，后续评测不具备可解释的比较基础。

下一篇 [04 · 从本地推理到统一模型 API](./04-local-inference-to-model-api.md) 将从一份已经验证可加载的 Qwen 权重出发，解释为什么服务必须常驻、如何接入请求和生成流式输出。

## 参考资料

- [模型服务完整学习路线](./LEARNING_PATH.md)
- [01 · vLLM 推理服务机制](./01-vllm-inference-serving.md)
- [02 · 模型服务容量规划](./02-model-serving-capacity-planning.md)
- [Hugging Face Transformers：Chat Templates](https://huggingface.co/docs/transformers/chat_templating)
- [Hugging Face Hub：版本与 Revision](https://huggingface.co/docs/huggingface_hub/guides/download)
- [Qwen3 官方项目](https://github.com/QwenLM/Qwen3)
- [vLLM-Ascend：Qwen3.8-27B 模型部署](https://docs.vllm.ai/projects/ascend/en/latest/tutorials/models/Qwen3.8-27B.html)
- [vLLM-Ascend：支持矩阵](https://docs.vllm.ai/projects/ascend/en/latest/user_guide/support_matrix/supported_models.html)
