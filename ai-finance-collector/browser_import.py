"""Import small, reviewed batches of visible social posts; no network or credentials."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
import radar

HOSTS = {'reddit-local': {'www.reddit.com', 'reddit.com'},
         'reddit-stocks': {'www.reddit.com', 'reddit.com'},
         'x-ai': {'x.com', 'www.x.com', 'twitter.com'},
         'xueqiu': {'xueqiu.com', 'www.xueqiu.com'}}


def import_batch(source_id, rows):
    sources = json.loads((radar.ROOT / 'sources.json').read_text())
    if source_id not in HOSTS:
        raise ValueError('不支持的浏览器来源')
    source = next(s for s in sources if s['id'] == source_id)
    with radar.connect() as c:
        if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(source_id,)).fetchone():
            raise ValueError('来源已删除，请重新添加后再导入')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError('每批需要 1–50 条帖子')
    validated = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('帖子必须是对象')
        url = radar.canonical(str(row.get('url', '')))
        parsed = urlsplit(url)
        if parsed.hostname not in HOSTS[source_id] or parsed.scheme != 'https':
            raise ValueError('链接必须属于所选平台并使用 HTTPS')
        title = str(row.get('title', '')).strip()
        author = str(row.get('author', '')).strip()
        if not title or not author:
            raise ValueError('必须提供标题与页面可见作者')
        published = radar.date(row.get('published_at'))
        if row.get('published_at') and not published:
            raise ValueError('发布时间无效；页面未显示时留空，不要推测')
        validated.append(dict(url=url, title=title[:500],
                              publisher=source['name'] + ' · ' + author[:200],
                              excerpt=str(row.get('excerpt', ''))[:1200],
                              published_at=published))
    radar.init()
    with radar.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(source_id,)).fetchone():
            raise ValueError('来源已删除，请重新添加后再导入')
        added = sum(radar.put(c, source, row) for row in validated)
        c.execute('UPDATE sources SET status=?, checked_at=?, success_at=?, error=?, last_count=? WHERE id=?',
                  ('样本已入库', radar.now(), radar.now(), '浏览器辅助批次；不代表完整覆盖或自动接通', len(validated), source_id))
    return {'added': added, 'duplicates': len(validated) - added, 'backup': radar.backup()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, choices=HOSTS)
    parser.add_argument('file', type=Path, help='UTF-8 JSON array of reviewed visible posts')
    args = parser.parse_args()
    print(json.dumps(import_batch(args.source, json.loads(args.file.read_text())), ensure_ascii=False))
