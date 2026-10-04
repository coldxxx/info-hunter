"""Explainable Reddit candidate gate; discussion volume alone is not evidence."""
import html
import json
import re
import time
from urllib.parse import urlsplit

VERSION = 1
MIN_COMMENTS = 10
HOSTS = {'reddit.com', 'www.reddit.com', 'old.reddit.com', 'oauth.reddit.com'}
# Personal annotations and explicit manual imports remain available in every view.
VISIBLE = "(NOT EXISTS (SELECT 1 FROM article_quality aq WHERE aq.article_id=articles.id AND aq.eligible=0) OR articles.starred=1 OR articles.note<>'' OR articles.review<>'未核验' OR articles.source_id='manual-import')"


def is_reddit(url):
    return (urlsplit(url or '').hostname or '').lower() in HOSTS


def comment_count(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?|[0-9]{1,3}(?:,[0-9]{3})+)\s*([km]?)\s*(?:comments?|条评论)?\s*', value, re.I)
    if not match:
        return None
    number = float(match[1].replace(',', '')) * {'': 1, 'k': 1000, 'm': 1000000}[match[2].lower()]
    return int(number) if number.is_integer() else None


def assess(row, source=None):
    source = source or {}
    minimum = source.get('reddit_min_comments', MIN_COMMENTS)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= 1000:
        minimum = MIN_COMMENTS
    count = comment_count(row.get('comment_count'))
    title = str(row.get('title') or '')
    body = html.unescape(re.sub(r'<[^>]+>', ' ', str(row.get('body') or row.get('excerpt') or '')))
    if any(s in body for s in ('仅保存列表标题', '未读取正文')) or body.strip() in ('[deleted]', '[removed]'):
        body = ''
    # Links and repeated words do not pad the substantive-text threshold.
    plain = re.sub(r'https?://\S+', ' ', body)
    plain = re.sub(r'\s+', ' ', plain).strip()
    words = re.findall(r'[a-zA-Z]+', plain.lower())
    varied = len(set(words)) >= 30 or len(set(re.findall(r'[\u3400-\u9fff]', plain))) >= 60
    substantive = len(plain) >= 240 and varied
    quantitative = bool(re.search(r'\d+(?:\.\d+)?\s*(?:%|ms\b|s\b|tokens?\b|t/s\b|gb\b|tb\b|倍|亿|万|秒|美元|billion\b|million\b)', plain, re.I))
    method = bool(re.search(r'\b(?:benchmark|dataset|ablation|latency|throughput|quantization|measured|tested|reproduce|implementation|profiling|revenue|earnings|capex|filing)\b|评测|基准|数据集|量化|延迟|吞吐|实测|复现|实现|营收|业绩|财报|资本开支', plain, re.I))
    resource = False
    urls = [str(row.get('outbound_url') or '')] + re.findall(r'https?://[^\s<>\)\]]+', body)
    for url in urls:
        p = urlsplit(url)
        host = (p.hostname or '').lower().removeprefix('www.')
        # A bare domain or arbitrary promotional link does not establish substance.
        if p.scheme == 'https' and host in {'github.com', 'huggingface.co', 'arxiv.org', 'openreview.net', 'aclanthology.org'} and len(p.path.strip('/').split('/')) >= 2:
            resource = True
    flair = str(row.get('flair') or '')
    low_value = bool(re.search(r'\b(?:meme|memes|humor|humour|shitpost|satire)\b|梗图|搞笑|讽刺', flair, re.I))
    evidence = [name for name, present in [('数据', quantitative), ('方法或产业细节', method), ('代码或论文', resource)] if present]
    eligible, reason = False, '主帖信息不足：需要具体数据、方法或代码/论文线索'
    if low_value:
        reason = '娱乐或讽刺内容'
    elif resource and ((substantive and (method or quantitative)) or (len(title) >= 40 and bool(re.search(r'\b(?:benchmark|dataset|model|agent|inference|quantization|paper|release)\b|评测|数据集|模型|论文|推理|发布', title, re.I)))):
        eligible, reason = True, '代码或论文一手线索'
    elif substantive and quantitative and method and len(plain) >= 600:
        eligible, reason = True, '详细数据与方法，低评论量例外'
    elif substantive and evidence:
        if count is not None and count >= minimum:
            eligible, reason = True, f'主帖有具体内容，评论数达到 {minimum}'
        else:
            reason = ('评论数未知' if count is None else f'评论数 {count} 低于 {minimum}') + '，未达到实质内容例外'
    return dict(eligible=eligible, reason=reason, comment_count=count, evidence=evidence, version=VERSION)


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS article_quality(
        article_id TEXT PRIMARY KEY, eligible INTEGER NOT NULL, reason TEXT NOT NULL,
        comment_count INTEGER, outbound_url TEXT, flair TEXT, evidence TEXT,
        version INTEGER NOT NULL, assessed_at REAL NOT NULL)''')


def record(c, aid, row, source=None):
    row = dict(row)
    if not row.get('body'):
        content = c.execute('SELECT body FROM article_content WHERE article_id=?', (aid,)).fetchone()
        if content:row['body'] = content[0]
    decision = assess(row, source)
    previous = c.execute('SELECT comment_count,outbound_url,flair FROM article_quality WHERE article_id=?', (aid,)).fetchone()
    if previous:
        # A partial list response is unknown, not a reset to zero or empty metadata.
        row = dict(row)
        for key, value in zip(('comment_count', 'outbound_url', 'flair'), previous):
            if row.get(key) is None or row.get(key) == '':
                row[key] = value
        decision = assess(row, source)
    c.execute('INSERT OR REPLACE INTO article_quality VALUES(?,?,?,?,?,?,?,?,?)',
              (aid, int(decision['eligible']), decision['reason'], decision['comment_count'],
               row.get('outbound_url'), row.get('flair'), json.dumps(decision['evidence'], ensure_ascii=False), VERSION, time.time()))
    return decision


def bootstrap(c):
    schema(c)
    # Reassess old candidates once without editing provider text or topic bindings.
    rows = c.execute('''SELECT a.*,ac.body FROM articles a LEFT JOIN article_content ac ON ac.article_id=a.id
        LEFT JOIN article_quality aq ON aq.article_id=a.id WHERE aq.article_id IS NULL OR aq.version<>?''', (VERSION,)).fetchall()
    for raw in rows:
        row = dict(raw)
        if is_reddit(row['url']) and row['source_id'] != 'manual-import':
            saved = c.execute('SELECT config FROM sources WHERE id=?', (row['source_id'],)).fetchone()
            record(c, row['id'], row, json.loads(saved[0]) if saved else {})
