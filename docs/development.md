# 开发指南

路径均相对仓库根目录。开发与测试使用隔离数据，不切换现有正式实例。架构见 [architecture](architecture.md)，配置与恢复见 [operations](operations.md)。

## 依赖

核心采集器声明 Python 3.9+、标准库，文件锁使用 fcntl，当前运行目标为 macOS/Linux；Docker 使用 Python 3.12。原生 FastAPI/Playwright/MLX 路径使用独立 Python 3.12 与 `native/requirements.lock`，不能以核心的标准库说明代替原生依赖安装。

前端要求 Node >=22.13.0，Docker 构建使用 Node 24。安装依赖：

```sh
cd ai-finance-radar
npm ci
```

原生服务只支持 Apple Silicon macOS。准备 `uv` 和本地 Whisper 模型后，从采集器目录执行 `sh native/bootstrap.sh`，会安装 Python、同步锁定依赖、安装项目 Chromium 并检查模型。这是安装操作。声明在 `requirements.in`，版本在 `requirements.lock`；更新时记录锁文件生成方式和目标平台。

## 独立开发

先确认默认端口空闲，将下列路径替换为独立测试目录。不要指向正式 data/backups。

终端一，从仓库根启动 API：

```sh
IH_DEV_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/info-hunter-dev.XXXXXX")"
RADAR_DATA_DIR="$IH_DEV_ROOT/data" \
RADAR_BACKUP_DIR="$IH_DEV_ROOT/backups" \
RADAR_CONNECTIONS_FILE="$IH_DEV_ROOT/connections.local.json" \
RADAR_NATIVE_DATA="$IH_DEV_ROOT/native" \
python3 -B ai-finance-collector/radar.py serve
```

终端二：

```sh
cd ai-finance-radar
npm run dev
```

页面为 `127.0.0.1:43187`，后端为 `127.0.0.1:43188`；Vite 固定端口并代理 `/api`。改变端口需同步代理与 Origin 规则。启动后端会运行后台检查、翻译恢复和语义线程，不是静态预览。既有 `启动观察室.command` 使用默认数据目录，关闭窗口会结束其后端。

## 验证

优先从仓库根使用隔离脚本，避免导入初始化副作用接触正式状态：

```sh
python3 scripts/check_backend.py
python3 scripts/check_backend.py test_fetch test_collection
```

该脚本先设置临时 data、backups、连接配置和 native 路径，再运行 unittest。核心完整回归与原生服务依赖检查分别执行。测试使用数据库副本和模拟平台；HTTP 测试会短暂启动本机测试服务，不替换正式实例。脚本仍继承宿主环境，真实授权环境和网络行为不能仅靠路径隔离来验证。

原生 HTTP 检查由根 `scripts/check_native.py` 运行。重建原生环境后使用其解释器：

```sh
ai-finance-collector/native/.venv/bin/python -B scripts/check_native.py
```

本次迁移验收没有修复旧虚拟环境链接，而是使用已迁移的实际 Python 3.12.12 和既有 site-packages：

```sh
IH_NATIVE_PYTHON=ai-finance-collector/native/.python/cpython-3.12.12-macos-aarch64-none/bin/python3.12
PYTHONPATH="$PWD/ai-finance-collector/native/.venv/lib/python3.12/site-packages" "$IH_NATIVE_PYTHON" -B scripts/check_native.py
```

原生测试在导入 service 前设置临时目录，ASGI 请求不启动 lifespan worker，并以替身限制 DNS/桥接/任务提交，不访问真实平台或模型。默认核心 discover 不包含这些 native 检查。

前端在其目录执行：

```sh
node --test tests/*.test.mjs
npx tsc --noEmit --incremental false
npx oxlint app lib features tests
npm run build:container
npm run build
```

业务 lint 与全项目 `npm run lint` 分开记录；基线全量 lint 有 19 项既有错误，不能写成全量通过。格式化会改文件。构建产物是生成资料，不进入 Git。根 `python3 scripts/check_frontend.py` 在临时副本中执行两种构建，复用已安装依赖，适合避免覆盖工作目录产物；直接 npm 构建会重写对应输出。

隔离浏览器交互同样从根目录运行；使用已准备的原生 Python/Playwright 与项目 Chromium。脚本只读浏览器可执行文件，创建新上下文，构建和媒体 fixture 在临时目录，全部 API 合成并阻止外网请求：

```sh
PYTHONPATH="$PWD/ai-finance-collector/native/.venv/lib/python3.12/site-packages" \
PLAYWRIGHT_BROWSERS_PATH="$PWD/ai-finance-collector/data/native/browsers" \
"$IH_NATIVE_PYTHON" -B scripts/check_interactions.py
```

正常重建环境后可用 `.venv/bin/python` 替代 `IH_NATIVE_PYTHON`，保留浏览器缓存变量。`--source-batch` 专用于本次历史验收：其它页面固定在 `3e21457`，验证来源模块；未来完整回归不使用该参数。

`build:container` 生成 `container-dist/`，普通 `build` 使用 Vinext/Cloudflare，两者分别验收；保留普通配置导入的 `.openai/hosting.json`。根 `docker compose build` 仅构建，`up` 会启动服务、初始化数据并调度，不能混记。

`verify_semantic.py` 使用临时库，但调用真实本地模型并写 `verification/`，不是离线测试。`start_semantic_models.py` 会检查/启动服务或加载模型，应单独记录。根据改动验证候选/失败、授权/限流、迁移/标注、筛选/分组/分页、媒体取消恢复、语义引用防护与撤销；通过后仅在新增风险或失败时扩大复测。

## 扩展来源

1. 先复用 `capture.ADAPTERS`。RSS、论坛、博客或频道只提供参数，避免按来源复制读取器。`sources.json` 为种子注册表，页面新增来源在 SQLite 中持久保存。
2. 新平台在 `interests.identify/discover/register` 维护作者、频道或板块身份，并保留原提交链接。复用公开 URL、DNS 与重定向校验。
3. 新策略登记名称、说明、参数和函数，返回 `(rows, status, error)`。候选至少有 `url/title`，其他共用字段包括摘要、日期、发布方、正文与媒体。
4. 授权和 adapter 选择遵循 `social.effective_adapter` 与连接绑定。来源添加不自动启用付费或代表取得审批。
5. 统一进入 `collect_source → put` 的主题、质量、URL 去重、正文、主题归属、同文与语义流程。
6. 同步 `source_details.py` 的真实步骤/限制；测试成功、空结果、失败、限流、重复、标注保留。真实平台验收另外记录。

浏览器新平台还需维护 `native/browser_worker.py` 的身份、确认登录、DOM 解析及预算。测试使用合成响应，不读取或提交用户 profile。

## 扩展 API

主 Handler 顺序委派 `semantic_api.get/post` → `collection_api.get/post` → `source_api.get/post` / `article_api.get/post`，剩余路由保留核心 Handler。`api_contracts.py` 的 Collection/Source/ArticleServices 显式传入当前函数，代替整模块服务参数。新增接口放在对应领域，沿用 JSON 错误、Host/Origin、大小限制与事务边界；兼容 `radar` 公共调用和测试补丁点。`database`、`archive_store`、`collection_runner` 由兼容入口传入当前连接、路径、锁和调用函数；`semantic_worker` 也使用当前领域依赖，不能在新模块缓存可替换全局值。

读取入口包括 `/api/watch-topics`、`/api/status`、`/api/sources`、`/api/source-detail`、`/api/articles`；写入口包括 `/api/watch-topic`、`/api/watch-source`、`/api/source`、`/api/source-delete`、`/api/source-feedback`、`/api/article`、`/api/import`、`/api/collect`、`/api/backup`。媒体上传为 `/api/media-upload` 的 multipart 流式处理，不使用普通 JSON 限制。

HTTP 方法不等于无副作用：GET `/api/content` 会查询原生任务并同步正文/状态；播客发现 GET 会请求外部服务。新增接口要明确这些边界。本机 API 没有完整远程身份认证，不直接公开部署。

## 扩展页面

`app/` 保留页面入口兼容性，领域 UI/状态放业务组件；页面与容器入口复用同一实现。`features/workspace` 协调工作台，`feed` 负责轮询和列表，`articles` 负责详情/录入，`topics` 负责主题视图，`sources` 管理来源状态与分离视图；`platform`、`media`、`semantic` 分别拆分协调 hook、显示工具和业务视图。`lib/api.ts` 管传输，`lib/api-types/` 管 DTO；更新响应时同步领域类型和失败展示，保留各请求 profile 原有错误行为及 multipart 语义。

使用 `lib/url-state.ts` 维护视图、主题、筛选、分页和详情，保留 push/replace、刷新、前进/后退及轮询间隔。来源、平台、媒体和语义交互分别由其组件负责；机器翻译和模型关系不呈现为事实核验。

依据 `DESIGN.md` 与 CSS 变量，检查宽/窄屏、键盘关闭、加载、请求失败及 URL 直达。交互验收使用隔离服务和假数据，不能为了测试启动正式平台访问或改现有资料库。
