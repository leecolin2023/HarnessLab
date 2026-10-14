# EXP-MS-001 · PaddleOCR 3.7 / PP-OCRv6 OCR 服务交付

## 实验问题

如何在一台 **Ubuntu 24.04、4 vCPU / 16 GiB RAM、CPU-only x86_64** 云服务器，将成熟 OCR 模型作为**有鉴权、可压测、可恢复**的内部服务交付？

采用截至 2026-10 核实的最新 [PaddleOCR v3.7.0](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0) 与 **PP-OCRv6_small**。不是 v6 默认的 medium；small 优先用于 CPU 资源有限的基线。使用 [Python 本地推理 API](https://www.paddleocr.ai/latest/en/quick_start.html)，**不**使用 `paddleocr api`（后者调用官方托管服务）。

首期只支持 PNG/JPEG/WEBP 单张图片、OCR 文本及坐标；不支持 PDF、复杂表格提取和业务字段核验。以后 VLM 做独立服务，不伪装成 OCR 或聊天 API。

## 在服务器部署

先安装官方 Docker Engine / Compose，确保 `uname -m` 返回 `x86_64`，不要对公网开放识别端口。

```bash
git clone https://github.com/leecolin2023/HarnessLab.git
cd HarnessLab/04-experiments/model-service/ocr-serving-ppocrv6
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
# 把输出密钥写入 .env 的 MODEL_API_KEY
chmod 600 .env
docker compose build
docker compose up -d
docker compose logs -f --tail=100
```

首次构建需联网安装 Paddle，首次启动会下载模型。`./models` 映射模型缓存；`docker compose restart` 应复用缓存。Docker 镜像固定 PaddleOCR 3.7.0 + PaddlePaddle CPU 3.3.0 **候选兼容版本**，目前尚未在目标服务器完成构建验证。

容器仅映射 `127.0.0.1:8008`；可经 VS Code Remote SSH 端口转发或 SSH 隧道访问。

## 基础验证

```bash
curl -sS http://127.0.0.1:8008/health/live
curl -sS http://127.0.0.1:8008/health/ready
# 先在宿主机安装 Pillow 后生成公开合成测试图片
sudo apt-get install -y python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install Pillow
.venv/bin/python tools/make_sample.py
set -a; . ./.env; set +a
curl -sS -H "Authorization: Bearer $MODEL_API_KEY" -F "file=@sample.png" http://127.0.0.1:8008/v1/ocr
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer wrong" -F "file=@sample.png" http://127.0.0.1:8008/v1/ocr
unset MODEL_API_KEY
```

正常请求应有识别文本、置信度、box、模型标识；错误 SK 为 401，非图片为 415，超过输入限制为 413。服务采用单实例**单次推理保护**，并发拥塞返回 429，不把 429 算成成功吞吐。

## 压测：固定样本、对比并发

```bash
set -a; . ./.env; set +a
python3 tools/bench.py --image sample.png --concurrency 1 --requests 20 --out results/c1
python3 tools/bench.py --image sample.png --concurrency 2 --requests 40 --out results/c2
python3 tools/bench.py --image sample.png --concurrency 4 --requests 80 --out results/c4
unset MODEL_API_KEY
docker stats --no-stream
```

记录 HTTP 200、401、429、5xx 分布，成功请求 P50/P95、成功 QPS、CPU/内存。负载脚本生成 CSV 与 JSON 放 `results/`，不得提交真实银行数据。

| 验收项 | 预期 | 状态 |
| --- | --- | --- |
| 容器运行、就绪检查 | 200，模型加载完成 | 待实测 |
| 正确 / 错误 SK | 200 / 401 | 待实测 |
| 非图片、超大图 | 415 / 413 | 待实测 |
| 并发负载 | 可记录 P50、P95、QPS、429 | 待实测 |
| 重启 | 恢复服务并复用模型缓存 | 待实测 |
| 模型版本切换 | tiny / small / medium 同条件比较 | 后续 |

后续轻量 VLM 试验先测常驻 RAM、推理时延、OOM 与部署复杂度；4 核 16 GiB 不能默认同时承载 OCR 与 VLM。

**当前状态：目录与部署脚手架准备中，运行与压测尚未验证。**
