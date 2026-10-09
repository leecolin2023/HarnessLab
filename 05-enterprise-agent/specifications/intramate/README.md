# IntraMate · 产品需求规格

此目录是 IntraMate 的**框架中立产品需求**归档位置。产品目标是企业内网 Agent，但当前 DSH 代码库不构成需求本身；未来可以在保留验收语义的前提下选择不同实现栈。

## 使用方法

1. 从 [SRS 模板](../srs-template.md)复制一份需求文档，建议命名 `SRS-001-<capability>.md`，并填写业务事实和待确认项。
2. 将需求登记到 [需求索引](../requirements-index.md)，状态由 `Draft` 开始。
3. 明确 `REQ` 与 `AC` 编号，评审后建立稳定需求基线。
4. 技术实现另见 [不同框架的 Implementation Profiles](../../implementation-profiles/)；对应版本应引用同一 SRS ID 和版本。
5. 产品仓库的 Issue、PR 与测试引用 SRS/REQ/AC ID，避免需求与实现脱节。

可考虑的研究方向包括桌面端隔离、Agent 任务持续性、Office 文件操作、银行 Skills、权限审计、离线部署等；它们**不是已经确认的规格清单**。

> 当前：等待第一份经澄清的 SRS 草稿。
