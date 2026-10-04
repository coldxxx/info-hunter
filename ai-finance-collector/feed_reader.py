"""Conditional RSS requests; never cache an invalid feed or an error page."""
import sqlite3
import urllib.error


def read(source,context):
    url=source.get('feed_url') or source['url']
    cached=None
    if source.get('id'):
        with sqlite3.connect(context['db'],timeout=30) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='feed_cache'").fetchone():
                cached=c.execute('SELECT etag,modified,payload FROM feed_cache WHERE url=?',(url,)).fetchone()
    headers={}
    if cached:
        if cached[0]:headers['If-None-Match']=cached[0]
        if cached[1]:headers['If-Modified-Since']=cached[1]
    try:raw=context['fetch'](url,headers=headers) if headers else context['fetch'](url)
    except urllib.error.HTTPError as e:
        if e.code==304 and cached: return context['parse_feed'](cached[2]),'成功',''
        raise
    rows=context['parse_feed'](raw)
    metadata=getattr(getattr(context['fetch'],'metadata',None),'value',{})
    if source.get('id') and isinstance(metadata,dict):
        with sqlite3.connect(context['db'],timeout=30) as c:
            c.execute('INSERT OR REPLACE INTO feed_cache VALUES(?,?,?,?)',(url,metadata.get('ETag'),metadata.get('Last-Modified'),raw))
    return rows,'成功',''
