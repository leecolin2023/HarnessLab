# DeepSeek Harness SDK Minimal · Phase 0 实验

这是 **HarnessLab 的 Agent Runtime 原理实验**，不是招聘岗位研究业务代码。该实验原先暂放在 `job-agent`，现根据职责边界完整迁入本目录。

**要回答的问题**：Python SDK 怎样启动 dsh Runtime？模型如何通过工具与外部环境交互？一次运行的 Session 如何保存？哪些结论能从真实工具调用证明，哪些只是假设？

- [项目架构和逐行代码解读](./01-code-walkthrough.md)
- [Agent / Runtime 基础原理](../../README.md)
- [Agent Loop 运行机制](../../01-agent-loop-execution-mechanism.md)
- [Agent Runtime 学习路线](../../LEARNING_PATH.md)
- [JD Research Agent 独立业务仓库](https://github.com/leecolin2023/job-agent)

## 实验代码地图

| 路径 | 作用 |
| --- | --- |
| `src/run_phase0.py` | 验证 `DeepSeekHarness(...).run(...)`，保存运行元数据 |
| `src/session_report.py` | 解析已保存的 JSONL Session 事件种类，不展示原始负载 |
| `scripts/run-docker.sh` | 在 Linux 上检查环境、构建容器、运行实验、查看 Session |
| `docker/Dockerfile` | Python 3.12 与 DeepSeek Harness SDK 运行镜像 |
| `config/disable-session-upload.patch.yml` | 关闭额外附加 Session 事件的可选传输，**不关闭正常模型请求** |
| `tests/test_phase0.py` | 不连接真实模型的离线测试 |
| `../../../.github/workflows/agent-runtime-phase0-offline.yml` | 本实验独立的 GitHub Actions 离线检查 |

## Linux Docker 运行

进入 HarnessLab 仓库后：

```bash
cd agent-runtime/labs/sdk-minimal-phase0
bash scripts/run-docker.sh check
bash scripts/run-docker.sh test
bash scripts/run-docker.sh build
# 使用单独申请且可撤销的测试 API Key，通过安全方式设置 DEEPSEEK_API_KEY
bash scripts/run-docker.sh run
bash scripts/run-docker.sh inspect
```

如果需要固定 SDK 版本，可在构建前指定 `DSH_SDK_VERSION`；若当前配置的 `DSH_MODEL` 不在目标端点上可用，必须根据实际服务选择可用的模型 ID。

**安全前提**：`sdk-minimal` 的 `danger-full-access` 不会因为设置 `cwd` 而消失。Docker 使用只读根目录、部分资源限制与独立挂载，但默认 bridge 网络仍可出站，且容器内的 Bash 理论上可能访问环境变量中的 API Key。只使用可丢弃的工作目录和专用凭据，不放入银行内部资料或真实招聘个人信息。

## 已验证与未验证

已有的代码和历史离线测试验证的是包装层的基本逻辑；迁移后的工作流只执行 Python/Bash 静态检查及 FakeHarness 单元测试。**目前不宣称已在本目录完成真实 Docker + 模型 API + 工具执行 + Session Trace 的端到端实验。** 应当通过真实 Session 的调用与结果配对来验收。

## 为什么这套代码不放在 job-agent？

`run_phase0.py` 只检查目录，并不读取职位数据库、不分析 JD、不生成岗位研究报告。它用于理解 Harness SDK 和 Agent Loop 的基础机制，因此连同运行脚本、配置、测试一起迁入 HarnessLab；在 job-agent 中保留它会使业务仓库混入教学实验。之后真正实现岗位检索、证据引用、结果校验时，再在 job-agent 编写独立的业务入口。
