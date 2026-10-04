"""Persistent, explainable source preferences. Only user feedback earns rewards."""
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import watchlists
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin

WEIGHTS = {'share': 2, 'star': 4, 'verified': 2, 'prefer': 8, 'less': -8}


def schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS source_signals(
      source_id TEXT NOT NULL, signal_key TEXT NOT NULL, kind TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
      PRIMARY KEY(source_id,signal_key));
    CREATE TABLE IF NOT EXISTS source_controls(source_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS submitted_links(
      url TEXT PRIMARY KEY, source_id TEXT NOT NULL, submitted_at TEXT NOT NULL);
    ''')


def signal(c, source_id, key, kind, active=True, topic_id=None):
    if topic_id and topic_id!='ai':key='scope:'+topic_id+':'+key
    if kind not in WEIGHTS:
        raise ValueError('无效偏好信号')
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    # Toggling a bookmark or replaying the same feedback cannot refresh its reward.
    c.execute('''INSERT INTO source_signals VALUES(?,?,?,?,?)
      ON CONFLICT(source_id,signal_key) DO UPDATE SET active=excluded.active''',
      (source_id, key, kind, int(active), stamp))


def policy(c, source_id, at=None, topic_id=None):
    at = at or dt.datetime.now(dt.timezone.utc)
    score, counts = 10.0, {}
    for row in c.execute('SELECT kind,active,created_at,signal_key FROM source_signals WHERE source_id=?', (source_id,)):
        kind, active, stamp, key = row
        if topic_id and topic_id!='ai':
            if not key.startswith('scope:'+topic_id+':'):continue
        elif key.startswith('scope:'):continue
        if not active:
            continue
        age = max(0, (at-dt.datetime.fromisoformat(stamp)).total_seconds()/86400)
        score += WEIGHTS[kind] * math.pow(0.5, age/30)
        counts[kind] = counts.get(kind, 0)+1
    score = max(0, min(100, score))
    hours = 6 if score >= 30 else 12 if score >= 15 else 24
    return {'score': round(score, 2), 'interval_hours': hours, 'signals': counts,
            'reason': '分享、收藏、核验与显式反馈计分；30天减半；采集次数不计分'}


def plan(c, sources, scheduled=False, only=None):
    """Keep established feeds; budget learned feeds with one exploration slot."""
    active, learned = [], []
    now = dt.datetime.now(dt.timezone.utc)
    for s in sources:
        if c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NOT NULL',(s['id'],)).fetchone():
            continue
        control=c.execute('SELECT enabled FROM source_controls WHERE source_id=?',(s['id'],)).fetchone()
        enabled=bool(control[0]) if control else s.get('enabled',True)
        if not enabled or (only and s['id'] != only):
            continue
        p = s.get('_watch_policy') or policy(c, s['id'], now)
        s = dict(s, preference=p)
        if s.get('adapter')=='wechat-rss':
            checked=c.execute('SELECT checked_at FROM sources WHERE id=?',(s['id'],)).fetchone()[0]
            elapsed=(now-dt.datetime.fromisoformat(checked)).total_seconds()/3600 if checked else math.inf
            if scheduled and elapsed<12:continue
            active.append(s);continue
        if not s.get('user_added') and not p['signals']:
            active.append(s)
            continue
        checked = c.execute('SELECT checked_at FROM sources WHERE id=?', (s['id'],)).fetchone()[0]
        elapsed = (now-dt.datetime.fromisoformat(checked)).total_seconds()/3600 if checked else math.inf
        if scheduled and elapsed < p['interval_hours']:
            continue
        s['_elapsed'] = elapsed
        learned.append(s)
    learned.sort(key=lambda s: (-s['preference']['score'], s['id']))
    if only:
        chosen = learned
    elif len(learned) <= 8:
        chosen = learned
    else:
        chosen = learned[:7]
        # Oldest due source still gets a check, even with a low learned score.
        chosen.append(max(learned[7:], key=lambda s: (s['_elapsed'], s['id'])))
    return sorted(active+chosen, key=lambda s: (-s['preference']['score'], s['id']))


def validate_public_url(url, resolve=False):
    p = urlsplit(url)
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:
        raise ValueError('需要公开 HTTP(S) 链接')
    if p.port not in (None,80,443):
        raise ValueError('来源链接仅支持80/443端口')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
        raise ValueError('不能将本机或内部网络设为采集来源')
    try:
        literal=True
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        literal=False
        addresses = [ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, p.port or (443 if p.scheme=='https' else 80), type=socket.SOCK_STREAM)] if resolve else []
    fake_dns=os.environ.get('RADAR_FAKE_DNS')=='1' and not literal
    fake_net=ipaddress.ip_network('198.18.0.0/15')
    if any(not a.is_global and not (fake_dns and a.version==4 and a in fake_net) for a in addresses):
        raise ValueError('来源不能指向本机或内部网络')
    return url


class FeedLinks(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.channel=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='link' and 'alternate' in a.get('rel','').lower() and a.get('type','').lower() in ('application/rss+xml','application/atom+xml') and a.get('href'):
            self.links.append(a['href'])
        if tag=='meta' and a.get('itemprop')=='channelId':
            self.channel=a.get('content')


def identify(url):
    validate_public_url(url)
    p=urlsplit(url); host=p.hostname.lower(); parts=[x for x in p.path.split('/') if x]
    if host in ('reddit.com','www.reddit.com','old.reddit.com'):
        if len(parts)<2 or parts[0].lower()!='r' or not re.fullmatch(r'[A-Za-z0-9_]{1,50}',parts[1]):
            raise ValueError('请提供Reddit板块或该板块内的帖子链接')
        name=parts[1]; return {'platform':'reddit','url':f'https://www.reddit.com/r/{name.lower()}/','name':'Reddit / '+name,'subreddit':name.lower(),'adapter':'browser','kind':'论坛'}
    if host in ('x.com','www.x.com','twitter.com','www.twitter.com'):
        if not parts or not re.fullmatch(r'[A-Za-z0-9_]{1,15}',parts[0]) or parts[0].lower() in ('i','home','search','explore','intent','settings'):
            raise ValueError('请提供X作者主页或带作者名的帖子链接')
        name=parts[0].lower(); return {'platform':'x','url':'https://x.com/'+name,'name':'X / @'+name,'query':f'from:{name} -is:retweet','adapter':'browser','kind':'论坛'}
    if host in ('xueqiu.com','www.xueqiu.com'):
        if not parts or not re.fullmatch(r'\d+',parts[0]):
            raise ValueError('请提供雪球用户主页或该用户的帖子链接')
        return {'platform':'xueqiu','url':'https://xueqiu.com/'+parts[0],'name':'雪球 / '+parts[0],'adapter':'browser','kind':'论坛'}
    if host in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
        return {'platform':'youtube','url':url,'name':'YouTube 来源','adapter':'pending','kind':'视频'}
    return {'platform':'web','url':url,'name':host,'adapter':'pending','kind':'博客/播客'}


def discover(url, fetch, parse_feed, canonical, feed_url=None):
    s=identify(canonical(url))
    if s['platform'] in ('reddit','x','xueqiu') and not feed_url:
        s['note']='来源偏好已记录；浏览器辅助内容需手动读取，不会自动启动浏览器或启用付费API。'
        return s
    target=canonical(feed_url) if feed_url else canonical(url)
    validate_public_url(target)
    if s['platform']=='youtube' and not feed_url:
        m=re.search(r'/channel/(UC[A-Za-z0-9_-]{22})(?:/|$)',urlsplit(target).path)
        if m:
            cid=m.group(1); s['url']='https://www.youtube.com/channel/'+cid
            target='https://www.youtube.com/feeds/videos.xml?channel_id='+cid
    try:
        data=fetch(target)
        try:
            parse_feed(data); chosen=target
        except Exception as first:
            # Non-feed HTML can advertise a feed; arbitrary page bodies are not articles.
            if feed_url:
                raise ValueError('指定链接未返回RSS/Atom') from first
            parser=FeedLinks(); text=data.decode('utf-8','replace'); parser.feed(text)
            if s['platform']=='youtube':
                cid=parser.channel
                if not cid:
                    matches=re.findall(r'"(?:channelMetadataRenderer|videoDetails)"\s*:\s*\{[^}]{0,30000}?"(?:channelId|externalId)"\s*:\s*"(UC[A-Za-z0-9_-]{22})"',text)
                    if matches:cid=matches[0]
                if not cid or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',cid):
                    raise ValueError('未能确认YouTube频道；请填写/channel/UC…主页或频道RSS')
                s['url']='https://www.youtube.com/channel/'+cid
                chosen='https://www.youtube.com/feeds/videos.xml?channel_id='+cid
            elif parser.links:
                chosen=canonical(urljoin(target,parser.links[0]))
            else:
                raise ValueError('页面未公开RSS/Atom，可填写订阅地址后重新添加')
            validate_public_url(chosen); parse_feed(fetch(chosen))
        if s['platform']=='youtube':
            from urllib.parse import parse_qs
            cid=parse_qs(urlsplit(chosen).query).get('channel_id',[''])[0]
            if cid:s['url']='https://www.youtube.com/channel/'+cid
        if s['platform']=='web':s['url']=chosen
        s.update(adapter='rss', feed_url=chosen, note='已验证RSS/Atom，可自动收集新条目的标题、摘要和链接；不代表已观看/收听全文。')
    except Exception as e:
        s.update(adapter='manual', note='待接入：'+str(e)[:220]+'；链接和偏好已保存，可补充RSS后重试。')
    return s


def register(c, s, original_url, canonical, topic_id='ai', include_all=True):
    """Canonical author/channel/community identity, persistent outside seed JSON."""
    if topic_id:watchlists.get(c,topic_id)
    url=canonical(s['url']); ident='user-'+hashlib.sha256(url.encode()).hexdigest()[:16]
    bridge_key=lambda config: urlsplit(config.get('bridge_feed','')).path.rsplit('/',1)[-1].rsplit('.',1)[0]
    if s.get('adapter')=='wechat-rss':ident='wechat-'+hashlib.sha256(bridge_key(s).encode()).hexdigest()[:16]
    existing=None
    submitted=c.execute('SELECT source_id FROM submitted_links WHERE url=?',(canonical(original_url),)).fetchone()
    for row in c.execute('SELECT id,config FROM sources'):
        config=json.loads(row[1])
        old_url=canonical(config['url']).rstrip('/')
        same=old_url==url.rstrip('/') or bool(submitted and submitted[0]==row[0])
        if s.get('adapter')=='wechat-rss' and config.get('adapter')=='wechat-rss':same=bridge_key(s)==bridge_key(config)
        if s.get('platform')=='reddit':same=old_url.lower()==url.rstrip('/').lower()
        if same:
            existing=(row[0],config);break
    if existing:
        ident,old=existing
        # Following an existing global source cannot downgrade or replace its adapter.
        # A verified RSS discovery may upgrade a user-added source that was pending.
        if old.get('user_added') and old.get('adapter')!='rss' and s.get('adapter')=='rss':
            s={**old,**s}
        else:
            s=old
        url=canonical(s['url'])
    s={**s,'id':ident,'url':url,'region':s.get('region','全球'),'language':s.get('language','未知'),'focused':True,'enabled':s.get('enabled',True)}
    if not existing:s['user_added']=True
    if s.get('feed_url'):
        s['feed_url']=canonical(s['feed_url'])
    c.execute('''INSERT INTO sources(id,config,status) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET
              config=excluded.config,
              status=CASE WHEN sources.deleted_at IS NOT NULL THEN excluded.status ELSE sources.status END,
              checked_at=CASE WHEN sources.deleted_at IS NOT NULL THEN NULL ELSE sources.checked_at END,
              error=CASE WHEN sources.deleted_at IS NOT NULL THEN '' ELSE sources.error END,
              last_count=CASE WHEN sources.deleted_at IS NOT NULL THEN 0 ELSE sources.last_count END,
              deleted_at=NULL''',
              (ident,json.dumps(s,ensure_ascii=False),'未采集' if s['adapter']=='rss' else '待接入'))
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    c.execute('INSERT INTO submitted_links VALUES(?,?,?) ON CONFLICT(url) DO NOTHING',(canonical(original_url),ident,stamp))
    # Same link repeated on the same day contributes once; different author posts do add interest.
    if topic_id:
        watchlists.bind(c,topic_id,ident,include_all)
        signal(c,ident,'share:'+stamp[:10]+':'+canonical(original_url),'share',topic_id=topic_id)
        watchlists.reindex(c,topic_id)
    return {'source_id':ident,'config':s,'preference':policy(c,ident,topic_id=topic_id)}
