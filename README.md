# Info Hunter · 信息雷达

本地研究资料库：按自定义主题关注公开订阅、作者、频道与板块，保存来源、标题、摘要、可用正文和媒体文字稿。信息流支持搜索、同文分组、收藏、笔记和独立核验；开发者主题按具体技术线索筛选。可选本地模型提供日语/韩语翻译和可撤销的语义关系复核。

采集能力取决于来源与已有授权。浏览器登录、公众号桥接、转写及模型服务按需配置；页面上的模型判断不替代人工核验。用户数据留本机，源码与私有配置分开管理。

## 项目组成与依赖

| 部分 | 技术与要求 |
| --- | --- |
| `ai-finance-radar/` | React 19、Vinext、Vite 8、TypeScript、Tailwind/shadcn；Node >=22.13.0、npm |
| `ai-finance-collector/` | Python 3.9+ 标准库、SQLite、HTTP；Docker 运行时 Python 3.12 |
| 可选 `ai-finance-collector/native/` | Apple Silicon macOS、Python 3.12、FastAPI、Playwright、FFmpeg、MLX Whisper；锁定依赖见 requirements.lock |
| 可选模型 / 公众号 | LM Studio 本地服务 / 独立 We-MP-RSS Compose |

前端领域组件与状态位于 `features/`，`app/` 保留兼容入口。后端保留 `radar.py` CLI 与公共调用，通过存储、API、采集与语义工作模块协作。完整数据流见 [架构](docs/architecture.md)。

## 开发启动

在仓库根目录启动隔离 API，避免开发过程使用正式数据库：

```sh
IH_DEV_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/info-hunter-dev.XXXXXX")"
RADAR_DATA_DIR="$IH_DEV_ROOT/data" \
RADAR_BACKUP_DIR="$IH_DEV_ROOT/backups" \
RADAR_CONNECTIONS_FILE="$IH_DEV_ROOT/connections.local.json" \
RADAR_NATIVE_DATA="$IH_DEV_ROOT/native" \
python3 -B ai-finance-collector/radar.py serve
```

另一个终端启动页面：

```sh
cd ai-finance-radar
npm ci
npm run dev
```

访问 `http://127.0.0.1:43187`；Vite 将 `/api` 代理到 `127.0.0.1:43188`。启动 API 会初始化所选目录并运行后台调度。正式数据位置、端口、模型与授权配置见 [运维说明](docs/operations.md)。

迁移来的 native 虚拟环境仍有指向旧目录的绝对链接，需从采集器目录通过 `sh native/bootstrap.sh` 在新路径重建，才可使用 `sh native/start.sh`。安装 LaunchAgent 会切换固定标签的服务，按运维步骤单独安排；此次代码整理未切换实例。

## 构建与 Docker

```sh
cd ai-finance-radar
npm run build:container
npm run build
```

静态容器构建生成 `container-dist/`，由 Python 提供页面及同源 API；普通构建保留 Vinext/Cloudflare 链路。`npm run start` 对应 Wrangler 本地运行，开发 API 代理定义在 Vite 配置中；两种构建分别验证。

完整 Docker 启动在仓库根目录执行：

```sh
docker compose up -d --build
docker compose ps
```

Compose 仅绑定本机端口，默认 43187，挂载采集器 `data/` 与 `backups/`。启动会使用并写入这些目录。`compose.override.yaml` 为 Fake-IP DNS 环境启用兼容；不需要时用 `docker compose -f compose.yaml up -d --build`。停止用 `docker compose stop`。

`.gitignore` 与 `.dockerignore` 分别排除数据库、备份、账号配置、登录状态、许可文件、原始验收资料、依赖和生成产物。官方 API 的无凭据形状可参考 [配置示例](ai-finance-collector/connections.example.json)，实际配置通过 `social.py configure` 保存到被忽略文件；主 Python 不自动读取 `.env`。

## 验证与贡献

仓库根目录：

```sh
python3 scripts/check_backend.py
python3 scripts/check_frontend.py
```

前端目录：

```sh
node --test tests/*.test.mjs
npx tsc --noEmit --incremental false
npx oxlint app lib features tests
npm run lint
```

后端检查先设置临时数据目录；构建脚本只在临时副本产生输出。原生 HTTP 检查用原生 Python 依赖环境运行 `scripts/check_native.py`；合成 API 的无头交互用 `scripts/check_interactions.py`，需已安装 Playwright 与 Chromium。完整命令与边界见 [开发指南](docs/development.md)。

结构整理前基线为 181 项后端、类型和两种构建通过；全量 lint 有 19 项既有 UI/hook 错误。每批的准确结果、回退点与剩余问题见 [变更记录](docs/changes/README.md)。增加来源适配器、接口或页面功能前请读 [AGENTS.md](AGENTS.md)；行为修改和结构重排分批提交。

## 当前说明与历史

- [架构与数据流](docs/architecture.md)
- [开发指南](docs/development.md)
- [配置、备份恢复与常见故障](docs/operations.md)
- [模块审计与优先级](docs/audit.md)
- [历史验收资料索引](docs/history/README.md)

旧手册保留原有记录和日期，作为当时环境的证据；当前操作以本 README 与 docs 指南为准。数据库、历史归档、收藏、笔记和核验状态不随源码整理重建。
