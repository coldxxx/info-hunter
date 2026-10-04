"""Collection orchestration with caller-supplied runtime paths and entry points."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import urllib.error

import content_store
import interests
import translation
import watchlists


def collect(only=None, scheduled=False, topic_id=None, *, db, lock, connect, now, collect_source, put, canonical, backup):
    if not lock.acquire(blocking=False):
        return {'busy': True}
    process_lock = (db.parent / 'collector.lock').open('a')
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
        lock.release()
