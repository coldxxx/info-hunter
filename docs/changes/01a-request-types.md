# 批次 1A：请求层与接口类型（2026-10-05）

## 改动

- 新增 `lib/api.ts` 单一 fetch 传输实现，page/platform/semantic/upload 保留各自既有错误解析顺序、普通 Error 文案、API 前缀、GET/POST 和 FormData 约定。
- 前端 feed、平台、语义、媒体和来源 DTO 迁入 `lib/api-types/`，不合并语义资料投影与信息流资料投影。来源兼容入口留给 1B 接续迁移。
- 首页文章详情也使用统一请求层，保留 Abort、HTTP 文案与不存在资料的判断。媒体上传不设置 JSON Content-Type。
- 添加 AGENTS 代码边界、隔离后端验证与临时前端构建脚本；6 个 API 契约测试覆盖真实行为差异，沿用 Node 内建测试，无新增依赖。

## 验证与剩余

- `tsc --noEmit --incremental false`、`oxlint app lib tests`、6 项 API 契约检查通过。
- `python3 scripts/check_frontend.py`：静态容器构建与 Vinext 构建均通过，输出仅写临时副本。
- 全量 lint 的 19 项基线错误仍单独跟踪。URL 实现未修改；交互在来源与页面拆分后使用隔离数据统一核验。
- 无 API/URL 或业务规则修改，无真实数据写入。
