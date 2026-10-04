"""Archive ingestion and scrubbed snapshots with caller-supplied runtime helpers."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import content_store
import dedup
import reddit_quality
import semantic
import watchlists


def put(c, s, row, *, canonical, classify, now):
    url = canonical(row['url'])
    ident = hashlib.sha256(url.encode()).hexdigest()[:24]
    if reddit_quality.is_reddit(url) and s['id']!='manual-import':
        existing=c.execute('SELECT id FROM articles WHERE id=?',(ident,)).fetchone()
        if existing:
            decision=reddit_quality.record(c,ident,row,s)
        else:
            decision=reddit_quality.assess(row,s)
        if not decision['eligible']:return 0
    tags = classify(row['title'] + ' ' + row.get('excerpt', ''))
    result = c.execute('INSERT OR IGNORE INTO articles(id,url,title,excerpt,publisher,region,language,kind,topics,published_at,collected_at,source_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (ident,url,row['title'],row.get('excerpt',''),row.get('publisher') or s['name'],s['region'],s['language'],s['kind'],json.dumps(tags,ensure_ascii=False),row.get('published_at'),now(),s['id']))
    c.execute('INSERT INTO sightings VALUES(?,?,?) ON CONFLICT(article_id,source_id) DO UPDATE SET seen_at=excluded.seen_at', (ident,s['id'],now()))
    content_store.store(c,ident,row)
    if reddit_quality.is_reddit(url) and s['id']!='manual-import':reddit_quality.record(c,ident,row,s)
    annotation=c.execute('SELECT * FROM saved_annotations WHERE article_id=?',(ident,)).fetchone()
    if annotation:
        c.execute('UPDATE articles SET starred=?,note=?,review=? WHERE id=?',(annotation['starred'],annotation['note'],annotation['review'],ident))
        c.execute('DELETE FROM saved_annotations WHERE article_id=?',(ident,))
    watchlists.reindex_article(c,ident)
    dedup.index_article(c,ident)
    dirty=semantic.mark_dirty(c,ident)
    if dirty or result.rowcount:semantic.rebuild(c)
    return result.rowcount


def backup(connect, root):
    folder = Path(os.environ.get('RADAR_BACKUP_DIR',str(root/'backups')))
    folder.mkdir(parents=True,exist_ok=True)
    dest = folder / ('radar-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    with connect() as src, sqlite3.connect(dest) as out:
        src.backup(out)
        content_store.purge_reddit(out,all_content=True)
        out.commit()
        out.execute("VACUUM")
    return str(dest)
