"""Read-only, credential-free descriptions of the collector's actual source paths."""
import json
import datetime as dt
import time
import interests
import social
import watchlists
import capture
import content_store
import reddit_quality


def describe(c, row, topic_id=None):
    source = content_store.decorate(c,json.loads(row['config']))
    control = c.execute('SELECT enabled FROM source_controls WHERE source_id=?', (row['id'],)).fetchone()
    if control:
        source['enabled'] = bool(control[0])
    strategy = capture.describe(source)
    adapter = strategy['adapter']
    bindings = []
    for binding in c.execute('SELECT topic_id,include_all FROM watch_sources WHERE source_id=?', (row['id'],)).fetchall():
        topic = watchlists.get(c, binding['topic_id'])
        bindings.append(dict(topic, include_all=bool(binding['include_all']), preference=interests.policy(c, row['id'], topic_id=topic['id'])))
    active = [t for t in bindings if t['enabled']]
    policy = max((t['preference'] for t in active), key=lambda p: p['score'], default=interests.policy(c, row['id'], topic_id=topic_id))
    baseline = not source.get('user_added') and not policy['signals']
    interval = 6 if baseline else policy['interval_hours']
    if adapter=='wechat-rss':interval=12
    if adapter=='browser-auto':interval=6
    steps = []

    def step(title, detail, implementation):
        steps.append({'title': title, 'detail': detail, 'implementation': implementation})

    if adapter=='browser-auto':
        step('选择来源与调度', '先取启用主题的绑定来源，再排除已暂停来源。本机调度器每分钟检查队列；每源至少6小时、同账号至少间隔5分钟、每天最多20次巡检。到期只代表可以排队，账号登录、冷却与访问预算仍可能推迟执行；手动更新也遵守这些限制。', 'radar.py · native_periodic / native/browser_worker.py · reserve')
    else:step('选择来源与调度',
         '先取启用主题的绑定来源，再排除已暂停来源。后台每 6 小时检查一次；' +
         ('这个基础来源没有偏好信号，每轮检查。' if baseline else f'共享来源采用启用主题中最高兴趣分，当前到期间隔 {interval} 小时。每轮最多选择 8 个个性来源：7 个优先来源和 1 个等待最久的来源；到期不保证立即被选中。') +
         '手动更新可提前检查，仍受每轮数量限制。',
         'watchlists.py · collection_sources → interests.py · plan → radar.py · collect')
    step('复用采集策略', f"所有主题共享这个来源配置。使用「{strategy['name']}」策略和「{strategy['adapter_name']}」适配器；只把该来源的入口参数交给共用实现。" + strategy['description'] + '适配器输出标题、链接、摘要、发布时间和发布方，再进入统一筛选与归档。', 'capture.py · ADAPTERS → read → radar.py · collect_source')
    entry = source.get('bridge_feed') if adapter=='wechat-rss' else source.get('feed_url') or source['url']
    access = {'mode': adapter, 'ready': adapter == 'rss', 'message': ''}
    if adapter in ('rss','rss-browser'):
        step('读取公开订阅', '请求已配置的 RSS/Atom 入口，每次验证公开 URL 及重定向。每次请求超时 20 秒；超时、连接中断或 TLS 意外结束最多尝试 3 次，依次等待 0.5、1 秒。证书校验、HTTP 错误及限流不自动重试。XML 订阅上限 32 MB，其他响应上限 5 MB。博客新条目会尝试提取公开正文；音视频只订阅元数据。会员正文需要专用登录会话。', 'capture.py · _feed → radar.py · fetch')
        step('解析与清洗', '解析 RSS / Atom / RDF 的 item 或 entry；提取标题、链接、摘要和发布时间。去除摘要 HTML，摘要最多 1,200 字符；无法解析的日期保留为空。', 'radar.py · parse_feed → clean / date')
        access['message'] = '公开订阅自动读取；成功只代表入口可读，零条结果也可成功。'
    elif adapter in ('x', 'reddit'):
        cfg = social.connection_status()[adapter]
        if adapter == 'x':
            access['ready'] = cfg['credentials_configured'] and cfg['paid_usage_enabled']
            entry = 'https://api.x.com/2/tweets/search/recent'
            access['message'] = f"凭据{'已配置' if cfg['credentials_configured'] else '未配置'} · 付费请求{'已启用' if cfg['paid_usage_enabled'] else '未启用'} · 每日上限 {cfg['daily_request_limit']} 次 · 每次 {cfg['posts_per_request']} 条"
            step('检查授权与请求额度', access['message'] + '。请求前预留次数；达到日上限或处于限流冷却时停止请求。', 'social.py · collect → cooldown → x_rows')
            step('读取官方 API', '使用配置的 query 读取 recent search，提取帖子文本、作者 ID、链接与时间；不分页抓取全量历史。返回部分错误时不会标记成功。', 'social.py · x_rows → request_json')
        else:
            access['ready'] = cfg['credentials_configured'] and cfg['approval_confirmed'] and cfg['enabled'] and cfg['user_agent_configured']
            entry = 'https://oauth.reddit.com/r/' + source.get('subreddit', '') + '/new?limit=50&raw_json=1'
            access['message'] = f"凭据{'已配置' if cfg['credentials_configured'] else '未配置'} · API 审批{'已确认' if cfg['approval_confirmed'] else '未确认'} · 接口{'已启用' if cfg['enabled'] else '未启用'} · User-Agent {'已配置' if cfg['user_agent_configured'] else '未配置'}"
            step('检查审批与 OAuth', access['message'] + '。需要审批、凭据、明确启用和 User-Agent；使用 OAuth 令牌，限流时进入冷却。', 'social.py · collect → cooldown → reddit_rows')
            step('读取板块帖子', '读取板块最新最多 50 条主帖、正文、评论数、外链和分类，并同步响应内的删除或移除状态；原文缓存最长48小时，资料备份不保留 Reddit 原文，个人笔记独立保留。不读取评论树。', 'social.py · reddit_rows → request_json / content_store.py · purge_reddit')
    elif adapter=='wechat-rss':
        access['message']='缓存由本机公众号桥接提供；微信授权和上游更新状态请在桥接管理界面查看。'
        step('读取本机缓存', '主采集器通过本机执行器读取这个公众号的 RSS，强制 is_update=false，不触发微信上游抓取。缓存为空不代表已有文章，桥接限流时暂停来源并保留原因。', 'capture.py · _wechat / native/service.py · wechat_feed')
        step('上游更新与恢复', '独立 We-MP-RSS 服务在授权有效且任务启用时每12小时更新，首次最多一页。上游限流时停用桥接任务，冷却后在桥接中启用并应用，再恢复雷达来源；授权失效时本人重新扫码。', 'We-MP-RSS · 消息任务 / 授权管理')
        step('解析文章正文', '解析缓存 RSS 的标题、链接、发布时间及 content:encoded 正文；全文独立保存，所有关注它的主题复用同一份内容。', 'radar.py · parse_feed / content_store.py · feed_extras → store')
    elif adapter=='browser-auto':
        access['message']='连接：'+source.get('connection_id','本机公众号桥接')+'；请在平台连接中检查授权状态。'
        step('读取独立连接', '本机专用浏览器或公众号桥接负责访问；会话不进入日常浏览器。登录、验证、限流与解析异常分别记录，异常期间停止访问。', 'native/browser_worker.py · collect / native/service.py · wechat_feed')
        step('限频与增量', '浏览器每源至少6小时、账号串行、每日最多20次巡检，每次最多20条与两次滚动；公众号上游每12小时检查。首次只采最新内容，不回溯全量历史。', 'native/browser_worker.py · reserve / We-MP-RSS 定时任务')
        step('正文与媒体', '全文独立存储；音视频仅在点击提取文字后获取字幕或排队本地转写。结果跨主题共享。', 'content_store.py / native/jobs.py / native/transcribe.py')
    elif adapter == 'browser':
        access['message'] = '需要人工读取浏览器可见内容；定时任务只记录浏览器辅助状态，不会自动打开或操作浏览器。'
        step('等待浏览器辅助', access['message'], 'radar.py · collect_source')
        step('人工核对与导入', '现有批次导入仅支持登记的 Reddit、X 与雪球来源（每批 1–50 条），校验平台、作者和可见时间。新添加作者可在「录入资料」保存链接与摘录；该入口记录为手动来源。', 'browser_import.py · import_batch / radar.py · POST /api/import')
    else:
        access['message'] = '没有自动入口；定时任务记录待接入，可补充有效 RSS 地址或手动收录。'
        step('等待接入', source.get('note') or access['message'], 'radar.py · collect_source / interests.py · discover')
        step('手动收录', '在「录入资料」填写链接、标题与自己的摘录。手动资料记为 manual-import，并单独加入选定主题；不会伪装成此来源的自动采集结果。', 'radar.py · POST /api/import')
    if adapter in ('rss','rss-browser', 'x', 'reddit','browser-auto','wechat-rss'):
        if reddit_quality.is_reddit(source['url']):
            minimum=source.get('reddit_min_comments',reddit_quality.MIN_COMMENTS)
            step('Reddit 内容门槛', f'普通讨论至少 {minimum} 条评论，主帖至少240字符且含具体数据、方法或代码/论文线索；足够具体的代码/论文一手链接、至少600字符并同时含数据与方法的主帖可低评论量例外收录。分类为梗图、娱乐或讽刺的内容过滤。评论数缺失记为未知，不当作0。整板收录也应用此规则；评论多不代表质量高，规则不核验事实，也不读取评论树。历史过滤仅隐藏默认信息流，原文与标注保留，收藏、笔记和手动收录仍可访问。', 'native/browser_worker.py · POSTS_JS / social.py · reddit_rows → reddit_quality.py · assess / radar.py · collect_source → put')
        step('应用主题规则', '只保留至少符合一个启用绑定主题的标题与摘要。一般主题先检查地区和排除词，再匹配关键词或全部收录；开发者主题还需符合工程内容规则。「全部收录」仍应用排除词与开发者规则。', 'watchlists.py · accepts → applies / engineering.py · assess')
    step('标准化、去重与归档', '对进入入库路径的条目去掉 URL 中的 utm_*、fbclid、gclid 和片段，按标准化 URL 生成 ID；INSERT OR IGNORE 保留已有原文、笔记与收藏。记录 sightings 入口关系，重新计算主题归属。另对新闻索引与原站的同文记录按标题、发布方、语言和 24 小时内发布时间建立分组，列表分页前折叠；优先展示带标注的版本，其次原站。各版本原文、收藏、笔记与核验状态独立保留，可从同文入口查看。新条目默认未核验。', 'radar.py · canonical → put / dedup.py · index_article → page / watchlists.py · reindex_article')
    step('记录结果与备份', '自动采集写入状态、检查时间、最近成功时间和筛选后的候选数（含重复链接，不等于新增数）。采集轮次分别记录 found 与 added；结束后备份 SQLite。已配置本地翻译时，新条目另行排队翻译。', 'radar.py · collect → backup / translation.py · enqueue')
    total = c.execute('SELECT count(*) FROM sightings WHERE source_id=?', (row['id'],)).fetchone()[0]
    visibility=reddit_quality.VISIBLE.replace('articles.','a.')
    topic_count = c.execute('SELECT count(*) FROM sightings s JOIN articles a ON a.id=s.article_id JOIN article_watches aw ON aw.article_id=s.article_id WHERE s.source_id=? AND aw.topic_id=? AND '+visibility, (row['id'], topic_id)).fetchone()[0] if topic_id else c.execute('SELECT count(*) FROM sightings s JOIN articles a ON a.id=s.article_id WHERE s.source_id=? AND '+visibility,(row['id'],)).fetchone()[0]
    recent = [dict(a) for a in c.execute('SELECT a.id,a.title,a.url,a.published_at,a.collected_at FROM articles a JOIN sightings s ON s.article_id=a.id WHERE s.source_id=? AND '+reddit_quality.VISIBLE.replace('articles.','a.')+' ORDER BY s.seen_at DESC LIMIT 8', (row['id'],))]
    last_run = None
    # A source can be absent from the latest round. Find its latest recorded result.
    for run in c.execute('SELECT id,started_at,finished_at,result FROM runs WHERE result IS NOT NULL ORDER BY id DESC'):
        result = next((r for r in json.loads(run['result']) if r.get('source') == row['id']), None)
        if result:
            last_run = dict(result, run_id=run['id'], started_at=run['started_at'], finished_at=run['finished_at'])
            break
    connection=__import__('native_client').snapshot().get(source.get('connection_id'),{}) if source.get('connection_id') else {}
    if source.get('connection_id'):
        access['ready']=adapter=='rss-browser' or connection.get('status')=='ready'
        access['message']=('公开订阅继续自动读取；会员全文使用' if adapter=='rss-browser' else '')+'连接：'+source['connection_id']+' · '+connection.get('status','执行器未连接')+' · '+connection.get('message','')
    enabled=bool(source.get('enabled',True)) and bool(active)
    next_at=0
    if enabled and adapter=='browser-auto' and connection.get('status') in ('ready','cooldown'):
        next_at=max(connection.get('next_visit_at',0),connection.get('sources_next_at',{}).get(row['id'],0)) or time.time()
    elif enabled and adapter in ('rss','rss-browser','wechat-rss'):
        next_at=dt.datetime.fromisoformat(row['checked_at']).timestamp()+interval*3600 if row.get('checked_at') else time.time()
    return {'connection':connection, 'next_at':next_at, 'source_id': row['id'], 'entry_url': entry, 'query': source.get('query', ''),
            'configured_adapter': source['adapter'], 'effective_adapter': adapter, 'capture_strategy': strategy,
            'connection_id':source.get('connection_id'), 'access': access, 'steps': steps, 'topics': bindings,
            'schedule': {'interval_hours': interval, 'enabled': enabled, 'policy': policy, 'baseline': baseline},
            'stats': {'archived': total, 'in_topic': topic_count}, 'recent': recent, 'last_run': last_run}
