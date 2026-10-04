# 网站采集与本地转写

当前入口：[信息雷达](http://localhost:43187/)；[本机公众号桥接](http://127.0.0.1:43203/)。

来源、正文和转写结果由所有主题共享。主题只保存关注关系和筛选规则，添加已有来源不会复制采集任务。数据库采用增量迁移，原有来源 ID、主题、笔记和收藏继续保留。

## 首次接入

| 平台 | 页面操作 | 实际采集流程 |
| --- | --- | --- |
| X | 来源管理 → 平台连接 → 打开 X 登录，完成小号登录后确认；进入作者来源详情，启用隔离采集 | 同一个专用浏览器读取作者主帖，按帖子链接/ID去重，保存正文。不调用付费 API |
| Reddit | 打开 Reddit 登录，完成小号登录并展开账号菜单后确认；在板块详情启用隔离采集 | 读取 `/new/` 主帖、正文、评论数、外链与分类，先应用内容门槛再应用主题规则。获批后可切换 OAuth，来源及主题绑定继续复用 |
| YouTube | 新增信息源，粘贴频道 `/channel/UC…` 链接或频道 RSS | RSS 发现视频；条目详情点击「提取文字」后才获取字幕或音轨 |
| 播客 | 发现播客 → 搜索主题/人物/节目 → 验证并查看单集 → 订阅 | Apple 目录用于发现；以节目 RSS 采集单集、音轨、时长和文字稿地址 |
| 公开博客 | 新增信息源，粘贴博客主页或 RSS | RSS 正文优先；没有正文的新博客条目尝试提取公开文章正文 |
| 会员博客 | 来源详情启用隔离采集，打开窗口完成邮箱验证，确认登录 | RSS 保留订阅；条目详情「获取全文」通过该站点专用会话读取。登录页及会员预览不保存为全文 |
| 微信公众号 | 在本机桥接登录管理界面，再扫码授权并添加公众号；将生成的 RSS 填入「公众号与文章」，可选补充分享链接 | 主采集器只读取桥接缓存，强制 `is_update=false`，不重复触发上游抓取。可识别的 `MP_WXS_…` 订阅无需分享链接；也可单独导入公开分享文章 |

账号验证、二维码和邮箱验证码需要本人完成。2026-10-05 已确认 X、Reddit 的专用登录会话，两者连接均为就绪；X 也通过原生服务重启后的会话确认。Reddit 首次确认需要展开个人菜单，以个人资料入口作为已登录证据。同日已确认公众号助手管理登录及微信扫码授权，授权管理页面显示已授权、Token 有效。首批来源为 @elonmusk、r/ArtificialInteligence 与 Kevin策略研究，均关注到 AI 产业；X 和公众号按主题关键词筛选，AI 板块整板收录仍需通过 Reddit 内容门槛（默认10条评论及具体主帖内容，明确代码/论文或详细数据与方法可例外；娱乐、讽刺、只有标题的内容过滤）。公众号首轮上游返回频率限制，暂不视为内容采集验收通过。

### 浏览器与访问预算

本机 Chromium 位于项目数据目录，配置保存在 `data/native/profiles/`；X、Reddit 各自独立，博客按域名隔离。不会读取日常浏览器的 Cookie、历史或密码。登录打开普通浏览器进程，由本人操作，不在自动化窗口内进行 Google 授权。登录后关闭该平台所有登录窗口，再点击「确认登录 / 恢复」，采集器才接回同一隔离配置并检查登录。登录期间及执行器重启后仍保留运行的登录窗口锁，后台不会争用配置目录。

macOS 上手动登录和采集均使用系统钥匙串。采集进程移除 Playwright 默认的测试钥匙串及基础密码存储参数，避免无法解密手动窗口保存的会话。旧版本切换后若仍显示登录页，需要本人重新登录；账号连接以实际登录界面检查为准。

Google 仍可能因账号、浏览器或网络拒绝授权；若仍提示浏览器不安全，使用 X 的用户名与密码登录。Google/Apple 创建而没有 X 密码的账号可按 [X 官方说明](https://help.x.com/en/managing-your-account/sso)由本人通过「忘记密码」设置。项目不会降低账号安全设置或代填验证。

每源至少 6 小时一次，每账号串行，账号两次巡检至少间隔 5 分钟，每天最多 20 次，每次最多 20 条、两次滚动。此配置是初始访问预算，不能保证不触发风控。恢复后依然遵守间隔，不集中并发补跑。

验证码/账号限制、401/403、页面结构异常分别暂停连接；429 使用服务器冷却时间。网络失败最多尝试三次后暂停。页面上可打开专用窗口检查，再确认恢复。后台不会自动填写验证码。

Reddit 原文采用最长 48 小时缓存；再次见到帖子可刷新缓存，采集响应中的删除/移除状态会清理资料和索引。普通数据库备份不保留 Reddit 原文；启动时也清理旧 SQLite 备份中的副本。个人笔记、收藏和核验标注单独保留，可在帖子重新出现时恢复。当前不会主动查询整个历史档案逐条核验删除状态。

免费 OAuth 获批后，在宿主机配置供容器读取的私有文件：

```sh
cd /Users/herman/AI/codex/ai-finance-collector
RADAR_CONNECTIONS_FILE="$PWD/data/connections.local.json" python3 social.py configure reddit
```

凭据隐藏输入，文件权限 0600；不要在聊天中粘贴。配置审批确认、Client ID/secret、授权方式及 User-Agent 后，现有 Reddit 来源自动改用 API。X 付费开关保持关闭。

### 公众号桥接首次设置

桥接已独立运行在 Docker，只绑定 `127.0.0.1:43203`，服务会随 Docker 恢复启动。镜像固定到已检查的 digest。配置使用公众号后台 `web` 模式，禁用代理转发、级联共享和抓取失败后的第三方降级；首次最多一页、一个工作线程。

1. 打开桥接管理界面，按[项目说明](https://github.com/rachelos/we-mp-rss)完成管理登录，修改默认密码，再扫码授权公众号管理账号。
2. 添加要跟踪的公众号。在定时任务界面选择这些公众号，创建每 12 小时执行的任务，例如北京时间每天 05:00、17:00，cron 表达式 `0 5,17 * * *`。保持首次一页，不填写第三方 webhook。
3. 复制该公众号 RSS，地址形如 `http://127.0.0.1:43203/api/v1/wx/feed/MP_….rss`，在雷达内连接订阅。分享文章仅用于展示入口，同一个桥接公众号 ID 会复用同一个全局来源；可识别的公众号 ID 会生成官方主页入口。默认按当前主题关键词筛选，也可勾选全部收录。
4. 授权失效时，在桥接界面重新扫码。首次扫码已完成且页面显示有效；首次订阅已完成。上游频率限制时停用消息任务及雷达来源，不追加抓取；冷却后由本人在桥接任务中启用并应用，再恢复雷达来源。实际定时更新及失效恢复仍需实测。

桥接默认管理员自动登录、令牌保存和关闭容器日志的初始化没有执行；管理登录保留为本人操作。桥接是非官方路径，上游可能改变，需要按桥接界面恢复授权。

## 音视频文字

在音视频条目详情点击「提取文字」，或上传已有媒体（最多 512 MB）。点击后先查发布者字幕/文字稿，再尝试公开音轨；获取失败会显示原因，支持改为上传已有文件。

模型为 `mlx-community/whisper-large-v3-turbo`，复用 LM Studio 下载到 `~/.lmstudio/models/mlx-community/whisper-large-v3-turbo` 的模型文件，由 `mlx-whisper` 在 Apple Silicon 原生执行转写，不额外下载项目副本，也不需要启动 LM Studio 的 API 服务。LM Studio 使用自定义模型目录时，通过 `RADAR_WHISPER_MODEL_DIR` 指定该模型文件夹。FFmpeg 每 600 秒分段，去掉近数字静音并保留原始时间偏移；一次运行一个任务，不区分说话人。解码过程保留至少 1 GB 空闲空间，解码输出超过 2 GB 时停止并提示拆分媒体，不截断后伪装成全文。完成后可以查看全文、点击时间戳，并导出 TXT/SRT/VTT/JSON。有字幕或文字稿时保留其来源，与本地模型转写区分。

转写结果持久保存，同一媒体和处理参数复用任务；失败或取消可重试，服务重启恢复排队。媒体缓存保留 7 天，过期清理保留文字；平台连接中显示用量和清理入口。7 天期限针对终态任务，正在运行的媒体不会被清理。

YouTube 获取依赖第三方工具，可因平台限制失败。频道 RSS 可读不等于每个视频的字幕或音轨可取。真实视频提取仍应逐条点击确认。

## 独立 HTTP 与 MCP

转写 API 运行在 `http://127.0.0.1:43202`，访问令牌保存在 `data/native/token`（0600）。不接受网页跨源调用。其他工具可直接调用 API，或使用同一 API 的 stdio MCP 服务。

| 接口 | 功能 |
| --- | --- |
| `POST /v1/transcription-jobs` | multipart 文件字段 `file`，可选 `language` 为 `zh`、`en` 或空；返回任务 ID |
| `GET /v1/transcription-jobs/{id}` | 返回 queued/running/completed/failed/cancelled、进度、错误及完成结果 |
| `POST /v1/transcription-jobs/{id}/cancel` | 取消排队或运行中的任务 |
| `POST /v1/media-jobs` | 提交已确认的 YouTube URL 或 RSS 音轨/文字稿元数据 |
| `POST /v1/cache/cleanup` | 清理过期媒体，返回存储用量 |
| `GET /v1/health` | 服务状态与磁盘用量 |

请求使用 `Authorization: Bearer <本机令牌>`。独立 Python 客户端示例，令牌不打印：

```python
import sys
from pathlib import Path
sys.path.insert(0, '/Users/herman/AI/codex/ai-finance-collector')
import native_client
job = native_client.upload_file(Path('/absolute/path/audio.mp3'), 'zh')
result = native_client.call('/v1/transcription-jobs/' + job['id'])
print(result['status'])
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "local-transcription": {
      "command": "/Users/herman/AI/codex/ai-finance-collector/native/.venv/bin/python",
      "args": ["/Users/herman/AI/codex/ai-finance-collector/native/mcp_server.py"]
    }
  }
}
```

工具为 `transcribe_audio(file_path, language)`、`get_transcription(job_id)`、`cancel_transcription(job_id)`。不需要把令牌写进客户端配置。HTTP/MCP 上传均流式传输，本地模型不会把音频发送给外部转写 API。

## 运行与恢复

本机服务已经安装为当前用户的 LaunchAgent：`com.herman.signal-radar.native`。登录 macOS 时启动并在进程退出后恢复；睡眠期间不运行。公众号桥接及信息雷达需要 Docker Desktop 正常运行。

```sh
launchctl print "gui/$(id -u)/com.herman.signal-radar.native"
launchctl kill SIGTERM "gui/$(id -u)/com.herman.signal-radar.native"
```

日志位于 `data/native/service.log`（0600）；接口访问日志关闭，连接信息不返回凭据。项目数据目录权限 0700。原生服务数据/账号会话不会进入雷达的 SQLite 资料备份。

新机器或重建环境：先在 LM Studio 下载 `mlx-community/whisper-large-v3-turbo`，再安装 `uv`，执行 `sh native/bootstrap.sh` 安装锁定依赖、项目 Chromium 并检查 LM Studio 模型文件，然后运行 `native/.venv/bin/python native/install-launch-agent.py`。现有机器已经完成，不需要重复执行。转写直接读取 LM Studio 的本地模型文件；HTTP媒体/订阅仍按需联网。使用 Fake-IP DNS 的当前机器通过 `native/env.local` 与 compose override 显式启用兼容，不接受用户来源指向本机地址。

公众号桥接可用 `sh native/wechat-start.sh` 恢复。清理缓存使用页面入口；不要直接删除仍被任务引用的工作目录。

Docker 运行期间，通过页面/API 或容器内命令访问实际资料库，例如 `docker exec codex-observatory-1 python radar.py status`。不要在宿主机另开 SQLite 写连接访问同一个资料库；macOS 与 Docker 的跨环境文件锁可能影响 WAL 并发访问。正常备份由页面完成。

## 验证记录

代码及模拟平台路径：129 项后端回归通过，包含共享来源、主题筛选、条件请求、去重、备份、授权/429、访问预算、人工登录不挂载自动化、执行器重启后保留登录窗口锁、macOS 钥匙串一致、确认登录的网络失败状态及账号菜单恢复入口、任务取消/恢复、字幕/无字幕/媒体限制、文字稿/失效音频、公众号无分享链接接入与跨主题身份复用、暂停原因保留，以及解码超限后停止不响应正常终止信号的子进程。前端 TypeScript、修改页面 lint 及容器构建通过。

真实验证：YouTube Google for Developers 频道 RSS 15 个视频；Latent Space 播客 RSS 近期 10 集含音轨，重复入库新增 0；GitHub 博客 RSS 10 篇完整正文。以上使用临时数据库，没有把测试条目写入用户资料库。

本地模型：中文、英文、620 秒跨两段音频验证通过；第二段时间戳约 605 秒，静音段没有生成重复文字。独立 MCP 客户端完成工具发现与提交，并复用了 HTTP 已完成结果。运行中取消、LaunchAgent 重启后恢复并完成任务已实测。

首批真实来源验证：X `user-68fb56627384188a` 读取 8 条作者主帖，当前 AI 关键词匹配 0 条；Reddit `user-a065f94bc532d1b8` 首轮收录 20 条，其中 9 条有正文。两者均使用隔离登录会话与原有低频预算，没有为测试追加巡检。Kevin策略研究已订阅为 `MP_WXS_3076555400`，全局来源 `wechat-b1af65e25d428c3c` 已绑定 AI 产业并按关键词筛选，缓存 RSS 可读但无文章；首次上游明确返回频率限制，停止追加请求。桥接已保存仅针对这个公众号、05:00/17:00 的任务，状态为禁用，没有配置第三方 WebHook；雷达来源也已暂停，并保存限流原因和恢复步骤。部署后容器内 SQLite `quick_check` 返回 `ok`。

仍待真实验证：X、Reddit 后续增量与重复去重、公众号取得文章后的 RSS/定时更新/授权失效恢复、具体会员博客站点，以及真实 YouTube 有字幕/无字幕/不可获取三个视频的逐条提取。这些场景的实现和模拟失败路径已完成，尚未把它们标为真实验收通过。
