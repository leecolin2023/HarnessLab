# Specifications · 框架无关的产品需求

本目录存放面向企业 Agent 产品的**需求规格说明书（Software Requirements Specifications，SRS）**。SRS 描述“什么是正确结果”，而不是“用 DeepSeek Harness 或 LangGraph 怎样编码”。

## 目录

- [requirements-index.md](./requirements-index.md)：维护需求文档 / 版本 / 状态 / 验收追踪的单一入口。
- [srs-template.md](./srs-template.md)：编写单份 SRS 的通用模板。
- [intramate/](./intramate/)：IntraMate 的产品级规格文档；以后有其他产品可建立并列目录。

## 每份 SRS 应覆盖

1. 背景与用户问题、目标与非目标、范围和用户角色。
2. 典型场景、输入输出、数据和流程边界、失败和异常行为。
3. 带**稳定 ID**的功能需求、非功能约束（如脱网、权限、可靠性、性能、可维护性）。
4. 可观察、可测量的验收条件与反例，不以“模型能够回答”冒充执行成功。
5. 依赖、未知项、风险、变更历史及证据来源。

## 约定

- SRS 文档 ID：`SRS-001`；单条需求：`REQ-0001`；验收项：`AC-0001`。均应在产品范围内保持稳定，重排目录不改变 ID。
- 状态建议：`Draft → Review → Approved → Superseded`；不得将草稿视为获批。
- 用明确要求与验收值取代模糊形容词；未知阈值保留 `TBD`，不填虚构数字。
- 不直接写 `Cordis`、`LangGraph node` 或某个具体仓库的文件路径作为**用户需求**；这些属于 [implementation-profiles](../implementation-profiles/)。
- 如确实存在外部规定必须使用某种技术，将它明确标注为“外部强制设计约束”并记录依据，避免混同业务功能。
- 产品基线发生实质变化时更新 SRS 并留下历史；单纯更换技术栈通常只更新实现方案。

> 当前仅创建说明及模板，没有预先替用户确立具体功能要求。
