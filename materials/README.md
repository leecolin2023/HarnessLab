# 外部资料加工归档（materials）

这里保存来自 [ingest2md](https://github.com/leecolin2023/ingest2md) 等来源的二次加工材料，与仓库根目录下的**正式专题研究文章**分开管理。原始采集与转写底稿仍保存在 [ingest2md/output](https://github.com/leecolin2023/ingest2md/tree/main/output)。

## 按主题浏览

| 目录 | 内容 | 累计归档文件 |
| --- | --- | ---: |
| [model-platform](./model-platform/) | LLM 原理、推理引擎、模型性能与微调 | 34 |
| [rag](./rag/) | 检索、BM25、向量、Reranker、知识构建与相关评测 | 34 |
| [agent-runtime](./agent-runtime/) | Agent、LangChain、MCP、Skills、意图识别 | 29 |
| [enterprise-ai](./enterprise-ai/) | AI 客服、销售、数据与业务系统的场景应用 | 34 |
| [ai-career](./ai-career/) | AI 岗位面试、项目表达、简历及招聘市场案例 | 47 |
| [_migration](./_migration/) | 历史 README、处理索引、完整迁移映射清单 | 2 + 清单 |

## 材料规则

- 每个来源以原始素材标题建立目录；根据实际已完成的处理过程保存 `refinement.md`、`deep-read.md` 和/或 `learning.md`。
- 这些稿件属于**加工资料与学习素材**，不是全部经过独立事实审查或严格 Skill 执行验收的正式研究成果；原稿和当前处理限制应一起参考。
- 一篇材料如果值得沉淀为正式知识文章，应重新组织到根目录的 `rag/`、`model-platform/` 或其他研究专题中，而非直接当作研究结论。
- 非 AI 资料另存于 [knowledge-archive](https://github.com/leecolin2023/knowledge-archive) 的 `business/`、`life/`、`inbox/`。
- [MIGRATION_MANIFEST.json](./_migration/MIGRATION_MANIFEST.json) 记录了每个旧文件与新文件的精确映射及 SHA-256，适用于追溯和验证。
