# 运维、配置与恢复

本文说明源码的操作方式，不宣称新路径已替换现有实例。安装、启动、授权、收录、迁移和恢复会改变状态，正式切换单独安排。旧实测见 [历史索引](history/README.md)。

## 服务与启动

| 服务 | 默认入口 | 状态位置 |
| --- | --- | --- |
| 开发网页 / Python API | `127.0.0.1:43187` / `127.0.0.1:43188` | 采集器 data/backups 或显式目录 |
| Docker 信息雷达 | `127.0.0.1:${RADAR_PORT:-43187}` | Compose 挂载采集器 data/backups |
| macOS 原生执行器 | `127.0.0.1:43202` | data/native 或 `RADAR_NATIVE_DATA` |
| 公众号桥接 | `127.0.0.1:43203` | data/wechat |
| LM Studio | 默认 1234 | 用户管理的本地模型目录 |

Compose 服务名为 `observatory`，容器名取决于项目名；优先使用服务名，不复制旧容器名。Docker Desktop 就绪且端口空闲后，在根目录执行：

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f observatory
```

停止用 `docker compose stop`，不删除数据。自定义端口用 `RADAR_PORT=43190 docker compose up -d --build`，后续保持同样配置。健康检查只验证 `/api/status`，不证明平台或模型连通。

`compose.override.yaml` 启用 Fake-IP DNS 兼容。无此网络环境时显式使用 `docker compose -f compose.yaml up -d --build`，后续继续使用同一文件集合；本机/内网 URL 仍不能作为公开来源。

## 配置与优先级

| 配置 | 用途/默认 |
| --- | --- |
| `RADAR_DATA_DIR` | 主数据库目录；宿主机默认采集器 data，Docker `/data` |
| `RADAR_BACKUP_DIR` | 快照目录；宿主机默认采集器 backups，Docker `/backups` |
| `RADAR_CONNECTIONS_FILE` | 私有官方 API JSON；宿主机默认 connections.local.json，Docker `/data/connections.local.json` |
| `RADAR_STATIC_DIR` | 静态产物目录；默认不提供网页，镜像 `/app/static` |
| `RADAR_BIND_HOST`、`RADAR_PORT` | Python 默认 loopback:43188，镜像 0.0.0.0:43187 |
| `RADAR_PUBLIC_PORT` | 网页 Origin 检查用宿主机端口；Compose 与映射同步 |
| `RADAR_TRANSLATION_URL`、`RADAR_TRANSLATION_MODEL` | 本地翻译接口/标识；没有模型标识不启用 |
| `RADAR_FAKE_DNS` | 1 启用指定 Fake-IP 域名解析兼容，不放行内网 IP 字面量 |
| `RADAR_NATIVE_URL` | 原生 RPC；默认 loopback，Docker 为 host.docker.internal:43202 |
| `RADAR_NATIVE_DATA` | 原生任务库、令牌、会话与媒体目录 |
| `RADAR_WHISPER_MODEL_DIR` | 覆盖 LM Studio 默认 Whisper 文件目录 |
| `RADAR_LMS_BIN` | 语义模型启动脚本使用的 lms 可执行文件 |

主 Python 不自动加载 `.env`。官方设置先读私有 JSON，再用对应凭据环境变量覆盖字段；凭据不替代明确启用或审批。初始化重新加载 `sources.json` 种子配置，用户新增来源、主题和绑定在数据库。

原生 `start.sh` 先设默认目录，再 source `native/env.local`；这是会执行的私有 shell 设置。Compose 插值、容器环境、宿主进程环境各自核对，不能假设宿主变量自动传入容器。

语义设置在数据库，空地址自动使用本机 LM Studio；默认标识 `radar-semantic-embedding`、`radar-semantic-judge`，人工复核且自动折叠关闭。`start_semantic_models.py` 可能启动服务/加载已下载模型。Whisper 直接读取文件，无需 LM Studio API 持续运行。

## 私有状态与授权

data、backups、连接 JSON、native/env.local、日志、截图、媒体与会话留本机；Git 和 Docker 排除分别验收。`.openai/hosting.json` 为必要构建配置，不能按目录名称一并移除。

原生 token 以 0600 创建，原生根目录以 0700 管理。`native_client` 读取 token，MCP 配置不需要复制令牌。普通数据库快照不包括 API JSON、native 任务库/会话或公众号授权，这些状态独立受保护地保留。

官方设置在采集器目录执行 `python3 social.py configure reddit` 或 `configure x`；Docker 使用 `docker compose exec observatory python social.py configure reddit`。这是配置写入，隐藏输入保存，不是状态检查。X 付费需明确启用；Reddit 需审批/授权/开关。

浏览器由本人打开专用登录窗口、完成验证，关闭窗口后确认。验证码、限流、登录失效和结构异常按真实状态暂停或冷却。实现 adapter 不代表平台已验收。

公众号用 `sh ai-finance-collector/native/wechat-start.sh` 初始化私有 service.env 并启动独立 Compose。管理登录、修改默认管理密码、扫码由本人完成。主雷达只读桥接缓存；上游更新、暂停和授权恢复在桥接管理界面处理。

## 原生安装与恢复

迁移过来的 `native/.venv/bin/python` 含指向旧 checkout 的绝对符号链接，当前目标不存在；直接 `native/start.sh` 不能据此运行。虚拟环境属于可重建的本机状态，不应把复制成功当作运行环境可用。操作者需要按 [开发指南](development.md) 的 bootstrap 步骤在新路径重建依赖、核对 Chromium 与 Whisper，再选择是否安装服务；本次整理没有重建或切换现有原生实例。

环境就绪后安装命令为：

```sh
cd ai-finance-collector
native/.venv/bin/python native/install-launch-agent.py
```

安装器写当前用户 LaunchAgents，并卸载/重新安装固定标签 `com.herman.signal-radar.native`，程序路径来自当前 checkout。在新路径执行会切换现有服务，仓库整理不自动执行它。

```sh
launchctl print "gui/$(id -u)/com.herman.signal-radar.native"
launchctl kill SIGTERM "gui/$(id -u)/com.herman.signal-radar.native"
```

原生日志在 data/native/service.log。进程退出由 LaunchAgent 恢复，未完成任务重排队；睡眠不保证运行。媒体清理只处理过期终态缓存并保留文字结果；使用页面清理入口，不直接删除仍被任务引用的目录。

## 一致性备份

正式 Docker 运行时用页面备份或容器内命令：

```sh
docker compose exec observatory python radar.py backup
```

应用使用 SQLite backup API，随后移除 Reddit 提供方记录并压缩快照，个人笔记/收藏/核验标注保存在独立表。因此快照文章数不必等于正式库总数。备份为同机快照，需独立异地保留；不覆盖私有连接、native 或公众号状态。

所有 radar CLI，包括 status/semantic-status，都先初始化并清理旧快照。正式 Docker 使用库期间不从宿主机另开同库写连接；诊断/备份走页面或容器。GET `/api/content` 也可能同步任务并写库。

## 隔离恢复验收

选取已完成的一致性快照。以下只建立临时恢复目录，不启动服务、不采集、不切换正式实例；替换快照路径后从仓库根执行：

```sh
IH_SNAPSHOT=/absolute/path/to/completed-snapshot.sqlite3
IH_RECOVERY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/info-hunter-recovery.XXXXXX")"
python3 -B - "$IH_SNAPSHOT" "$IH_RECOVERY_ROOT" <<'PY'
from pathlib import Path
import shutil
import sqlite3
import sys
source = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
(root / 'data').mkdir()
(root / 'backups').mkdir()
target = root / 'data' / 'radar.sqlite3'
shutil.copy2(source, target)
with sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as connection:
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('快照完整性检查未通过')
    for table in ('articles', 'saved_annotations'):
        exists = connection.execute(
            'SELECT 1 FROM sqlite_master WHERE type=? AND name=?',
            ('table', table),
        ).fetchone()
        if exists:
            count = connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            print(table, count)
print('isolated snapshot integrity: ok')
PY
RADAR_DATA_DIR="$IH_RECOVERY_ROOT/data" \
RADAR_BACKUP_DIR="$IH_RECOVERY_ROOT/backups" \
python3 -B ai-finance-collector/radar.py init
RADAR_DATA_DIR="$IH_RECOVERY_ROOT/data" \
RADAR_BACKUP_DIR="$IH_RECOVERY_ROOT/backups" \
python3 -B ai-finance-collector/radar.py backup
```

先在副本上用 mode=ro 检查；后两条会迁移/初始化副本并产生隔离快照。继续只读核对文章身份/原文、笔记、收藏、核验、主题/来源绑定和保留策略；解释旧 schema 新增表/索引及 Reddit 规则差异，不只看总数。

未来正式恢复先停止所有访问该库的写入，保留现有数据目录作回退，再用已验收快照建立新目录；不带旧 WAL/SHM。核对私有连接、原生状态和绑定后再安排重启。本次迁移未执行正式恢复或实例切换。

## 常见故障

| 现象 | 核对与处理 |
| --- | --- |
| 43187/43188 已占用，Vite 严格端口失败 | 确认占用实例；新实例选择空闲端口，开发代理与 Origin 同步，不停止未知服务 |
| native/start.sh 找不到解释器 | 旧 .venv 绝对链接失效；按 bootstrap 在新路径重建，确认实际解释器/依赖后才安排 LaunchAgent 切换 |
| native 返回 401 或 403 | 核对后端与执行器使用同一数据目录/token、正确 RPC 地址；不打印令牌。带 Origin 的浏览器直连被拒绝，使用主后端 |
| 翻译/语义模型未就绪 | 检查本地端口、模型已加载、标识与设置一致；Whisper 则检查本地文件目录，两者分别恢复 |
| RSS DNS/TLS/公开 URL 失败 | 核对代理、DNS 与证书；只有确认 Fake-IP 环境才启用兼容。有限重试后如实记录，不关闭证书或内网检查 |
| 平台登录失效、验证码或限流 | 本人检查专用会话，按冷却期与预算恢复；公众号在桥接管理界面恢复授权/任务，不追加密集请求 |
| SQLite busy 或并发异常 | 检查重复进程与跨宿主机/容器写入，正式库使用容器/页面入口；停止冲突写入后再恢复，不复制活跃 WAL 文件 |
| 快照文章数与主库不同 | 先检查 integrity 和保留策略；核对非 Reddit 原文/绑定及 saved_annotations，不能只比较总数 |

## 验收边界

代码回归、类型、lint、构建、健康、浏览器、真实平台、真实模型和恢复分别记录命令、日期、revision、环境与样本。登录就绪不是后续增量成功，RSS 可读不是字幕可取，模型联调不是自动模式资格；未执行保持待验收。
