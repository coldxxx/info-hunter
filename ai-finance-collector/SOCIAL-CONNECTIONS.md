> 历史资料：以下保留原环境的说明、日期和验收记录。当前启动与开发步骤见[根 README](../README.md)和 [docs 指南](../docs/history/README.md)，旧路径与测试数字不代表本次迁移验收。

# Reddit、X、雪球接入进度

2026-10-04 更新：X、Reddit 新增本机专用 Chromium 自动采集，采用小号、每源6小时及账号串行预算；本人登录后在来源详情绑定。Reddit 获批 OAuth 配置保留。新的步骤、凭据文件路径和原文缓存策略见 [网站采集与本地转写](COLLECTION-SETUP.md)。下文为此前浏览器辅助路线的历史记录。

## 当前路线：不购买 API（2026-09-08）

Reddit、X、雪球现使用 browser 适配器，后台更新不调用这些平台的 API。以下 OAuth / X API 配置仅作为可选代码保留，不是当前路线。

最新实测：用户完成验证与登录后，Reddit LocalLLaMA 网页可读，已入库 5 条标题线索；X 的 AI capex 搜索可读，已入库 3 条摘要线索。均为未核验资料，不含完整正文、图表或视频。网页读取需要本任务手动触发；后台“更新来源”不会启动浏览器。

读取后保存 UTF-8 JSON 数组，每条包含 url、title、author、excerpt、published_at。发布时间未显示则为 null；只保存可见内容的短摘录或明确标记的摘要。执行：

```sh
python3 browser_import.py --source reddit-local /absolute/path/posts.json
```

来源可选 reddit-local、reddit-stocks、x-ai、xueqiu。每批 1–50 条；整批验证、链接去重，保留收藏和笔记，导入后自动备份。该工具负责入库，不是独立浏览器爬虫。

当前实现与实际连通分开记录：Reddit OAuth 与 X API 的适配器已实现，但缺少获批应用/授权，未完成真实取数。2026-09-08 已确认雪球首页处于登录状态；搜索试读时浏览器连接丢失，尚未完成帖子样本入库，更未建立全天自动采集。

## Reddit

普通 Reddit 账号、浏览器登录、创建应用与 Data API 审批是不同步骤。先按官方入口申请数据访问，说明个人、本地、只读的 AI 产业研究用途。没有代你提交申请。

- 官方要求：https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy
- 数据 API：https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki

已获批应用可在本机终端配置：

```sh
cd /Users/herman/AI/codex/ai-finance-collector
python3 social.py configure reddit
python3 radar.py collect --source reddit-local
```

输入应用 Client ID、Client secret、可选 Refresh token 和标识应用及联系账号的 User-Agent。没有 Refresh token 时尝试 client_credentials；应用授权方式是否可用须以获批类型和实际接口结果为准。凭据隐藏输入，不要在聊天中粘贴。

每个社区每轮只取最新 50 帖，无评论树、全历史或全量保证。共享访问令牌，429 时对同一平台进入冷却期并持久保存状态。不会自动切换匿名入口或网络身份。

## X

- 开发者控制台：https://console.x.com/
- 计费说明：https://docs.x.com/x-api/getting-started/pricing

官方当前文档列出 Posts Read 为每个资源 $0.005，具体以控制台为准。默认最多每轮 20 条、每日 4 次，即满量时每日最多返回 80 条帖子，按该单价粗算 $0.40/日；不作为账单保证，也不包含其他应用消耗。应在 X 控制台设置实际费用上限。

```sh
python3 social.py configure x
python3 radar.py collect --source x-ai
```

配置命令明确询问是否启用付费请求；未确认或只有环境变量 Token 时不调用。首次启动没有自动充值或购买。请求数以 UTC 日期统计，网络请求前预占次数，失败和超时也计入本地次数上限。只读帖子，不请求额外作者资料，不发帖、不点赞、不关注。

## 雪球

2026-09-08 已在 https://xueqiu.com/ 首页确认用户登录成功。搜索“算力”后浏览器连接丢失，当前没有可核验的帖子采集样本；下次从搜索结果试读继续，并保留作者、链接和时间。不会读取浏览器 Cookie、调用隐藏接口或把账户会话复制到脚本。浏览器辅助读取不等于无人值守自动接口。

目前可以用网站的“录入资料”保存链接与自己的摘录。尚未找到适用于此用途的公开官方社区 API 文档；这不等于断言雪球不存在合作数据接口。若需要长期自动化，应核实可授权的数据接口或数据合作方式。

## 凭据与运维

`connections.local.json` 是仅当前用户可读写的本地配置文件（权限 0600，不是加密保险库）。它被版本控制忽略，不写入文章库，也不随数据库快照备份。不要将该文件分享或提交到仓库。配置读取发生在每次采集时，不需要因更新凭据重启服务。

```sh
python3 social.py status
```

该命令只显示配置是否存在、启用状态与限制，不显示任何密钥。`/api/connections` 提供同样的脱敏状态。

实现测试使用模拟平台响应，不能证明账号权限或真实连通。收到凭据后须进行单来源真实采集，再根据入库结果标记完成。

## 不购买 API 的第一版方案

Reddit / X 可先采用用户正常可访问网页的浏览器辅助摘录，再保存原链接、作者、时间和短摘要。此模式需要浏览器会话与人工触发，尚未实现后台无人值守；登录或访问限制出现时停止并显示真实状态。公开搜索索引仅作线索补充，存在延迟、漏收与截断，不能代表平台全量内容。

Reddit 匿名 RSS 之前实测返回 429，暂不作为稳定来源；不以切换身份绕过限流。X 官方 API 仍为按使用量计费，个人用途不自动获得免费额度。非官方 RSS 转换和抓取服务需要逐一核实上游来源、访问权限与可用性，目前未接入，也未验证。

## 雪球实测更新（2026-09-08）

算力搜索结果可读，已读取《中贝算力畅想》详情正文；选取3条短摘要入库，全部保持未核验。重复导入新增0条、识别3条重复，备份成功。页面时间原样保存在摘要中，未明确时区的时间不擅自转换。
