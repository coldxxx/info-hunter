"""Local AI industry research collector. Python 3.9+, standard library only."""
import argparse
import database
import archive_store
import datetime as dt
import email.utils
import fcntl
import hashlib
import html
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import social
import interests
import translation
import watchlists
import engineering
import dedup
import semantic
import semantic_api
import mimetypes
import source_details
import source_lifecycle
import capture
import content_store
import collection_api
import native_client
import reddit_quality
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('RADAR_DATA_DIR', str(ROOT/'data'))) / 'radar.sqlite3'
STATIC = Path(os.environ['RADAR_STATIC_DIR']).resolve() if os.environ.get('RADAR_STATIC_DIR') else None
LOCK = threading.Lock()
TOPICS = {
 '算力与芯片': ['gpu', 'semiconductor', 'nvidia', 'hbm', 'chip', '半導体', '반도체', '芯片', '半导体', '半導體', '英伟达', '輝達'],
 '资本开支与基础设施': ['capex', 'data center', 'datacenter', 'power', 'データセンター', '데이터센터', '资本开支', '数据中心', '資料中心', '液冷', '電力'],
 '模型与商业化': ['llm', 'model', 'inference', 'agent', 'openai', 'deepseek', 'anthropic', '模型', '推理', '生成ai', '生成式', '생성형'],
 '业绩与估值': ['earnings', 'revenue', 'valuation', 'investment', 'profit', 'order', '決算', '売上', '실적', '매출', '订单', '營收', '业绩', '估值', '投资'],
 '政策与供应链': ['export', 'supply chain', 'tariff', 'tsmc', 'samsung', 'hynix', '輸出', '수출', '台积电', '台積電', '供应链', '供應鏈', '出口', '关税'],
}
AI_WORDS = ['artificial intelligence', 'ai', 'llm', 'gpu', 'hbm', 'nvidia', 'openai', 'anthropic', 'deepseek', 'semiconductor', 'inference', '人工智能', '人工智慧', '大模型', '算力', '半导体', '半導体', '半導體', '반도체', '인공지능', '生成', 'tsmc', '台積電', '台积电', 'hynix', 'データセンター', '데이터센터']

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def connect():
    return database.connect(DB)

def init():
    return database.initialize(connect, ROOT, AI_WORDS)

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', value or ''))).strip()

def date(value):
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            d = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat()

def canonical(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('只允许公开 HTTP(S) 链接')
    query = [(k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path, urllib.parse.urlencode(query), ''))

def matches(text, word):
    return bool(re.search(r'\b' + re.escape(word) + r'\b', text)) if word.isascii() else word in text

def classify(text):
    low = text.lower()
    return [tag for tag, words in TOPICS.items() if any(matches(low, w) for w in words)]

def parse_feed(data):
    root = ET.fromstring(data)
    local = lambda t: t.rsplit('}', 1)[-1]
    if local(root.tag) not in ('rss', 'feed', 'RDF'):
        raise ValueError('返回内容不是 RSS/Atom')
    rows = []
    for item in root.iter():
        if local(item.tag) not in ('item', 'entry'):
            continue
        fields = {}
        link = ''
        for child in item:
            key = local(child.tag)
            val = ''.join(child.itertext())
            fields[key] = val
            if key == 'link' and child.get('rel', 'alternate') == 'alternate':
                link = child.get('href') or val
        if not link:
            continue
        rows.append(dict(title=clean(fields.get('title')), url=link.strip(), excerpt=clean(fields.get('description') or fields.get('summary') or fields.get('content'))[:1200], published_at=date(fields.get('pubDate') or fields.get('published') or fields.get('updated') or fields.get('date')), publisher=clean(fields.get('source') or '')))
    return content_store.feed_extras(data,rows)

def transient_fetch_error(error):
    # Retry public GET transport failures, never HTTP responses or invalid certificates.
    if isinstance(error, urllib.error.HTTPError):
        return False
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return False
    return isinstance(reason, (TimeoutError, ConnectionError, ssl.SSLEOFError,
                               http.client.IncompleteRead, http.client.RemoteDisconnected)) or (
        isinstance(reason, ssl.SSLError) and getattr(reason, 'reason', '') == 'UNEXPECTED_EOF_WHILE_READING')


def fetch(url, headers=None):
    fetch.metadata.value = {}
    class PublicRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            interests.validate_public_url(newurl, resolve=True)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    for attempt in range(3):
        interests.validate_public_url(url, resolve=True)
        req = urllib.request.Request(url, headers={'User-Agent':'PersonalAIIndustryRadar/0.3 (RSS reader)', **(headers or {})})
        try:
            with urllib.request.build_opener(PublicRedirect()).open(req,timeout=20) as r:
                limit=32_000_000 if any(kind in r.headers.get('Content-Type','').lower() for kind in ('xml','rss','atom')) else 5_000_000
                data=r.read(limit+1)
                if len(data)>limit:raise ValueError('响应超过'+str(limit//1_000_000)+' MB限制')
                fetch.metadata.value=dict(r.headers)
                return data
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            if attempt == 2 or not transient_fetch_error(error):
                raise
            time.sleep(0.5 * (2 ** attempt))

fetch.metadata=threading.local()

def collect_source(s):
    if s.get('id'):
        with connect() as c:
            if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(s['id'],)).fetchone():
                return [], '已删除', ''
            s=content_store.decorate(c,s)
    rows,status,error = capture.read(s,fetch=fetch,parse_feed=parse_feed,db=DB)
    if status != '成功':return rows,status,error
    eligible=[]
    for row in rows:
        if row.get('deleted') or not reddit_quality.is_reddit(row.get('url')):
            eligible.append(row)
            continue
        decision=reddit_quality.assess(row,s)
        if s.get('id'):
            aid=hashlib.sha256(canonical(row['url']).encode()).hexdigest()[:24]
            with connect() as c:
                old=c.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
                if old:
                    content=c.execute('SELECT body FROM article_content WHERE article_id=?',(aid,)).fetchone()
                    existing=dict(old);existing.update(row)
                    if not existing.get('body') and content:existing['body']=content[0]
                    decision=reddit_quality.record(c,aid,existing,s)
        if decision['eligible']:eligible.append(row)
    rows=eligible
    if '_watch_rules' in s:
        rows=[r for r in rows if r.get('deleted') or watchlists.accepts(s,r)]
    if '博客' in s.get('kind','') and s.get('adapter')=='rss':
        from readable import extract
        attempted=0
        for row in rows:
            if row.get('body') or row.get('media') or attempted>=5:continue
            aid=hashlib.sha256(canonical(row['url']).encode()).hexdigest()[:24]
            with connect() as c:
                if c.execute('SELECT 1 FROM article_content WHERE article_id=?',(aid,)).fetchone():continue
            attempted+=1
            try:row['body']=extract(fetch(row['url']).decode('utf-8','replace'))
            except Exception:row['body_error']='正文未获取；可能需要登录或站点适配，可在详情中重试'
    return rows, '成功', ''

def put(c, s, row):
    return archive_store.put(c, s, row, canonical=canonical, classify=classify, now=now)

def collect(only=None, scheduled=False, topic_id=None):
    if not LOCK.acquire(blocking=False):
        return {'busy': True}
    process_lock = (DB.parent / 'collector.lock').open('a')
    try:
        try:
            fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'busy': True}
        with connect() as c:
            content_store.purge_reddit(c)
            run = c.execute('INSERT INTO runs(started_at) VALUES(?)', (now(),)).lastrowid
            sources = watchlists.collection_sources(c,topic_id)
            for source in sources:
                source['_watch_policy']=max((interests.policy(c,source['id'],topic_id=t['id']) for t in source['_watch_rules']),key=lambda p:p['score'])
            sources = interests.plan(c,sources,scheduled,only)
        results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(collect_source, s): s for s in sources}
            for f in as_completed(futures):
                s = futures[f]
                try:
                    rows, status, error = f.result()
                    with connect() as c:
                        c.execute('BEGIN IMMEDIATE')
                        if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(s['id'],)).fetchone():
                            results.append({'source':s['id'], 'status':'已删除', 'found':0, 'added':0, 'error':''})
                            continue
                        for r in rows:
                            if r.get('deleted'):content_store.remove(c,hashlib.sha256(canonical(r['url']).encode()).hexdigest()[:24])
                        added = sum(put(c,s,r) for r in rows if r.get('title') and not r.get('deleted'))
                except Exception as e:
                    rows, added, status = [], 0, '失败'
                    error = ('HTTP ' + str(e.code)) if isinstance(e, urllib.error.HTTPError) else (type(e).__name__ + ': ' + str(e))[:240]
                with connect() as c:
                    c.execute('UPDATE sources SET status=?,checked_at=?,success_at=CASE WHEN ?=\'成功\' THEN ? ELSE success_at END,error=?,last_count=? WHERE id=? AND deleted_at IS NULL', (status,now(),status,now(),error,len(rows),s['id']))
                results.append({'source':s['id'], 'status':status, 'found':len(rows), 'added':added, 'error':error})
        with connect() as c:
            c.execute('UPDATE runs SET finished_at=?,result=? WHERE id=?', (now(), json.dumps(results,ensure_ascii=False),run))
        if translation.model():
            with connect() as c:recent=c.execute('SELECT * FROM articles ORDER BY collected_at DESC LIMIT 200').fetchall()
            translation.enqueue(connect,recent)
        backup()
        return {'results': results}
    finally:
        process_lock.close()
        LOCK.release()

def backup():
    return archive_store.backup(connect, ROOT)

class Handler(BaseHTTPRequestHandler):
    def send(self, obj, code=200):
        body = json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def static_file(self, path):
        if STATIC is None:
            return self.send({'error':'Not found'},404)
        rel=urllib.parse.unquote(path).lstrip('/') or 'index.html'
        root=STATIC.resolve()
        file=(root/rel).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            return self.send({'error':'Not found'},404)
        body=file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-cache' if file.name=='index.html' else 'public, max-age=3600')
        self.end_headers();self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1'):
            return self.send({'error':'仅允许本机访问'},403)
        p = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(p.query))
        if not p.path.startswith('/api/'):
            return self.static_file(p.path)
        with connect() as c:
            try:
                extra=semantic_api.get(p.path,q,c)
                if extra is not None:return self.send(extra)
                extra=collection_api.get(p.path,q,c,sys.modules[__name__])
                if extra is not None:return self.send(extra)
            except (ValueError,KeyError,urllib.error.URLError) as e:return self.send({'error':str(e)},400)
            if p.path == '/api/watch-topics':
                self.send(watchlists.listing(c))
            elif p.path == '/api/status':
                tid=q.get('watch_id')
                if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return self.send({'error':'主题不存在'},404)
                count=dedup.count(c,' WHERE '+reddit_quality.VISIBLE+(' AND EXISTS(SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)' if tid else ''),[tid] if tid else [])
                self.send({'count':count, 'busy':LOCK.locked(), 'last_run':dict(r) if (r:=c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()) else None})
            elif p.path == '/api/sources':
                rows=[];tid=q.get('watch_id')
                connections=social.settings()
                native_connections=native_client.snapshot() if c.execute('SELECT 1 FROM source_connections LIMIT 1').fetchone() else {}
                topics={t['id']:t for t in watchlists.configs(c)}
                if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return self.send({'error':'主题不存在'},404)
                for r in c.execute('SELECT * FROM sources WHERE deleted_at IS NULL ORDER BY id'):
                    binding=c.execute('SELECT include_all FROM watch_sources WHERE topic_id=? AND source_id=?',(tid,r['id'])).fetchone() if tid else None
                    if tid and q.get('all')!='1' and not binding:continue
                    config=content_store.decorate(c,json.loads(r['config']));control=c.execute('SELECT enabled FROM source_controls WHERE source_id=?',(r['id'],)).fetchone()
                    if control:config['enabled']=bool(control[0])
                    memberships=[dict(id=b['topic_id'],name=topics[b['topic_id']]['name'],enabled=topics[b['topic_id']]['enabled'],include_all=bool(b['include_all'])) for b in c.execute('SELECT topic_id,include_all FROM watch_sources WHERE source_id=? ORDER BY topic_id',(r['id'],)) if b['topic_id'] in topics]
                    preference=interests.policy(c,r['id'],topic_id=tid) if tid else max((interests.policy(c,r['id'],topic_id=t['id']) for t in memberships if t['enabled']),key=lambda p:p['score'],default=interests.policy(c,r['id']))
                    connection=native_connections.get(config.get('connection_id'),{})
                    body_count=c.execute("SELECT count(*) FROM sightings s JOIN article_content ac ON ac.article_id=s.article_id WHERE s.source_id=? AND ac.body<>''",(r['id'],)).fetchone()[0]
                    rows.append(dict(r,connection_status=connection.get('status','未连接' if config.get('connection_id') else '未绑定' if config.get('adapter')=='browser' else '无需登录'),next_at=max(connection.get('next_visit_at',0),connection.get('sources_next_at',{}).get(r['id'],0)),body_count=body_count,config=config,effective_adapter=social.effective_adapter(config,connections),topics=memberships,followed=bool(binding),include_all=bool(binding[0]) if binding else False,preference=preference))
                self.send(sorted(rows,key=lambda r:-r['preference']['score']))
            elif p.path == '/api/source-detail':
                tid=q.get('watch_id') or None
                if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return self.send({'error':'主题不存在'},404)
                row=c.execute('SELECT * FROM sources WHERE id=? AND deleted_at IS NULL',(q.get('id',''),)).fetchone()
                if not row:return self.send({'error':'来源不存在'},404)
                self.send(source_details.describe(c,dict(row),tid))
            elif p.path == '/api/translations':
                ids=q.get('ids','').split(',')[:50]
                articles=c.execute('SELECT * FROM articles WHERE id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
                self.send({'enabled':bool(translation.model()),'items':{a['id']:translation.cached(c,dict(a)) for a in articles}})
            elif p.path == '/api/connections':
                self.send(social.connection_status())
            elif p.path == '/api/articles':
                where, args = [], []
                if not q.get('id'):where.append(reddit_quality.VISIBLE)
                if q.get('id'):
                    where.append('id=?');args.append(q['id'])
                if q.get('watch_id'):
                    if not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(q['watch_id'],)).fetchone():return self.send({'error':'主题不存在'},404)
                    where.append('EXISTS (SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)');args.append(q['watch_id'])
                if q.get('engineering_category'):
                    if not q.get('watch_id') or watchlists.get(c,q['watch_id']).get('content_profile')!='developer':return self.send({'error':'技术方向仅用于开发者主题'},400)
                    category=q['engineering_category']
                    if category not in engineering.CATEGORIES+['手动收录']:return self.send({'error':'无效的技术方向'},400)
                    if category=='手动收录':
                        where.append("EXISTS (SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=? AND aw.reason='手动收录')");args.append(q['watch_id'])
                    else:
                        where.append("EXISTS (SELECT 1 FROM article_focus af WHERE af.article_id=articles.id AND af.profile='developer' AND af.eligible=1 AND af.category=?)");args.append(category)
                for key in ('region','kind','source_id'):
                    if q.get(key):
                        where.append(key+'=?'); args.append(q[key])
                if q.get('q'):
                    where.append('(title LIKE ? OR excerpt LIKE ? OR note LIKE ? OR EXISTS (SELECT 1 FROM article_content ac WHERE ac.article_id=articles.id AND ac.body LIKE ?) OR EXISTS (SELECT 1 FROM translations t WHERE t.article_id=articles.id AND t.model=? AND t.status=\'完成\' AND (t.title LIKE ? OR t.excerpt LIKE ?)))')
                    term='%'+q['q']+'%';args.extend([term,term,term,term,translation.model(),term,term])
                if q.get('topic'):
                    where.append('topics LIKE ?'); args.append('%'+q['topic']+'%')
                if q.get('starred') == '1':
                    where.append('starred=1')
                if q.get('since'):
                    where.append('published_at>=?'); args.append(q['since'])
                clause = ' WHERE '+' AND '.join(where) if where else ''
                try:
                    offset = max(0,int(q.get('offset','0')))
                except ValueError:
                    return self.send({'error':'无效分页'},400)
                raw=q.get('collapse')=='0'
                total = dedup.count(c,clause,args,raw=raw)
                rows = dedup.page(c,clause,args,offset,raw=raw)
                source_names={r['id']:json.loads(r['config'])['name'] for r in c.execute('SELECT id,config FROM sources')}
                def serialize(r):
                    reason=c.execute('SELECT reason FROM article_watches WHERE article_id=? AND topic_id=?',(r['id'],q.get('watch_id',''))).fetchone()
                    focus=c.execute("SELECT category FROM article_focus WHERE article_id=? AND profile='developer' AND eligible=1",(r['id'],)).fetchone()
                    metadata=content_store.info(c,r['id'])
                    quality=c.execute('SELECT eligible,reason,comment_count,evidence FROM article_quality WHERE article_id=?',(r['id'],)).fetchone()
                    item=dict(r,source_name=source_names.get(r['source_id'],'手动录入'),content_status=metadata['status'],media=metadata['media'],topics=json.loads(r['topics']),match_reason=reason[0] if reason else '',engineering_category='手动收录' if reason and reason[0]=='手动收录' else (focus[0] if focus else ''))
                    item['reddit_quality']=dict(quality) if quality else None
                    for key in ('duplicate_group','duplicate_priority','duplicate_rank'):item.pop(key,None)
                    return item
                items=[]
                for r in rows:
                    item=serialize(r)
                    item['duplicates']=[serialize(v) for v in dedup.versions(c,r['duplicate_group'],q.get('watch_id')) if v['id']!=r['id']]
                    item['duplicate_count']=len(item['duplicates'])+1
                    items.append(item)
                self.send({'total':total,'items':items})
            else:
                self.send({'error':'Not found'},404)

    def do_POST(self):
        # Local Vite proxy preserves Host. Reject cross-site writes and foreign Host headers.
        host = self.headers.get('Host','').split(':')[0]
        origin = self.headers.get('Origin')
        allowed_origins={'http://'+h+':'+str(port) for h in ('localhost','127.0.0.1') for port in (43187,43188,int(os.environ.get('RADAR_PUBLIC_PORT','43187')))}
        if host not in ('localhost','127.0.0.1') or (origin and origin not in allowed_origins):
            return self.send({'error':'仅允许本机操作'},403)
        try:
            if urllib.parse.urlsplit(self.path).path=='/api/media-upload':
                aid=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)).get('id','')
                with connect() as c:return self.send(collection_api.upload(self,c,aid))
            size = int(self.headers.get('Content-Length','0'))
            if size < 0 or size > 100_000:
                return self.send({'error':'请求过大'},413)
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body,dict):raise ValueError('请求必须为JSON对象')
            with connect() as c:
                extra=semantic_api.post(self.path,body,c)
                if extra is None:extra=collection_api.post(self.path,body,c,sys.modules[__name__])
            if extra is not None:return self.send(extra)
            if self.path == '/api/watch-topic':
                with connect() as c:result=watchlists.save(c,body)
                self.send(result)
            elif self.path == '/api/watch-source':
                tid=body['watch_id'];sid=body['source_id']
                if not isinstance(body.get('include_all',False),bool):raise ValueError('include_all须为布尔值')
                if not isinstance(body.get('follow',True),bool):raise ValueError('follow须为布尔值')
                with connect() as c:
                    watchlists.get(c,tid)
                    if body.get('follow',True):watchlists.bind(c,tid,sid,body.get('include_all',False))
                    else:c.execute('DELETE FROM watch_sources WHERE topic_id=? AND source_id=?',(tid,sid))
                    watchlists.reindex(c,tid)
                self.send({'ok':True})
            elif self.path == '/api/watch-sources':
                if not isinstance(body.get('include_all',False),bool):raise ValueError('include_all须为布尔值')
                with connect() as c:result=watchlists.bind_many(c,body['watch_id'],body.get('source_ids'),body.get('include_all',False))
                self.send(result)
            elif self.path == '/api/translate':
                ids=body.get('ids',[])
                if not isinstance(ids,list) or len(ids)>50 or any(not isinstance(i,str) for i in ids):raise ValueError('每次最多翻译50条资料')
                with connect() as c:articles=c.execute('SELECT * FROM articles WHERE id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
                self.send({'enabled':bool(translation.model()),'queued':translation.enqueue(connect,articles,body.get('retry') is True)},202)
            elif self.path == '/api/source':
                if not isinstance(body.get('include_all',True),bool):raise ValueError('include_all须为布尔值')
                if body.get('watch_id') is not None and not isinstance(body['watch_id'],str):raise ValueError('无效的主题')
                url=canonical(str(body['url']).strip())
                learned=interests.discover(url,fetch,parse_feed,canonical,body.get('feed_url') or None)
                if str(body.get('name','')).strip():learned['name']=str(body['name']).strip()[:200]
                with connect() as c:result=interests.register(c,learned,url,canonical,body.get('watch_id','ai') or None,body.get('include_all',True))
                self.send(result)
            elif self.path == '/api/source-delete':
                with connect() as c:result=source_lifecycle.delete(c,body.get('source_id'))
                self.send(result)
            elif self.path == '/api/source-feedback':
                source_id=body['source_id'];kind=body['action'];tid=body.get('watch_id') or 'ai'
                with connect() as c:
                    watchlists.get(c,tid)
                    if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(source_id,)).fetchone():raise ValueError('来源不存在')
                    if kind in ('pause','resume'):
                        reason=body.get('reason')
                        if reason is not None and (not isinstance(reason,str) or len(reason)>300):raise ValueError('暂停原因最多300字')
                        c.execute('INSERT OR REPLACE INTO source_controls VALUES(?,?)',(source_id,int(kind=='resume')))
                        if kind=='pause' and reason:
                            c.execute('UPDATE sources SET error=? WHERE id=?',(reason,source_id))
                    elif kind in ('prefer','less'):
                        interests.signal(c,source_id,'explicit:prefer','prefer',kind=='prefer',topic_id=tid)
                        interests.signal(c,source_id,'explicit:less','less',kind=='less',topic_id=tid)
                    elif kind=='reset':
                        if tid=='ai':c.execute("DELETE FROM source_signals WHERE source_id=? AND signal_key NOT LIKE 'scope:%'",(source_id,))
                        else:
                            prefix='scope:'+tid+':'
                            c.execute('DELETE FROM source_signals WHERE source_id=? AND substr(signal_key,1,?)=?',(source_id,len(prefix),prefix))
                    else:raise ValueError('无效来源操作')
                    result=interests.policy(c,source_id,topic_id=tid)
                self.send(result)
            elif self.path == '/api/collect':
                tid=body.get('watch_id') or None
                with connect() as c:
                    if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return self.send({'error':'主题不存在'},404)
                threading.Thread(target=collect,kwargs={'topic_id':tid},daemon=True).start()
                self.send({'accepted':True},202)
            elif self.path == '/api/backup':
                self.send({'path':backup()})
            elif self.path == '/api/article':
                if body.get('review','未核验') not in ('未核验','已核验','存疑'):
                    raise ValueError('无效核验状态')
                with connect() as c:
                    tid=body.get('watch_id') or 'ai';watchlists.get(c,tid)
                    old=c.execute('SELECT * FROM articles WHERE id=?',(body['id'],)).fetchone()
                    if not old:raise ValueError('资料不存在')
                    for hit in c.execute('SELECT source_id FROM sightings WHERE article_id=?',(body['id'],)).fetchall():
                        sid=hit[0]
                        interests.signal(c,sid,'star:'+body['id'],'star',bool(body.get('starred')),topic_id=tid)
                        interests.signal(c,sid,'verified:'+body['id'],'verified',body.get('review')=='已核验',topic_id=tid)
                    c.execute('UPDATE articles SET starred=?,note=?,review=? WHERE id=?',(int(bool(body.get('starred'))),str(body.get('note',''))[:20000],body.get('review','未核验'),body['id']))
                self.send({'ok':True})
            elif self.path == '/api/import':
                if not str(body.get('title','')).strip():
                    raise ValueError('标题不能为空')
                s = {'id':'manual-import','name':body.get('publisher','手动录入'),'region':body.get('region','全球'),'language':body.get('language','未知'),'kind':body.get('kind','研报')}
                body['published_at'] = date(body.get('published_at'))
                body['excerpt'] = str(body.get('excerpt',''))[:20000]
                with connect() as c:
                    tid=body.get('watch_id') or 'ai';watchlists.get(c,tid)
                    added = put(c,s,body)
                    aid=hashlib.sha256(canonical(body['url']).encode()).hexdigest()[:24]
                    c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(aid,tid,'手动收录'))
                self.send({'added':added})
            else:
                self.send({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError,urllib.error.URLError,OSError,ET.ParseError) as e:
            self.send({'error':str(e)},400)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init','collect','serve','backup','status','semantic-status','semantic-run','semantic-evaluate'])
    parser.add_argument('--source')
    parser.add_argument('--watch-topic')
    parser.add_argument('--evaluation-file')
    args = parser.parse_args()
    init()
    content_store.scrub_backups(Path(os.environ.get('RADAR_BACKUP_DIR',str(ROOT/'backups'))))
    if args.command == 'collect':
        print(json.dumps(collect(args.source,topic_id=args.watch_topic),ensure_ascii=False,indent=2))
    elif args.command == 'serve':
        semantic.start_worker(connect,DB)
        with connect() as c:translation.recover(c)
        def periodic():
            # The process must remain running; missed feed history is not guaranteed.
            while not threading.Event().wait(6 * 60 * 60):
                try:
                    collect(scheduled=True)
                except Exception as e:
                    print('Scheduled collection failed:', type(e).__name__, flush=True)
        threading.Thread(target=periodic, daemon=True).start()
        def native_periodic():
            import native_client, time
            while not threading.Event().wait(60):
                try:
                    with connect() as c:
                        content_store.purge_reddit(c)
                        content_store.sync_jobs(c)
                        bindings={r['source_id']:r['connection_id'] for r in c.execute('SELECT * FROM source_connections')}
                        if not bindings:continue
                        candidates=watchlists.collection_sources(c,None)
                        candidates=[s for s in candidates if social.effective_adapter(content_store.decorate(c,s))=='browser-auto']
                        checked={r['id']:r['checked_at'] or '' for r in c.execute('SELECT id,checked_at FROM sources')}
                    connections={r['id']:r for r in native_client.call('/v1/connections')['items']}
                    used=set()
                    for source in sorted(candidates,key=lambda s:checked.get(s['id'],'')):
                        cid=bindings.get(source['id']);connection=connections.get(cid)
                        if not source.get('enabled',True) or not connection or cid in used:continue
                        if connection['status'] not in ('ready','cooldown') or connection['next_visit_at']>time.time():continue
                        if connection['sources_next_at'].get(source['id'],0)>time.time():continue
                        used.add(cid);collect(only=source['id'])
                except Exception as e:print('Native scheduler:',type(e).__name__,flush=True)
        threading.Thread(target=native_periodic,daemon=True).start()
        host=os.environ.get('RADAR_BIND_HOST','127.0.0.1');port=int(os.environ.get('RADAR_PORT','43188'))
        print(f'Radar listening on {host}:{port}',flush=True)
        ThreadingHTTPServer((host,port),Handler).serve_forever()
    elif args.command == 'semantic-status':
        with connect() as c:print(json.dumps(semantic.status(c),ensure_ascii=False,indent=2))
    elif args.command == 'semantic-run':
        with connect() as c:
            cfg=semantic.settings(c)
            if not cfg['enabled']:raise SystemExit('请先在语义去重页面开启本地模型处理')
            print('Queued:',semantic.enqueue(c,args.watch_topic))
        while semantic.process_one(connect,cfg):pass
    elif args.command == 'semantic-evaluate':
        if not args.evaluation_file:raise SystemExit('请用 --evaluation-file 指定独立人工标注 JSON 文件')
        with connect() as c:
            report=semantic.evaluate(c,semantic.settings(c),json.loads(Path(args.evaluation_file).read_text()))
            print(json.dumps({k:v for k,v in report.items() if k!='predictions'},ensure_ascii=False,indent=2))
    elif args.command == 'backup':
        print(backup())
    elif args.command == 'status':
        with connect() as c:
            print(json.dumps([dict(r) for r in c.execute('SELECT id,status,last_count,error FROM sources WHERE deleted_at IS NULL')],ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
