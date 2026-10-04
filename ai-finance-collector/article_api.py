"""Article queries, annotations and imports, independent of the HTTP handler."""
from __future__ import annotations

import hashlib
import json

from api_contracts import ArticleServices, RouteResult
import content_store
import dedup
import engineering
import interests
import reddit_quality
import translation
import watchlists


def get(path, q, c) -> RouteResult | None:
    if path == '/api/articles':
        where, args = [], []
        if not q.get('id'):where.append(reddit_quality.VISIBLE)
        if q.get('id'):
            where.append('id=?');args.append(q['id'])
        if q.get('watch_id'):
            if not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(q['watch_id'],)).fetchone():return RouteResult({'error':'主题不存在'},404)
            where.append('EXISTS (SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)');args.append(q['watch_id'])
        if q.get('engineering_category'):
            if not q.get('watch_id') or watchlists.get(c,q['watch_id']).get('content_profile')!='developer':return RouteResult({'error':'技术方向仅用于开发者主题'},400)
            category=q['engineering_category']
            if category not in engineering.CATEGORIES+['手动收录']:return RouteResult({'error':'无效的技术方向'},400)
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
            return RouteResult({'error':'无效分页'},400)
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
        return RouteResult({'total':total,'items':items})
    return None


def post(path, body, connect, services: ArticleServices) -> RouteResult | None:
    if path == '/api/article':
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
        return RouteResult({'ok':True})
    if path == '/api/import':
        if not str(body.get('title','')).strip():
            raise ValueError('标题不能为空')
        s = {'id':'manual-import','name':body.get('publisher','手动录入'),'region':body.get('region','全球'),'language':body.get('language','未知'),'kind':body.get('kind','研报')}
        body['published_at'] = services.date(body.get('published_at'))
        body['excerpt'] = str(body.get('excerpt',''))[:20000]
        with connect() as c:
            tid=body.get('watch_id') or 'ai';watchlists.get(c,tid)
            added = services.put(c,s,body)
            aid=hashlib.sha256(services.canonical(body['url']).encode()).hexdigest()[:24]
            c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(aid,tid,'手动收录'))
        return RouteResult({'added':added})
    return None
