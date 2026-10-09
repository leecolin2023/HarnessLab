# Agent Runtime

**定位：** 沿真实执行链追踪 Agent、Session、Tool、Model 之间的关系。

## 建议研究问题

- 一个用户消息如何驱动 turn/step 请求序列？
- 工具执行与 Session 事件怎样保持一致？
- 异常、取消、恢复后模型到底看到了什么？

## 预期产物

按 commit 固定的端到端源码追踪与重要边界用例。

## 主要参考

- [Agent Loop 源码目录](https://github.com/deepseek-ai/deepseek-harness/tree/main/packages/core/agent-loop)

> 状态：待研究。此文件只是内容入口，尚无已验证结论。
