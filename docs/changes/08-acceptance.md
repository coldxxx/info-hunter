# 总验收与文档批次（2026-10-05）

基线 `317f3a3`，最后代码批次 `647be3c`；各结构提交见 [索引](README.md)。当前说明补齐 README、架构/数据流、来源/API/页面扩展、配置/备份恢复/故障及 AGENTS；旧根 README 归入 history，6 份原手册增加历史提示并保留原正文。配置示例无凭据且全部禁用。Git/Docker 另补连接配置备份与 .db WAL/SHM 的排除。

## 环境与完整结果

macOS Apple Silicon；核心 Python 3.9.6，原生实际迁移 Python 3.12.12；Node 24.21.0；既有项目依赖与 Chromium。依赖未升级、正式运行环境未重建。初始受限环境不能绑定 loopback，批准的隔离执行环境完成检查；内置 Browser Node runtime 无法启动，UI 改用独立 Playwright 无头上下文。

| 检查 | 实际结果 | 范围/限制 |
| --- | --- | --- |
| 核心 unittest / Python 3.9.6 | 185/185 通过 | 基线 181 + 4 纯工具边界测试；临时 data/backups/config/native |
| 核心 unittest / Python 3.12.12 | 185/185 通过 | 与 Docker Python 大版本一致，仍使用隔离路径 |
| native HTTP/资源 | 11/11 通过 | 临时目录、ASGI，不启动 lifespan/worker；DNS/桥接/任务替身 |
| 前端 API 契约 | 6/6 通过 | GET/POST、解析/错误顺序、Abort、multipart 等原契约 |
| TypeScript | 通过 | noEmit，关闭 incremental 写入 |
| 业务 lint | 通过 | app/lib/features/tests |
| 完整 npm lint | 19 项原有错误 | 与基线文件/规则集合相同；没有新增业务层错误或禁用规则 |
| 两种前端构建 | 全部通过 | 临时副本；静态容器和 Vinext/Cloudflare 分别检查 |
| 来源批次 UI | 5 组通过 | 其它页面固定 1A 基线，来源拆分独立验收 |
| 最终 UI | 12 组通过 | 合成 API、临时媒体、新上下文；页面异常 0、外网请求 0 |
| 独立对照审查 | 无阻塞回归 | 后端移动函数/13 路由及前端完整 JSX/effect/URL 等价；保留测试补丁点 |
| Compose 配置 | 通过 | `config --quiet`，未启动正式服务 |
| Docker 实际镜像 | 构建与隔离运行通过 | 独立标签；无网络/宿主机挂载/端口映射，模块、合成标注快照、status/static HTTP 与 /app 私有文件检查 |
| 私有内容指纹 | 78/78 一致 | 数据库、备份、关键配置；没有丢失或内容变更 |
| Git 候选/暂存审核 | 私有路径及常见强凭据特征均 0 命中 | 新排除模式也检查；原始指纹/日志留私有临时目录，不入 Git |

Vinext Unknown 静态分类提示与基线一致，构建退出为 0。完整 lint 的 19 项错误位于 breadcrumb、button-group、carousel、chart、field、input-group、input-otp、item、label、pagination、spinner、use-mobile；后续以独立批次修复。源码扫描是本次检查结果，不是对所有未知凭据的完备证明。

## 可重复命令

从仓库根执行后端及构建；前端命令在 ai-finance-radar 内执行：

```sh
python3 scripts/check_backend.py
python3 scripts/check_frontend.py
cd ai-finance-radar
node --test tests/*.test.mjs
npx tsc --noEmit --incremental false
npx oxlint app lib features tests
npm run lint
```

本次原生迁移环境的命令从仓库根执行：

```sh
IH_NATIVE_PYTHON=ai-finance-collector/native/.python/cpython-3.12.12-macos-aarch64-none/bin/python3.12
"$IH_NATIVE_PYTHON" -B scripts/check_backend.py
PYTHONPATH="$PWD/ai-finance-collector/native/.venv/lib/python3.12/site-packages" \
"$IH_NATIVE_PYTHON" -B scripts/check_native.py
PYTHONPATH="$PWD/ai-finance-collector/native/.venv/lib/python3.12/site-packages" \
PLAYWRIGHT_BROWSERS_PATH="$PWD/ai-finance-collector/data/native/browsers" \
"$IH_NATIVE_PYTHON" -B scripts/check_interactions.py
```

来源独立验收在最后一条后加 `--source-batch`，属于本次历史检查。正常原生环境重建后使用其 .venv 解释器，详见 [开发指南](../development.md)。Docker 构建命令：

```sh
docker compose config --quiet
docker build --progress plain -t info-hunter:refactor-validation .
```

镜像运行检查使用一次性 `docker run --rm -i --network none`，覆盖 RADAR_DATA_DIR/BACKUP_DIR/CONNECTIONS_FILE/NATIVE_DATA 到容器内临时目录，不启动正常 serve 调度。临时脚本导入新增模块、初始化合成库、写一条文章和收藏/笔记/核验、备份核对，再用临时 HTTP 线程检查静态页/status；无用户数据卷和公开端口。

## 剩余事项

- 全量 lint 的 19 个既有错误，真实账号/媒体/模型与长期增量、跨进程恢复、代表性语义评估和完整恢复演练仍另行安排；它们未纳入结构调整的完成声明。
- native/.venv 和 .python 的旧绝对符号链接失效；本次直接用已迁移实际解释器验证，没有重建依赖或安装固定标签 LaunchAgent。新路径运行实例切换见运维。
- 用户指出的低评论/低信息量 Reddit 条目属于业务质量样本问题，保持为独立行为验证批次，本次结构整理没有调整阈值或删除历史资料。
- 原有数据、历史归档、收藏、笔记及核验状态保留，未部署/切换现有实例、未推送 Git 远端。当前文档和历史记录已分开；测试成功不代表真实平台或生产环境已重新验收。
