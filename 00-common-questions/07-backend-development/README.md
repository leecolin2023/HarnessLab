# 07 · 后端开发｜常见问题

**定位：** 补充 Agent 工程之外的通用后端面试知识体系，既服务 Python / Java 岗位，也支撑 Agent 产品的服务端工程能力。

## 三个子方向

| 目录 | 内容 | 边界 |
| --- | --- | --- |
| [general](./general/) | HTTP、网络、数据库、缓存、并发、分布式、系统设计、工程质量 | 语言无关的基础机制 |
| [python](./python/) | Python 运行时、并发、FastAPI、ASGI、数据校验、依赖管理 | Python 特有实现 |
| [java](./java/) | JVM、Java 并发、Spring、数据库访问、服务治理 | Java 特有实现 |

## 写题原则

通用题只在 `general/` 讨论机制，Python / Java 特有题放在语言目录。例如“什么是事务隔离”归 `general/`，“Spring 的 @Transactional 为什么失效”归 `java/`。

候选题在对应 README 中，后续按需拆成单题文档，统一采用 [问题模板](../QUESTION_TEMPLATE.md)。
