# 历史资料索引

原有手册保持原位置，记录当时的实现、旧路径、特定容器和样本。有些正文包含不同阶段的能力差异。当前操作优先看 [开发](../development.md)、[运维](../operations.md) 和 [架构](../architecture.md)。

| 原件 | 阅读边界 |
| --- | --- |
| [旧根 README](root-readme-before-refactor.md) | 整理前的产品与逐次验收记录，不再是当前启动入口 |
| [采集器 README](../../ai-finance-collector/README.md) | 原型与后续更新；旧测试数、绝对路径不能作为当前步骤 |
| [网站采集与转写](../../ai-finance-collector/COLLECTION-SETUP.md) | 原生、登录、媒体、HTTP/MCP、公众号历史接入；未验收场景保持未完成 |
| [来源架构专题](../../ai-finance-collector/SOURCE-ARCHITECTURE.md) | 共享来源、主题、删除、详情与 URL 状态设计 |
| [社交接入](../../ai-finance-collector/SOCIAL-CONNECTIONS.md) | 早期 API、人工浏览器与后续路线，按日期区分 |
| [本地语义去重](../../ai-finance-collector/SEMANTIC-DEDUP.md) | 人工复核、联调样本与自动资格；不是生产准确率证明 |
| [来源失败诊断](../../ai-finance-collector/SOURCE-FAILURES-2026-10-05.md) | 原运行环境的逐项故障与恢复，不是新路径部署验收 |
| [设计原件](../../ai-finance-radar/DESIGN.md) | 保留用户设计依据用于实现核对 |
| [项目采集 skill](../../ai-finance-collector/skill/SKILL.md) | 早期研究/核验流程，旧路径与接入描述不代表已安装或定时运行 |

## Git 基线

保留 `a1a2b6f` 的 LICENSE 初始提交。2026-10-05 新增 `317f3a3`（`first-commit`），标签 `baseline/first-commit`，作为已有源码基线；没有改写初始历史或推送远端。

基线记录为 181 项后端、TypeScript 和两种前端构建通过，全量 lint 有 19 项既有错误。准确命令及整理后的结果见 [变更记录](../changes/)；入 Git 不代表新目录实例或真实平台重新验收。

整理后的验证与基线分开：当前已记录核心 185 项、native HTTP 11 项和前端 API 契约 6 项通过。最终构建/交互数量与环境仍以变更记录为准；这些检查不切换运行实例，也不重新验证真实账号。

## 历史与当前说明

历史保留原日期、样本和失败/限制，追加解释而不把旧数字改为当前数字。未来历史摘要去除本地账号标识、凭据、正文和会话；原始截图、DOM、JSON、数据库及代码快照留在被忽略目录。

当前指南负责可重复步骤，变更记录负责具体改动与本次验证，历史负责原环境证据；互相链接，不维护多套当前启动说明。
