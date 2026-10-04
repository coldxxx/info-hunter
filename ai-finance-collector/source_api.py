"""Source-library and watch-topic routes, independent of the HTTP handler."""
from __future__ import annotations

import json

from api_contracts import RouteResult, SourceServices
import content_store
import interests
import native_client
import social
import source_details
import source_lifecycle
import watchlists


def get(path, q, c) -> RouteResult | None:
    if path == '/api/watch-topics':
        return RouteResult(watchlists.listing(c))
    if path == '/api/sources':
        rows=[];tid=q.get('watch_id')
        connections=social.settings()
        native_connections=native_client.snapshot() if c.execute('SELECT 1 FROM source_connections LIMIT 1').fetchone() else {}
        topics={t['id']:t for t in watchlists.configs(c)}
        if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return RouteResult({'error':'主题不存在'},404)
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
        return RouteResult(sorted(rows,key=lambda r:-r['preference']['score']))
    if path == '/api/source-detail':
        tid=q.get('watch_id') or None
        if tid and not c.execute('SELECT 1 FROM watch_topics WHERE id=?',(tid,)).fetchone():return RouteResult({'error':'主题不存在'},404)
        row=c.execute('SELECT * FROM sources WHERE id=? AND deleted_at IS NULL',(q.get('id',''),)).fetchone()
        if not row:return RouteResult({'error':'来源不存在'},404)
        return RouteResult(source_details.describe(c,dict(row),tid))
    if path == '/api/connections':
        return RouteResult(social.connection_status())
    return None


def post(path, body, connect, services: SourceServices) -> RouteResult | None:
    if path == '/api/watch-topic':
        with connect() as c:result=watchlists.save(c,body)
        return RouteResult(result)
    if path == '/api/watch-source':
        tid=body['watch_id'];sid=body['source_id']
        if not isinstance(body.get('include_all',False),bool):raise ValueError('include_all须为布尔值')
        if not isinstance(body.get('follow',True),bool):raise ValueError('follow须为布尔值')
        with connect() as c:
            watchlists.get(c,tid)
            if body.get('follow',True):watchlists.bind(c,tid,sid,body.get('include_all',False))
            else:c.execute('DELETE FROM watch_sources WHERE topic_id=? AND source_id=?',(tid,sid))
            watchlists.reindex(c,tid)
        return RouteResult({'ok':True})
    if path == '/api/watch-sources':
        if not isinstance(body.get('include_all',False),bool):raise ValueError('include_all须为布尔值')
        with connect() as c:result=watchlists.bind_many(c,body['watch_id'],body.get('source_ids'),body.get('include_all',False))
        return RouteResult(result)
    if path == '/api/source':
        if not isinstance(body.get('include_all',True),bool):raise ValueError('include_all须为布尔值')
        if body.get('watch_id') is not None and not isinstance(body['watch_id'],str):raise ValueError('无效的主题')
        url=services.canonical(str(body['url']).strip())
        learned=interests.discover(url,services.fetch,services.parse_feed,services.canonical,body.get('feed_url') or None)
        if str(body.get('name','')).strip():learned['name']=str(body['name']).strip()[:200]
        with connect() as c:result=interests.register(c,learned,url,services.canonical,body.get('watch_id','ai') or None,body.get('include_all',True))
        return RouteResult(result)
    if path == '/api/source-delete':
        with connect() as c:result=source_lifecycle.delete(c,body.get('source_id'))
        return RouteResult(result)
    if path == '/api/source-feedback':
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
        return RouteResult(result)
    return None
