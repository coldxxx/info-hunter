"""Additive full-text/media storage, shared by all topics."""
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import native_client
import interests
import semantic


def schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS article_content(article_id TEXT PRIMARY KEY, body TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT 'metadata', segments TEXT NOT NULL DEFAULT '[]', media TEXT NOT NULL DEFAULT '{}', job_id TEXT, error TEXT NOT NULL DEFAULT '', updated_at REAL);
    CREATE TABLE IF NOT EXISTS source_connections(source_id TEXT PRIMARY KEY, connection_id TEXT NOT NULL, adapter TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS feed_cache(url TEXT PRIMARY KEY, etag TEXT, modified TEXT, payload BLOB);
    CREATE TABLE IF NOT EXISTS saved_annotations(article_id TEXT PRIMARY KEY,note TEXT,starred INTEGER,review TEXT);
    CREATE TABLE IF NOT EXISTS article_retention(article_id TEXT PRIMARY KEY, expires_at REAL NOT NULL);
    ''')
    if 'job_state' not in {r[1] for r in c.execute('PRAGMA table_info(article_content)')}:
        c.execute("ALTER TABLE article_content ADD COLUMN job_state TEXT NOT NULL DEFAULT 'pending'")


def store(c, aid, row):
    body = row.get('body') or ''
    media = row.get('media') or {}
    if body or media:
        c.execute('INSERT INTO article_content(article_id,body,origin,media,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(article_id) DO UPDATE SET body=CASE WHEN excluded.body<>\'\' AND article_content.origin IN (\'metadata\',\'article\') THEN excluded.body ELSE article_content.body END, origin=CASE WHEN excluded.body<>\'\' AND article_content.origin=\'metadata\' THEN \'article\' ELSE article_content.origin END, error=\'\', media=CASE WHEN excluded.media<>\'{}\' THEN excluded.media ELSE article_content.media END, updated_at=excluded.updated_at',
                  (aid, body, 'article' if body else 'metadata', json.dumps(media, ensure_ascii=False), time.time()))
    if row.get('body_error'):
        c.execute('INSERT INTO article_content(article_id,error) VALUES(?,?) ON CONFLICT(article_id) DO UPDATE SET error=excluded.error',(aid,row['body_error']))
    if 'reddit.com/' in row.get('url', ''):
        c.execute('INSERT OR REPLACE INTO article_retention VALUES(?,?)', (aid, time.time() + 48 * 3600))
    if semantic.mark_dirty(c,aid):semantic.rebuild(c)


def purge_reddit(c, all_content=False):
    c.execute('PRAGMA secure_delete=ON')
    c.execute("DELETE FROM feed_cache WHERE url LIKE '%reddit.com/%'")
    # The API recommends a short-lived cache; expired raw content is not archived.
    ids=[r[0] for r in c.execute('SELECT article_id FROM article_retention' + ('' if all_content else ' WHERE expires_at<=?'), () if all_content else (time.time(),))]
    if all_content:ids=list(set(ids+[r[0] for r in c.execute("SELECT id FROM articles WHERE url LIKE 'https://%reddit.com/%'")]))
    for aid in ids: remove(c,aid)
    return len(ids)


def scrub_backups(folder):
    """Remove provider content from older ordinary SQLite snapshots as well."""
    import sqlite3
    from pathlib import Path
    for file in Path(folder).glob('*.sqlite3'):
        if file.is_symlink():continue
        with sqlite3.connect(file) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='articles'").fetchone():continue
            if not c.execute("SELECT 1 FROM articles WHERE url LIKE 'https://%reddit.com/%' LIMIT 1").fetchone():continue
            schema(c);purge_reddit(c,all_content=True);c.commit();c.execute('VACUUM')


def remove(c,aid):
    semantic.remove(c,aid)
    original=c.execute('SELECT note,starred,review FROM articles WHERE id=?',(aid,)).fetchone()
    if original and (original[0] or original[1] or original[2]!='未核验'):
        c.execute('INSERT OR REPLACE INTO saved_annotations VALUES(?,?,?,?)',(aid,*original))
    for table in ('article_content','translations','sightings','article_watches','article_focus','article_duplicates','article_retention','article_quality'):
        if c.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():c.execute(f'DELETE FROM {table} WHERE article_id=?',(aid,))
    c.execute('DELETE FROM articles WHERE id=?',(aid,))
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_members'").fetchone():semantic.rebuild(c)


def info(c, aid, refresh=False, native_timeout=15):
    r = c.execute('SELECT * FROM article_content WHERE article_id=?', (aid,)).fetchone()
    data = dict(r) if r else dict(article_id=aid, body='', origin='metadata', segments='[]', media='{}', job_id=None, error='')
    data['segments'] = json.loads(data['segments']); data['media'] = json.loads(data['media'])
    if data['job_id'] and refresh:
        try:
            job = native_client.call('/v1/transcription-jobs/' + data['job_id'],timeout=native_timeout)
            data['job'] = job
            c.execute('UPDATE article_content SET job_state=? WHERE article_id=?',(job['status'],aid))
            if job['status'] == 'completed':
                result = job['result']
                data.update(body=result['text'], segments=result['segments'], origin=result.get('origin','local-asr'), error='')
                c.execute('UPDATE article_content SET body=?,segments=?,origin=?,error=\'\',updated_at=? WHERE article_id=?',
                          (data['body'], json.dumps(data['segments'], ensure_ascii=False), data['origin'], time.time(), aid))
                if semantic.mark_dirty(c,aid):semantic.rebuild(c)
            elif job['status'] == 'failed':
                data['error'] = job['error']
                c.execute('UPDATE article_content SET error=?,updated_at=? WHERE article_id=?',(data['error'],time.time(),aid))
            elif job['status']=='cancelled':
                data['error']='任务已取消'
                c.execute('UPDATE article_content SET error=?,updated_at=? WHERE article_id=?',(data['error'],time.time(),aid))
        except ValueError as e:
            data['error'] = str(e)
    data['status'] = ('已有字幕' if data['origin'] in ('manual-caption','automatic-caption','publisher-transcript') else '已转写' if data['origin']=='local-asr' else '已有正文') if data['body'] else ('未检测到语音' if data['origin']=='local-asr' else '等待转写' if data['job_id'] else '仅有标题摘要')
    if data['body'] and data['origin']=='article' and data['media'].get('type'):data['status']='已有正文 · 音频待提取'
    return data


def sync_jobs(c):
    ids=[r[0] for r in c.execute("SELECT article_id FROM article_content WHERE job_id IS NOT NULL AND job_state IN ('pending','queued','running') ORDER BY updated_at LIMIT 20")]
    for aid in ids:info(c,aid,refresh=True,native_timeout=2)


def attach_job(c, aid, job):
    c.execute('INSERT INTO article_content(article_id,job_id,updated_at) VALUES(?,?,?) ON CONFLICT(article_id) DO UPDATE SET job_id=excluded.job_id,job_state=\'pending\',error=\'\',updated_at=excluded.updated_at', (aid, job['id'], time.time()))


def extract(c, aid):
    article = c.execute('SELECT * FROM articles WHERE id=?', (aid,)).fetchone()
    if not article: raise ValueError('资料不存在')
    current = info(c, aid)
    if current['body'] and current['origin'] != 'article': return current
    if current['job_id']:
        old = native_client.call('/v1/transcription-jobs/' + current['job_id'])
        if old['status'] not in ('failed','cancelled'): return old
    media = current['media']
    job = native_client.call('/v1/media-jobs', {'url': article['url'], 'media': media}, timeout=20)
    attach_job(c, aid, job)
    return job


def decorate(c, source):
    binding = c.execute('SELECT * FROM source_connections WHERE source_id=?', (source.get('id',''),)).fetchone()
    if not binding:return source
    result=dict(source,adapter=binding['adapter'],connection_id=binding['connection_id'])
    platform=connection_for(source)['platform'];result['platform']=platform
    if platform=='reddit':
        parts=urllib.parse.urlsplit(source['url']).path.split('/')
        if len(parts)>2:result['subreddit']=parts[2]
    return result


def connection_for(source):
    parsed=urllib.parse.urlsplit(source['url']);host=parsed.hostname or ''
    platform = 'x' if host in ('x.com','www.x.com','twitter.com','www.twitter.com') else 'reddit' if host in ('reddit.com','www.reddit.com','old.reddit.com') else 'blog'
    if platform=='x' and (not re.fullmatch(r'/[A-Za-z0-9_]{1,15}/?',parsed.path) or parsed.path.strip('/').lower() in ('home','search','explore','i')):raise ValueError('隔离采集需要具体 X 作者主页；请新增作者来源，原有主页/搜索入口保留为辅助来源')
    url=source['url'] if platform!='blog' else urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,'/','',''))
    return dict(platform=platform, url=url)


def feed_extras(data, rows):
    root = ET.fromstring(data)
    local = lambda tag: tag.rsplit('}',1)[-1]
    by_url = {r['url']:r for r in rows}
    for item in root.iter():
        if local(item.tag) not in ('item','entry'): continue
        link = next((ch.get('href') or ''.join(ch.itertext()) for ch in item if local(ch.tag)=='link' and ch.get('rel','alternate')=='alternate'), '').strip()
        row=by_url.get(link)
        if row is None: continue
        media={}
        for ch in item:
            tag=local(ch.tag)
            if tag=='enclosure' or (tag=='link' and ch.get('rel')=='enclosure'):
                url=ch.get('url') or ch.get('href')
                if url and (ch.get('type','').startswith(('audio/','video/')) or (not ch.get('type') and re.search(r'\.(?:mp3|m4a|aac|wav|ogg|opus|mp4|webm)(?:[?]|$)',url,re.I))):
                    media.update(url=url, mime=ch.get('type',''), type='podcast')
            elif tag=='duration': media['duration']=''.join(ch.itertext())
            elif tag=='transcript' and ch.get('url'):
                media['transcript_url']=ch.get('url'); media['transcript_type']=ch.get('type','text/plain')
            elif tag=='videoId': media.update(type='youtube', video_id=ch.text)
        if 'youtube.com/watch' in link: media['type']='youtube'
        if media: row['media']=media
        # RSS content:encoded is a full body, description/summary may be an excerpt.
        full=next((''.join(ch.itertext()) for ch in item if local(ch.tag)=='encoded'), '')
        if full:
            from readable import gated
            text=plain_text(full)
            if gated(text):row['body_error']='订阅仅提供会员预览；请连接该站点后获取全文'
            else:row['body']=text
    return rows


class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.skip+=1
        if tag in ('p','br','div','li','h1','h2','h3'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def plain_text(html):
    parser=Text(); parser.feed(html)
    return '\n'.join(re.sub(r'\s+',' ',line).strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def podcasts(query, fetch, parse_feed):
    if not query.strip(): raise ValueError('请输入节目、人物或主题关键词')
    result=json.loads(fetch('https://itunes.apple.com/search?' + urllib.parse.urlencode(dict(term=query[:120],media='podcast',entity='podcast',limit=12))))
    items=[]
    for r in result.get('results',[]):
        if not r.get('feedUrl'): continue
        items.append(dict(name=r.get('collectionName',''),author=r.get('artistName',''),feed_url=r['feedUrl'],url=r.get('collectionViewUrl',''),updated_at=r.get('releaseDate'),reason='目录匹配：'+query[:120]))
    return items


def preview(url, fetch, parse_feed, query=''):
    interests.validate_public_url(url,resolve=True)
    raw=fetch(url); rows=parse_feed(raw)
    root=ET.fromstring(raw)
    language=next((x.text for x in root.iter() if x.tag.rsplit('}',1)[-1]=='language'),'未知')
    keywords=[word for word in re.split(r'[\s,，]+',query[:120].strip()) if word]
    for row in rows[:10]:row['matched_keywords']=[word for word in keywords if word.lower() in (row['title']+' '+row.get('excerpt','')).lower()]
    return dict(feed_url=url,language=language,episodes=rows[:10],valid=True)


def opml(text):
    root=ET.fromstring(text)
    feeds=[]
    for outline in root.iter('outline'):
        if outline.get('xmlUrl'):
            url=interests.validate_public_url(outline.get('xmlUrl'))
            feeds.append(dict(name=outline.get('text') or outline.get('title') or url,url=url))
    if len(feeds)>100: raise ValueError('一次最多导入100个订阅')
    return feeds
