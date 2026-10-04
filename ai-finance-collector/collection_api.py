"""Routes for platform connections, discovery, full text, and native media jobs."""
import base64
import hashlib
import http.client
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import content_store as content
import native_client
import interests
import watchlists


def get(path,q,c,radar):
    if path=='/api/platform-connections':
        try: result=native_client.call('/v1/connections');result['available']=True
        except ValueError as e: result=dict(available=False,items=[],error=str(e))
        result['reddit']=__import__('social').connection_status()['reddit']
        result['wechat_url']='http://127.0.0.1:43203'
        return result
    if path=='/api/content':
        if not c.execute('SELECT 1 FROM articles WHERE id=?',(q.get('id'),)).fetchone():raise ValueError('资料不存在')
        return content.info(c,q['id'],refresh=True)
    if path=='/api/podcasts':return {'items':content.podcasts(q.get('q',''),radar.fetch,radar.parse_feed)}
    if path=='/api/podcast-preview':return content.preview(q.get('url',''),radar.fetch,radar.parse_feed,q.get('q',''))
    return None


def post(path,body,c,radar):
    if path=='/api/refresh-platform':return {'ok':True}
    if path=='/api/source-connection':
        row=c.execute('SELECT * FROM sources WHERE id=? AND deleted_at IS NULL',(body.get('source_id'),)).fetchone()
        if not row:raise ValueError('来源不存在')
        source=json.loads(row['config'])
        if body.get('disconnect'):
            c.execute('DELETE FROM source_connections WHERE source_id=?',(row['id'],));return {'ok':True}
        conn=native_client.call('/v1/connections',content.connection_for(source))
        c.execute('INSERT OR REPLACE INTO source_connections VALUES(?,?,?)',(row['id'],conn['id'],'rss-browser' if source.get('adapter')=='rss' and conn['platform']=='blog' else 'browser-auto'))
        return conn
    if path=='/api/platform-connection':
        action=body.get('action','login')
        cid=body.get('id')
        if not cid:
            platform=body.get('platform')
            if platform not in ('x','reddit'):raise ValueError('请选择来源来连接会员博客')
            conn=native_client.call('/v1/connections',{'platform':platform,'url':'https://x.com/home' if platform=='x' else 'https://www.reddit.com/'})
            cid=conn['id']
        if not isinstance(cid,str) or not cid.replace('-','').isalnum():raise ValueError('无效连接')
        if action not in ('login','confirm','pause','resume'):raise ValueError('无效操作')
        return native_client.call('/v1/connections/'+cid+'/'+action,{},timeout=80)
    if path=='/api/extract':return content.extract(c,body['id'])
    if path=='/api/transcription-cancel':
        row=content.info(c,body['id'])
        if not row['job_id']:raise ValueError('没有转写任务')
        return native_client.call('/v1/transcription-jobs/'+row['job_id']+'/cancel',{})
    if path=='/api/media-cleanup':return native_client.call('/v1/cache/cleanup',{})
    if path=='/api/opml':
        feeds=content.opml(body.get('text',''));results=[]
        tid=body.get('watch_id') or None
        if tid:watchlists.get(c,tid)
        for feed in feeds:
            try:
                s=interests.discover(feed['url'],radar.fetch,radar.parse_feed,radar.canonical,feed['url']);s['name']=feed['name']
                results.append(interests.register(c,s,feed['url'],radar.canonical,tid))
            except Exception as e:results.append({'url':feed['url'],'error':str(e)[:200]})
        return {'items':results}
    if path=='/api/wechat-source':
        include_all=body.get('include_all',True)
        if not isinstance(include_all,bool):raise ValueError('收录规则必须为布尔值')
        feed=body['feed_url'];raw=native_client.call('/v1/wechat/feed',{'url':feed})['feed'].encode()
        radar.parse_feed(raw)
        url=str(body.get('url') or '').strip()
        if not url:
            feed_id=urllib.parse.urlsplit(feed).path.rsplit('/',1)[-1].rsplit('.',1)[0]
            publisher=re.fullmatch(r'MP_WXS_(\d{4,20})',feed_id)
            if not publisher:raise ValueError('该订阅无法识别公众号，请补充一篇分享文章链接')
            biz=base64.b64encode(publisher[1].encode()).decode()
            url='https://mp.weixin.qq.com/mp/profile_ext?'+urllib.parse.urlencode({'action':'home','__biz':biz})
        url=interests.validate_public_url(url)
        if urllib.parse.urlsplit(url).hostname!='mp.weixin.qq.com':raise ValueError('请填写该公众号的一篇分享文章链接')
        s={'url':url,'name':str(body.get('name') or '微信公众号'),'adapter':'wechat-rss','kind':'公众号','platform':'wechat','bridge_feed':feed,'note':'本机 We-MP-RSS 缓存；上游授权及更新由公众号桥接管理'}
        return interests.register(c,s,url,radar.canonical,body.get('watch_id') or None,include_all)
    if path=='/api/read-article':
        article=c.execute('SELECT * FROM articles WHERE id=?',(body['id'],)).fetchone()
        if not article:raise ValueError('资料不存在')
        source=c.execute('SELECT config FROM sources WHERE id=?',(article['source_id'],)).fetchone()
        s=content.decorate(c,json.loads(source[0])) if source else {}
        if s.get('adapter') in ('browser-auto','rss-browser'):
            result=native_client.call('/v1/browser/collect',dict(s,url=article['url'],id='article-'+article['id']),timeout=180)
            if result['status']!='成功':raise ValueError(result['error'])
            row=result['rows'][0]
        else:
            from readable import extract
            text=extract(radar.fetch(article['url']).decode('utf-8','replace'))
            row=dict(body=text)
        content.store(c,article['id'],row)
        return content.info(c,article['id'])
    if path=='/api/import-link':
        from readable import extract, title
        url=interests.validate_public_url(body['url'],resolve=True)
        raw=radar.fetch(url).decode('utf-8','replace');text=extract(raw)
        s={'id':'manual-import','name':urllib.parse.urlsplit(url).hostname,'region':'全球','language':'未知','kind':'公众号' if 'mp.weixin.qq.com' in url else '博客'}
        row=dict(url=url,title=title(raw) or str(body.get('title') or url),excerpt=text[:1200],body=text)
        radar.put(c,s,row)
        aid=hashlib.sha256(radar.canonical(url).encode()).hexdigest()[:24]
        tid=body.get('watch_id') or 'ai';watchlists.get(c,tid)
        c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(aid,tid,'手动收录'))
        return {'id':aid,'added':1}
    return None


def upload(handler,c,aid):
    if not c.execute('SELECT 1 FROM articles WHERE id=?',(aid,)).fetchone():raise ValueError('资料不存在')
    size=int(handler.headers.get('Content-Length','0'))
    if size<=0 or size>513*1024*1024:raise ValueError('媒体不能超过512 MB')
    kind=handler.headers.get('Content-Type','')
    if not kind.startswith('multipart/form-data;'):raise ValueError('请使用媒体上传表单')
    target=urllib.parse.urlsplit(native_client.base())
    conn=http.client.HTTPConnection(target.hostname,target.port,timeout=180)
    try:
        conn.putrequest('POST','/v1/transcription-jobs')
        conn.putheader('Authorization','Bearer '+native_client.key());conn.putheader('Content-Type',kind);conn.putheader('Content-Length',str(size));conn.endheaders()
        remaining=size
        while remaining:
            chunk=handler.rfile.read(min(1024*1024,remaining))
            if not chunk:raise ValueError('上传被中断')
            conn.send(chunk);remaining-=len(chunk)
        response=conn.getresponse();result=json.loads(response.read(1_000_000))
        if response.status!=200:raise ValueError(result.get('detail','上传失败'))
        content.attach_job(c,aid,result);return result
    finally:conn.close()
