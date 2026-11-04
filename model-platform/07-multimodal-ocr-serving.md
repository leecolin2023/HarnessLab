# 07 · 多模态 OCR Serving：模型能识别图片，为什么还不能稳定解析一份 PDF？

> **学习目标**：区分 OCR/VLM 单次推理、版面分析、PDF 渲染、多页重组、结构化输出和服务治理；理解图像/页面/文档三层请求为什么需要不同的调度与质量标准。
>
> **贯穿模型**：固定 `PaddleOCR-VL-1.5` 为学习基线，必要时与 `PP-OCRv5` 等传统 OCR 路线对照；在 NVIDIA 上参考官方高性能服务，昇腾设备使用独立适配资料，不能假设同一 Docker 命令跨硬件通用。
>
> **对应路线**：[阶段 8—9](./LEARNING_PATH.md)。前面的 Qwen/DeepSeek 主要处理文本生成；本篇引入含页、图像、表格和结构的文档服务，随后在 [08 · Gateway](./08-model-gateway-capability-routing.md) 讨论怎样统一接入。

## 一、图片识别出了文字，为什么表格提取仍可能失败？

一份扫描版合同或岗位说明有两列表格：

~~~text
技术要求 | 条件性质
Python  | 必须
Milvus  | 优先
~~~

如果 OCR 只输出：

~~~text
技术要求 条件性质 Python 必须 Milvus 优先
~~~

文字看起来全部识别正确，却丢失了**行、列与单元格之间的对应关系**。

业务模型此时可能把 Milvus 也当作“必须”，但错误首次发生的位置其实是**文档结构重建**，不是 DeepSeek 的语义推理。

再看其他问题：多栏排版的阅读顺序、跨页表格、印章覆盖、倾斜照片、旋转、页眉页脚、标题层级。这些都说明“把一张图片送进模型”和“解析完整文档”不是同一项任务。

因此，OCR 服务首先必须明确要交付什么：**纯文字、带坐标的块、带结构的表格，还是可供业务溯源的整份文档**。

## 二、一份 PDF 进入文档解析 Pipeline，实际经过哪些步骤？

用一条典型链路理解：

~~~text
PDF 文件 / 多页图像
      ↓
文件检测、页数限制、访问权限和恶意输入隔离
      ↓
PDF 渲染 / 页面拆分 / 图像方向与分辨率处理
      ↓
版面分析：文本块、标题、表格、图片等区域
      ↓
OCR / VLM 识别与结构化推理
      ↓
阅读顺序、表格重建、跨页关联
      ↓
Markdown / JSON + 页码 / 坐标 / 表格结构
      ↓
字段校验、原文定位、业务结果
~~~

不同 Pipeline 的实际顺序和组件可能不同。此图用于说明**为什么需要多个职责**，不代表每一行都对应一个独立的 PaddleOCR 模型。

对一份十页 PDF，文档提交是一次业务请求；页面渲染可能发生十次，版面区域可能有几十个，VLM 推理次数则依赖页面与区域策略。

**因此“每秒处理多少文档”不能用“每秒处理多少图片请求”简单换算。** 文档页数和页面复杂度必须进入容量定义。

## 三、PaddleOCR-VL-1.5 是一个模型，还是一整条产线？

这里要区分两个层次。

**视觉语言模型（VLM）推理端点**：给定图片及相关提示，返回模型的视觉理解结果。

**PaddleOCR-VL 完整 Pipeline / Serving**：在真实文档输入上协调页面处理、版面、视觉推理、结构重组和输出。

[PaddleOCR 官方 Pipeline 文档](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html) 特别强调：底层 VLM 服务只是完整文档处理的一部分；不能因为 VLM 已经以 OpenAI-compatible 形式监听端口，就称已经部署了 PaddleOCR-VL 整体解析服务。

在 [官方高性能 Serving 参考](https://github.com/PaddlePaddle/PaddleOCR/blob/main/deploy/paddleocr_vl_docker/hps/README.md) 中，典型架构包含：

~~~text
文档客户端
    ↓
FastAPI Gateway：请求接入和并发约束
    ↓
Triton：版面处理与 Pipeline 组织
    ↓
vLLM：视觉语言模型推理
    ↓
多页结果重构与结构化输出
~~~

该参考的拆分可以让我们看到不同负载：GPU 上的模型推理、CPU 上的多页后处理、HTTP 层的文件和任务管理。

但它是**官方特定版本的部署组合**，并非部署 PaddleOCR-VL 的唯一方式，也不等同于企业统一 Model Gateway。

## 四、为什么 NVIDIA 的高性能方案不能直接复制到 910B4？

PaddleOCR 当前官方高性能方案明确标注为**NVIDIA GPU 路线**，配置依赖相应 CUDA、Triton、vLLM 后端及镜像。

对于昇腾，PaddleOCR 另有 [Ascend NPU 专用教程](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL-Huawei-Ascend-NPU.html)。

这两条路径之间不能作以下假设：

- 同名 PaddleOCR-VL 权重就拥有完全相同的视觉推理后端；
- NVIDIA 上成功的 Triton/vLLM 镜像可以直接绑定 910B4；
- 支持某一种 NPU 型号就代表所有 910B4 驱动/CANN 组合可用；
- 文本 API 正常返回就证明 PDF Pipeline 的表格、跨页和坐标输出符合要求。

更稳妥的演进是：

**先用官方支持环境在固定脱敏文档上验证完整解析输出；再固定模型和样本，评估目标硬件可运行的替代推理/服务路径。**

如果只有 CPU 或小型云服务器，可先研究 PDF 渲染、传统 OCR、结果 Schema 和业务校验；不能在没有 GPU/NPU 运行证据时宣称完成了 1.5 的高性能 Serving。

## 五、为什么 OCR 的并发调度不应该照搬文本模型？

Qwen/DeepSeek 的典型请求是输入 Token，经过 Prefill 与 Decode 返回 Token。OCR Pipeline 的任务单位却可能是：

- 文件：包含若干页面与权限；
- 页面：大小、DPI、方向、图像质量不同；
- 区域：文本、表格、图表的计算需求不同；
- 后处理：重排阅读顺序、跨页合并和序列化。

例如 1 个 60 页 PDF 与 60 个单页文件，虽然页数相同，却可能有不同的多页重建、内存管理和业务交付语义。

官方高性能部署中会区分推理操作与非推理操作的并发上限：版面/视觉推理占用 GPU，而多页重组等后处理可能主要占用 CPU。二者共用一个无限队列，容易出现资源争用与长尾延迟。

因此应该测量**各环节的队列和耗时**：

~~~text
提交等待 → PDF 渲染 → 版面推理 → VLM 推理
                                      ↓
                  多页后处理 → 结构化输出 → 业务校验
~~~

GPU 推理加速两倍，不一定让整份文档完成时间减半；如果大部分时间花在 PDF 渲染或跨页重构，瓶颈已经在别处。

## 六、一个文档服务的 API 为什么通常需要异步任务？

如果单页图像能快速处理，同步 API 可能足够。但几十页 PDF 的持续处理、页面失败重试和中途取消，不适合长期绑定一个浏览器 HTTP 连接。

建议应用层定义明确的业务任务：

~~~http
POST /v1/document-parses
Authorization: Bearer <token>
Content-Type: application/json

{"file_id":"approved-file-001","pipeline":"paddleocr-vl-1.5"}
~~~

服务器完成授权和文件检查后返回：

~~~json
{"document_job_id":"doc-001","status":"queued"}
~~~

随后可以查询每页处理状态，再取得结构化结果。这里是**企业应用层的教学 API**，不是 PaddleOCR 官方服务必须采用的端点。

业务状态至少应能区别：

- `queued`：已接收等待执行；
- `running`：正在解析；
- `completed`：符合完成契约；
- `partial` / `needs_review`：部分页面失败或结构待复核；
- `failed` / `canceled`：失败或取消。

用户取消时，系统必须区分“停止未开始的页”与“正在执行的页是否已产生结果”；重试应该使用文档/页面的稳定幂等键，避免生成重复报告。

## 七、识别质量如何定义？为什么只看 CER 不够？

CER（字符错误率）通常根据字符编辑距离相对参考字符数计算：

\[
CER=\frac{S+D+I}{N}
\]

其中 S 为替换、D 为删除、I 为插入，N 为参考字符数。OCR 文字越准确，CER 一般越低。

但一张表格可能每个字符都正确，行列关联仍然错位。对企业文档还需要验证：

| 质量层次 | 检查什么 | 为什么重要 |
| --- | --- | --- |
| 文字识别 | CER/WER、数字和特殊字符 | 关键金额或日期不能误读 |
| 阅读顺序 | 多栏正文、标题与段落顺序 | 影响后续语言理解 |
| 版面区域 | 文本块、表格、图片、印章位置 | 决定证据是否能回查 |
| 表格结构 | 单元格行列、合并关系与数值对应 | 不能只保留文字 |
| 跨页关系 | 表格续页、标题层级与页码 | 一份文件不等于孤立页面 |
| 业务字段 | 金额、日期、主体名称与原文证据 | 业务是否真正可用 |

注意 CER 依赖准确参考文本、归一化规则与对齐方式；不能简单把 Markdown 去掉所有结构后算一个低 CER，就认为复杂表格解析达标。

针对文档模型的已有公开基准也需要核查数据领域差异。公开 Benchmark 上表现优秀，不代表银行合同、财报或低清晰度扫描件已达到业务验收水平。

## 八、怎样设计三个层次的对照实验？

选择固定、合法、脱敏的 PDF/图片，覆盖清晰文本、旋转、扫描噪声、合并表格单元格和跨页表格。

**第一层：功能正确性。** 同一输入分别生成文字、版面与结构化结果，检查字段、页码和来源定位。

**第二层：模型/后端对照。** 在都受官方支持的条件下比较同一 Pipeline 不同推理后端或 OCR 方案，尽量保持图像渲染条件和评测口径一致。

**第三层：服务负载。** 用不同页数、图像大小、复杂度和任务到达率观察队列、GPU/NPU/CPU 资源、每页耗时与整文档 P95。

特别做一个失败实验：让某一页解析失败。文档任务应该给出明确页级失败与部分结果，不能只因其他页面正常就返回“全文解析成功”。

实验应保留：原始样本哈希、页面渲染配置、Pipeline 与模型版本、每页结果、表格结构、运行轨迹、错误与人工判断。**不要将未经脱敏的真实业务文档上传到公开仓库或外部诊断系统。**

## 九、OCR 与语言模型服务的边界到底在哪里？

一份扫描版 JD 进入系统后：

~~~text
OCR Pipeline：恢复原始文字、表格、位置与页面证据
                ↓
业务程序：确认字段、版本、证据与结构完整性
                ↓
Qwen / DeepSeek：理解复杂条件、形成解释
                ↓
业务 Checker：核查判断是否得到原文支持
~~~

这不代表 OCR 必须与大模型部署在一张卡上，更不代表每份纯文本都需要视觉推理。

**OCR 的服务目标是让文档内容与结构被可靠还原；语言模型的服务目标是提供文本/多模态推理能力；业务任务是否正确完成，则仍需应用层验收。**

下一篇 [08 · 模型 Gateway 与能力路由](./08-model-gateway-capability-routing.md) 将解决这三类服务如何通过统一访问控制接入应用，同时保留各自的协议与资源差异。

## 参考资料

- [模型平台学习路线](./LEARNING_PATH.md)
- [06 · MoE 多卡推理](./06-moe-and-multi-device-inference.md)
- [PaddleOCR 官方仓库](https://github.com/PaddlePaddle/PaddleOCR)
- [PaddleOCR-VL Pipeline 使用说明](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [PaddleOCR-VL-1.5 介绍与评测](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL-1.5.html)
- [官方高性能 Serving（NVIDIA）](https://github.com/PaddlePaddle/PaddleOCR/blob/main/deploy/paddleocr_vl_docker/hps/README.md)
- [PaddleOCR-VL Ascend NPU 教程](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL-Huawei-Ascend-NPU.html)
