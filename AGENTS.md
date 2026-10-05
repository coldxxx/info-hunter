# 代码修改约定

## 边界与兼容性
- 保留 React/Vinext/Vite/TypeScript 与 Python stdlib/FastAPI 技术栈；按真实职责与重复提取，不增加替代框架。
- 前端 `lib/api.ts` 管传输，`lib/api-types/` 管接口 DTO，`features/` 管业务组件与状态；`app/` 保留页面入口兼容性。共享文件由主代理整合。
- 后端根级 Python 模块仍被 Docker `COPY *.py` 部署；native 的工作目录、裸模块导入、脚本路径保持兼容。
- 结构重排和业务行为修改分批。接口、错误文案、URL 参数与 push/replace、刷新、前进后退、轮询间隔必须保持。
- 保留 `radar` 的公共调用与现有测试补丁点；不要在新模块缓存 DB/ROOT/fetch 等可替换全局值。保留 schema 初始化次序、锁和事务边界。

## 数据与 Git
- 禁止测试写真实 `data/`、`backups/`、浏览器 profiles、凭据或真实模型/平台连接。必须先设置隔离目录，再导入有初始化副作用的模块。
- 不清空、重建或迁移用户数据库；保留历史归档、收藏、笔记、核验和语义复核记录。
- `.gitignore` 与 `.dockerignore` 分别保护版本管理和镜像上下文；新增配置提供无密钥示例，不提交真实连接配置、登录状态、原始验收数据。
- 每批通过相关验证后独立提交，在 `docs/changes/` 记改动、结果、基线失败和剩余问题。禁止把既有 lint 失败归因于本次或通过禁用规则掩盖。
- 文档依据实际代码与运行结果。当前说明在根 README 与 docs，旧环境验收材料按 `docs/history/README.md` 标注。

## 验证命令
- 后端：`python3 scripts/check_backend.py`；可加现有 unittest 模块名限定范围。脚本创建临时数据与配置目录。
- 原生 HTTP：使用原生 Python 依赖环境执行 `python -B scripts/check_native.py`；不启动 lifespan worker，设置临时路径并限制真实 DNS/任务。迁移环境的解释器命令见 `docs/development.md`。
- 前端：在 `ai-finance-radar` 执行 `node --test tests/*.test.mjs`、`npx tsc --noEmit --incremental false`、`npx oxlint app lib features tests`。
- 全量 lint：`npm run lint`。基线为通用 UI/hook 的 19 个错误，业务层 lint 基线通过。
- 构建：根目录 `python3 scripts/check_frontend.py` 在临时副本运行 `build:container` 与 `build`；`docker build` 验证完整镜像。不得启动现有生产实例作验证。
- 关键交互：按 `docs/development.md` 配置 Python/Chromium 后运行 `scripts/check_interactions.py`，以隔离服务/假数据检查 URL 直达、刷新、后退/前进、详情、来源选择/删除/新增、主题、媒体和语义草稿。

## 并行协作
- 最多 3 个子代理，目标、文件范围、验收标准明确；不同代理不同时编辑同一文件。
- 公共接口、入口整合、Git、记录由主代理负责。依赖或冲突先报告，不覆盖他人改动。
