# 企业制度知识引擎 · RAGFlow 原生 MCP × DSH 集成 Runbook V0.1

> **状态**：实施说明 / 尚未在用户环境部署或验收。2026-10-10。  
> **不修改** RAGFlow 源码、不修改 DSH Agent Loop、不创建第二个 RAG Agent。  
> 版本基线：RAGFlow [v0.27.2](https://github.com/infiniflow/ragflow/tree/v0.27.2) + [dsh-intramate/dsh-intramate-dev](https://github.com/leecolin2023/dsh-intramate/tree/dsh-intramate-dev)。  
> 本文和示例不包含真实银行制度、内部网络信息或 API Key。

## 0. 首轮架构（零新增产品代码）

```text
IntraMate Desktop / dsh web
    └─ DSH 原生 Agent Loop + Session + Tool Registry
         └─ @deepseek-ai/dsh-mcp-client (官方)
              └─ Streamable HTTP /mcp
                   └─ RAGFlow v0.27.2 官方 MCP Server（独立进程，未修改源码）
                        └─ RAGFlow REST /api/v1/retrieval
                             └─ 政策制度 Dataset / 已解析索引
```

DSH 原生支持 Cordis MCP 配置，工具自动注册并进入 DSH 权限和结果记录链路。RAGFlow 自带 MCP Server，**无需自己再开发适配器**。

- [DSH 原生 MCP client 配置源码与文档](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/packages/mcp/mcp-client/README.md)
- [DSH Cordis overlay 用法](https://github.com/leecolin2023/dsh-intramate/blob/dsh-intramate-dev/docs/user/guide/mcp-memory.md)
- [RAGFlow v0.27.2 官方 MCP Server](https://github.com/infiniflow/ragflow/blob/v0.27.2/mcp/server/server.py)
- [RAGFlow v0.27.2 Docker Compose](https://github.com/infiniflow/ragflow/blob/v0.27.2/docker/docker-compose.yml)

## 1. 环境与安全前提

- 优先同一开发机器：Windows 的 WSL2 + Docker Desktop，或 Linux x86-64 + Docker。**4 CPU / 16 GiB RAM / 50 GiB 空闲磁盘出自 [RAGFlow v0.27.2 官方 README](https://github.com/infiniflow/ragflow/blob/v0.27.2/README.md#prerequisites) 的通用部署前置条件，并非本项目数百份制度的实测资源需求，也不是模型本地推理的容量测算。** CPU 不代表本地 LLM 有足够性能；后续需按实际制度数量、页数、扫描比例、索引策略、模型部署位置、并发进行分阶段资源测量。
- 在封闭/授权环境处理银行制度；只上传已获授权文件到**本地/内网** RAGFlow，不上传真实制度到公共 GitHub、公共演示服务或模型 API。
- 首轮只允许一个可信开发者、一份专用低权限 RAGFlow 凭据和限定的制度 Dataset；**官方 v0.27.2 MCP self-host mode 以服务端凭据代表所有客户端**。即使模型遵循提示指定 Dataset，也不能作为安全边界。
- 正式多用户阶段必须先证明身份→知识库→文档→检索→缓存→MCP→Session 的隔离；无法证明则不开放多用户。v0.27.2 的 Compose 注释提示 **host mode + streamable-http 尚不支持**，与 DSH 当前所支持的 Streamable HTTP 形成约束；不得默认使用 host mode 解决权限。
- RAGFlow 的默认数据库/搜索引擎密码必须在部署前更换。MCP 本地端口绑定 `127.0.0.1`；跨主机经身份验证的私网代理或 SSH 隧道，勿直接暴露无鉴权 self-host MCP。

## 2. 启动 RAGFlow 官方版本（源码不修改）

终端 A（bash / WSL2；仅下载上游源码和运行官方镜像）：

```bash
git clone --branch v0.27.2 --depth 1 https://github.com/infiniflow/ragflow.git
cd ragflow/docker
# 修改本地 docker/.env 中的默认密码；核对镜像 tag、资源与端口
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs --tail=100 ragflow-cpu
```

一般默认 Web：`http://127.0.0.1/`，HTTP API：`http://127.0.0.1:9380`；以本机 `docker/.env` 的 `SVR_WEB_HTTP_PORT`、`SVR_HTTP_PORT` 为准。

**先配置 RAGFlow 自己的模型服务**（至少 embedding；复杂解析/知识编译和生成还需要匹配的 LLM、OCR/VLM 或 Rerank 能力），再建库。若必须离线运行，模型也必须是内网/本地端点。

### 第一次导入

1. 新建专用 Dataset，例如 `BANK-POLICIES-POC`，用它承载首轮制度样本；先选好 embedding 模型，确保所选模型可稳定运行。
2. 先上传 10–20 份具有代表性的授权制度（Word、文本 PDF、扫描 PDF、含表格/附录各若干），手动选择解析/Chunk 模板，逐个触发解析。
3. 检查文档是否全部解析结束、分块是否保持条号/标题和例外条件；尚不启用 Graph/Tree。记录失败、错乱条款、文本缺失。
4. RAGFlow 的 Retrieval Testing 中验证至少 5 道已知答案的问题。未命中不进入 DSH 集成排查，先解决文档/索引端问题。
5. 使用专用 RAGFlow 账号创建 API Key（切勿放在 Git 仓库）；记录 Dataset ID。

### 先独立测试 REST API（与 MCP/DSH 排错隔离）

```bash
# 交互输入，不将真实密钥写入命令行或仓库
read -rsp "RAGFlow API Key: " RAGFLOW_API_KEY; echo
export RAGFLOW_API_KEY
export POLICY_DATASET_ID="<from-ragflow-ui>"
curl -fsS -X POST "http://127.0.0.1:9380/api/v1/retrieval" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  -d '{"question":"请查找授信审批权限的有关条款","dataset_ids":["'"$POLICY_DATASET_ID"'"],"page_size":5}'
```

预期：HTTP 200、响应业务码 `code=0`、`data.chunks` 含目标条款/来源信息（字段实际以版本 API 为准）。**检索为空时先不要调 DSH Prompt。**

## 3. 启动 RAGFlow v0.27.2 原生 MCP Server（不改 RAGFlow）

**推荐首轮用上游自带的独立脚本进程**，避免为启用 MCP 修改官方 Compose 里的 `command`。终端 B（在 `ragflow/` 仓库根目录运行；确保安装了该版本所需的 `uv` 与 Python 环境）：

```bash
read -rsp "RAGFlow MCP test API Key: " RAGFLOW_MCP_HOST_API_KEY; echo
export RAGFLOW_MCP_HOST_API_KEY
uv run mcp/server/server.py \
  --host=127.0.0.1 \
  --port=9382 \
  --base-url=http://127.0.0.1:9380 \
  --mode=self-host \
  --no-transport-sse-enabled
```

观察输出包含 `Streamable HTTP endpoint available at /mcp`。目标 URL：`http://127.0.0.1:9382/mcp`，不是 REST API 的 `:9380/api/v1/retrieval`。**不要把带真实 Key 的 `--api-key=...` 命令粘进 shell 历史**。若 MCP 在不同 VM/容器内，需先实测从 DSH 运行环境访问 `127.0.0.1:9382` 是否可达；在不可信网络不使用明文对外监听。

官方 MCP 在此 tag 注册：
- `ragflow_retrieval`：检索 chunks（必须 `question`，可选 `dataset_ids/document_ids`、分页、阈值、vector weight、keyword、rerank id）；
- `ragflow_list_datasets`：列出账号可访问 Dataset；
- `ragflow_list_chats`：列出 chat assistants。

**已核实的限制**：这个 MCP 版本**没有**把 `use_kg`、`metadata_condition`、`toc_enhance` 等 REST 高级参数全都暴露为 MCP 工具入参。且不传 `dataset_ids` 时会枚举该账号的**全部可访问** Dataset。首版依靠专用账号权限作真正边界，不能仅靠 Prompt 限制访问。

## 4. 配置 DSH 官方 MCP Client（不 fork 内核）

本目录已提供 [可复制的 Cordis overlay](./ragflow-mcp.cordis.yml)。

```yaml
- insert:
    - id: mcp-policy-ragflow
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: ragflow
        transport: streamable-http
        url: http://127.0.0.1:9382/mcp
        toolCallTimeoutMs: 120000
        failOnStartupError: false
```

**先 CLI 冒烟，再 Desktop**。将文件路径替换为本地实际路径：

```bash
# 在 dsh-intramate 源码目录；前提是此前已 pnpm install + build
pnpm dsh web --patch "/absolute/path/to/ragflow-mcp.cordis.yml"
```

正式配置 IntraMate Desktop 时，将此文件的单项 `insert` 合并到 **IntraMate 自己的** `$DSH_HOME/profiles/desktop/cordis.patch.yml`（或产品自身可维护的配置覆盖），**不要覆盖其他已有 patch，不要改官方 DeepSeek Desktop 的 DSH_HOME**。确认 IntraMate 与官方程序已做到应用 ID / 数据目录隔离后再使用这一方式。

连接成功后，DSH 工具名应为：
- `mcp__ragflow__ragflow_retrieval`
- `mcp__ragflow__ragflow_list_datasets`
- `mcp__ragflow__ragflow_list_chats`

测试话术：
```text
请先调用 RAGFlow 知识检索工具，查找“授信审批权限”的制度依据。
只根据检索返回的内容回答，给出制度名称与原文引用。
如果没有查到，不要以模型记忆补充，不要声称制度没有规定。
```

**通过准则**：DSH 会话真实出现 `mcp__ragflow__ragflow_retrieval` 的 `tool/call` 和 `tool/result`；检索到目标文档且模型基于结果引用，不是仅凭对话输出了“看起来正确”的答案。

## 5. 端到端验收 Checklist

| ID | 项目 | 验收依据 |
| --- | --- | --- |
| AT-01 | 独立服务 | RAGFlow Web、API 正常；Docker 容器数据重启后保留 |
| AT-02 | 制度导入 | 10–20 份制度完成解析；记录失败文件、chunk 及条号偏差 |
| AT-03 | Retrieval Testing | 至少 5 个已知问题能命中人工认定条款 |
| AT-04 | REST smoke | `/api/v1/retrieval` 返回真实来源、响应 `code=0` |
| AT-05 | MCP smoke | 官方 `/mcp` 可连接，发现 3 个工具，执行 retrieve 返回 JSON chunks |
| AT-06 | DSH tools | DSH 自动发现 `mcp__ragflow__*`；真实 Tool Call/Result 在 Session 可追踪 |
| AT-07 | 来源忠实 | DSH 回复附制度名称/条款；未返回条号时不得虚构 |
| AT-08 | 负例 | 无答案时明确没找到；空库/索引未就绪/连接故障均有可解释输出 |
| AT-09 | 隔离 | MCP 服务未对公网暴露，Key 不在源码/日志/共享配置；DSH Home 不混用 |
| AT-10 | 恢复 | 重启 RAGFlow、MCP、DSH 后工具恢复；原始文件/索引持久化 |

本轮只需 5–10 个金标题目和 10–20 份文件完成技术接通。之后扩大到数百份、120–200 道题时再做性能和可信性对照评测。**AT-05/06 是必须真实运行才能确认的，不能由源码存在直接判为 PASS**。

## 6. 升级路径和明确不做的事情

- **V0.1（零产品代码）**：官方 RAGFlow → 官方 MCP Server → DSH 原生 MCP Client，证明调用链与基本引用能力。
- **V0.2（仅按真实缺口增补）**：若确实需要 REST 原有但 MCP 不暴露的 `use_kg` / metadata / 版本过滤，优先建设**薄的 DSH 专属只读 Tool Adapter**；绝不修改 RAGFlow 源码，也不改 DSH Agent Loop。
- **V0.3（内网治理）**：绑定企业 IAM 和权限范围；不允许 v0.27.2 self-host 单 Key MCP 直接服务不同权限的正式用户。验证完整文档权限链后才推广。
- **V0.4（复杂分析）**：根据金标评测启用 RAGFlow 原有 Graph/PageIndex/Agentic 等功能；对“全部”类问题另外要求有全库枚举覆盖证明。

**本阶段不做**：第二套向量库/图引擎/Embedding 管道、第二层 RAG Agent、定制检索 UI、自研知识库后台、系统内核修改、未经评测的大规模制度关系抽取。

## 7. 待用户环境补齐的信息（不阻断开发文档）

- RAGFlow 是否已启动、模型提供方和 embedding 模型；
- 运行方式：同机 Windows/WSL2/Docker 或内网服务器；
- 首批制度数量、格式比例、是否含不同密级及历史版本；
- 是否仅开发者本人单用户验证（本方案默认），还是计划多人立刻使用；
- IntraMate 打包后的真实 DSH Home，以及现有 desktop Cordis patch 的合并规则。

这些属于环境信息；在没有访问用户机器和制度文件的情况下，本文件**不声称已经部署或跑过端到端测试**。
