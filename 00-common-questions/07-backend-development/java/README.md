# 后端开发 · Java

## 初始候选题单

### JVM 与语言

- Java 内存模型（JMM）与 JVM 运行时内存区域分别是什么？
- JVM 垃圾回收如何工作？如何分析内存泄漏和 GC 停顿？
- equals / hashCode 为什么需要一致？HashMap 和 ConcurrentHashMap 各有什么特点？

### 并发

- synchronized、volatile、Lock 的区别是什么？各能保证哪些性质？
- Java 线程池如何设置参数？队列和拒绝策略有哪些风险？
- CompletableFuture 与普通线程池任务怎样组合？

### Spring 与数据库

- Spring IOC、依赖注入、AOP 和动态代理分别解决什么问题？
- @Transactional 在同类方法内部调用时为什么可能不生效？
- Spring Boot 自动配置是如何触发和覆盖的？
- MyBatis、JPA 的差异如何理解？如何排查慢 SQL 和连接池耗尽？

涉及分布式幂等、事务隔离等语言无关的问题，回链 [通用基础](../general/)。
