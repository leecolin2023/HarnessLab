# IntraMate Integration — 学习成果如何进入产品

## 用途

明确 HarnessLab 的研究、[框架无关的 SRS](../05-enterprise-agent/specifications/)和[实现方案](../05-enterprise-agent/implementation-profiles/)如何转化为产品工程任务。此处记录**接入边界与追踪**，不在研究仓库维护产品源码。

当前产品代码仓库：[dsh-intramate](https://github.com/leecolin2023/dsh-intramate)。未来如有其他框架实现，可替换或新增产品仓库，**不要求重新编号业务需求**。

## 集成记录模板

| 项目 | 待填写 |
| --- | --- |
| 集成编号 / 状态 | TBD / 提议 |
| 场景和目标 | TBD |
| SRS ID / 版本 / REQ / AC | TBD |
| 对应框架实现方案 / 版本 | TBD |
| 对应研究或实验 | TBD（路径、commit、结果） |
| 上游原生能力与缺口 | 待验证 |
| 接入方式 | 配置 / 插件 / 外部服务 / 必要 Fork 改动 |
| 是否触及上游核心 | 待判定，优先避免 |
| 数据 / 权限 / 离线约束 | TBD |
| 产品实现链接（Issue/PR） | 尚无 |
| 验收与回归证据 | 尚无 |
| 升级兼容 / 回滚策略 | TBD |

## 边界

1. **HarnessLab / Specifications**：描述需要满足的产品行为及验收条件。
2. **HarnessLab / Implementation Profiles**：按技术路线设计实现路径、覆盖和差距。
3. **HarnessLab / Engineering Decisions**：记录选型、复用与自建的依据。
4. **产品仓库**：负责实现、构建、测试和交付；提交记录回链到同一需求 ID。
5. 原则：Upstream-first，优先原生能力与薄适配，不为学习目的复制成熟实现。
6. 不得将“拟实现”“已设计”标成“已验收”。当产品需求变化时，先修订 SRS，再检查所有框架映射。

> 状态：集成跟踪模板就绪，尚无已完成的集成记录。
