# 批次 2：工作台、资料与平台面板（2026-10-05）

- `features/workspace` 协调工作台状态、URL 与看板轮询，feed 承接列表请求与归档视图，articles 承接详情/标注和录入，topics 承接主题视图。app/page 继续提供兼容入口。
- platform、media、semantic 各按协调 hook、显示工具和业务视图拆分；三个 app 入口与 request/SemanticArticleActions 导出兼容。controller 在原挂载位置无条件调用，保留状态存活、请求键、5/10 秒轮询、草稿、expected、媒体 refs/Blob 清理。
- JSX、状态与副作用按原顺序提取；稳定 setter 补入 hook 依赖，不改筛选、请求、错误、URL push/replace 或模型/平台业务行为。

## 验证

- TypeScript、业务范围 `oxlint app lib features tests` 和 6 项 API 契约通过；完整 lint 仍为原有 19 项通用 UI/hook 错误。
- 临时副本的 `build:container` 与 Vinext `build` 通过；16 个面板文件格式和 13 项面板抽取等价检查通过，主工作台另经独立只读对照审查。
- `scripts/check_interactions.py` 完整 12 组交互通过，使用临时静态构建、全合成 API、新浏览器上下文：来源筛选/未知参数/hash/刷新；详情与历史导航；跨页选择/批量默认；新增；删除失败重试；媒体播放跳转/字幕下载/上传/Blob 回收；笔记与核验保存/刷新及资料导航；搜索 URL；主题直达；播客深链接/预览门槛/刷新/新搜索清理；显式空主题/超范围分页；语义轮询保留草稿与 expected。
- 页面异常 0、外网请求 0。来源批次另外固定其它页面为 1A 基线完成两种构建及 5 组交互，见 [批次 1B](01b-source-management.md)。
- 测试调试中修正了包含关闭按钮的通知定位器，并为原有 preload=none 的播放器显式加载合成音频；这两项是测试前提修正，没有改产品行为。

内置 Browser 的 Node runtime 无法启动，本批使用已安装 Playwright/Chromium 的独立无头上下文。检查不接触真实数据库、账号 profile、平台或模型，不能替代真实运行环境验收。准确命令见 [总验收](08-acceptance.md)。
