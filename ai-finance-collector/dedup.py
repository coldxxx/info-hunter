"""Conservative news-index deduplication. Original records and annotations stay intact."""
import datetime as dt
import html
import re
import unicodedata
from urllib.parse import urlsplit

WINDOW = 24 * 60 * 60
GROUP_KEY = "COALESCE((SELECT group_id FROM semantic_members sm WHERE sm.article_id=articles.id),(SELECT group_id FROM article_duplicates d WHERE d.article_id=articles.id),articles.id)"


def index_link(a):
    return urlsplit(a['url']).hostname == 'news.google.com'


def text_key(value):
    value = unicodedata.normalize('NFKC', html.unescape(value or '')).casefold()
    return re.sub(r'\s+', ' ', value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))).strip()


def title_key(a):
    title = text_key(a['title'])
    # Only strip the publisher explicitly supplied by an index, not arbitrary subtitles.
    publisher = text_key(a.get('publisher'))
    if index_link(a) and publisher:
        title = re.sub(r'\s+[-–—|]\s*' + re.escape(publisher) + r'$', '', title).strip()
    return title if len(re.sub(r'\W', '', title)) >= 18 else ''


def publisher_keys(a):
    def key(s):
        return re.sub(r'\W', '', re.sub(r'^the\s+', '', text_key(s)))
    values = {key(a.get('publisher'))}
    if not index_link(a):
        host = (urlsplit(a['url']).hostname or '').removeprefix('www.')
        values.add(key(host))
        values.add(key(re.sub(r'\.(com|org|net|io|dev)$', '', host)))
    return values - {''}


def timestamp(a):
    try:
        t = dt.datetime.fromisoformat(a['published_at'].replace('Z', '+00:00'))
        return t.timestamp() if t.tzinfo else None
    except (ValueError, TypeError, AttributeError, KeyError):
        return None


def same_article(a, b):
    if not (index_link(a) or index_link(b)):
        return False
    if a.get('kind') in ('论坛', '视频', '播客', '博客/播客') or b.get('kind') in ('论坛', '视频', '播客', '博客/播客'):
        return False
    languages = [text_key(x.get('language')).split('-')[0] for x in (a, b)]
    if not all(languages) or languages[0] != languages[1] or languages[0] == '未知':
        return False
    ta, tb = timestamp(a), timestamp(b)
    return bool(title_key(a) and title_key(a) == title_key(b)
                and publisher_keys(a) & publisher_keys(b)
                and ta is not None and tb is not None and abs(ta - tb) <= WINDOW)


def priority(a):
    return int(not index_link(a)) * 10000 + min(len(a.get('excerpt') or ''), 2000)


def index_article(c, article_id):
    if c.execute('SELECT 1 FROM article_duplicates WHERE article_id=?', (article_id,)).fetchone():
        return
    a = dict(c.execute('SELECT * FROM articles WHERE id=?', (article_id,)).fetchone())
    key = title_key(a)
    groups = []
    if key:
        candidates = c.execute('SELECT articles.*,d.group_id FROM article_duplicates d JOIN articles ON articles.id=d.article_id WHERE d.title_key=? ORDER BY d.group_id', (key,)).fetchall()
        for b in candidates:
            if same_article(a, dict(b)) and b['group_id'] not in groups:
                groups.append(b['group_id'])
    target = article_id
    oldest = newest = timestamp(a)
    # Bound the entire cluster; repeated daily headlines must not form a time chain.
    for group in groups:
        times = [timestamp(dict(x)) for x in c.execute('SELECT articles.* FROM article_duplicates d JOIN articles ON articles.id=d.article_id WHERE d.group_id=?', (group,))]
        if any(t is None for t in times):
            continue
        lo, hi = min([oldest] + times), max([newest] + times)
        if hi - lo > WINDOW:
            continue
        if target == article_id:
            target = group
        else:
            c.execute('UPDATE article_duplicates SET group_id=? WHERE group_id=?', (target, group))
        oldest, newest = lo, hi
    c.execute('INSERT INTO article_duplicates VALUES(?,?,?,?)', (article_id, target, key, priority(a)))


def bootstrap(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS article_duplicates(article_id TEXT PRIMARY KEY,group_id TEXT NOT NULL,title_key TEXT NOT NULL,priority INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS duplicate_title ON article_duplicates(title_key);
    CREATE INDEX IF NOT EXISTS duplicate_group ON article_duplicates(group_id);
    ''')
    for row in c.execute('SELECT id FROM articles WHERE id NOT IN (SELECT article_id FROM article_duplicates) ORDER BY collected_at,id').fetchall():
        index_article(c, row[0])


def count(c, clause='', args=(), raw=False):
    if raw:return c.execute('SELECT count(*) FROM articles'+clause,args).fetchone()[0]
    return c.execute('SELECT count(DISTINCT ' + GROUP_KEY + ') FROM articles' + clause, args).fetchone()[0]


def page(c, clause, args, offset, raw=False):
    if raw:
        return c.execute('SELECT articles.*,'+GROUP_KEY+' AS duplicate_group FROM articles'+clause+' ORDER BY COALESCE(published_at,collected_at) DESC,id LIMIT 50 OFFSET ?',list(args)+[offset]).fetchall()
    # Filter first, group second, paginate last: favorites/search/topic/source filters
    # retain matching copies even if their preferred original is outside the filter.
    sql = '''WITH matching AS (
        SELECT articles.*,''' + GROUP_KEY + ''' AS duplicate_group,
          COALESCE((SELECT priority FROM article_duplicates d WHERE d.article_id=articles.id),0) AS duplicate_priority
        FROM articles''' + clause + '''), ranked AS (
        SELECT *,ROW_NUMBER() OVER (PARTITION BY duplicate_group ORDER BY
          starred DESC,(note!='' OR review!='未核验') DESC,duplicate_priority DESC,id) AS duplicate_rank
        FROM matching)
        SELECT * FROM ranked WHERE duplicate_rank=1
        ORDER BY COALESCE(published_at,collected_at) DESC,id LIMIT 50 OFFSET ?'''
    return c.execute(sql, list(args) + [offset]).fetchall()


def versions(c, group, topic_id=None):
    sql = 'SELECT articles.* FROM articles LEFT JOIN article_duplicates d ON d.article_id=articles.id WHERE '+GROUP_KEY+'=?'
    args = [group]
    if topic_id:
        sql += ' AND EXISTS(SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)'
        args.append(topic_id)
    return c.execute(sql + ' ORDER BY d.priority DESC,articles.id', args).fetchall()
