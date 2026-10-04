"""Durable semantic relation review, reversible grouping, and incremental model jobs."""
import array
import datetime as dt
import fcntl
import hashlib
import json
import math
import threading
import time
from pathlib import Path
import dedup
import semantic_models as models
import semantic_worker

WORKERS = {}
WORKER_LOCK = threading.Lock()
LABEL_MATCH = '''((l.left_id=p.left_id AND l.right_id=p.right_id AND l.left_fp=p.left_fp AND l.right_fp=p.right_fp)
 OR (l.left_id=p.right_id AND l.right_id=p.left_id AND l.left_fp=p.right_fp AND l.right_fp=p.left_fp))'''


def schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS semantic_settings(id INTEGER PRIMARY KEY CHECK(id=1),config TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_jobs(article_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,profile TEXT NOT NULL,status TEXT NOT NULL,phase TEXT NOT NULL DEFAULT 'embed',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_vectors(article_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,model_key TEXT NOT NULL,dimensions INTEGER NOT NULL,vector BLOB NOT NULL,updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_pairs(id TEXT PRIMARY KEY,left_id TEXT NOT NULL,right_id TEXT NOT NULL,left_fp TEXT NOT NULL,right_fp TEXT NOT NULL,profile TEXT NOT NULL,similarity REAL NOT NULL,relation TEXT NOT NULL,decision TEXT NOT NULL,model TEXT NOT NULL,status TEXT NOT NULL,updated_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS semantic_pair_status ON semantic_pairs(status,updated_at);
    CREATE TABLE IF NOT EXISTS semantic_labels(pair_id TEXT PRIMARY KEY,left_id TEXT NOT NULL,right_id TEXT NOT NULL,left_fp TEXT NOT NULL,right_fp TEXT NOT NULL,relation TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_blocks(pair_id TEXT PRIMARY KEY,left_id TEXT NOT NULL,right_id TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_members(article_id TEXT PRIMARY KEY,group_id TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS semantic_member_group ON semantic_members(group_id);
    CREATE TABLE IF NOT EXISTS semantic_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,target TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,created_at REAL NOT NULL,undone_by INTEGER);
    CREATE TABLE IF NOT EXISTS semantic_evaluations(id INTEGER PRIMARY KEY AUTOINCREMENT,profile TEXT NOT NULL,report TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_calls(id INTEGER PRIMARY KEY AUTOINCREMENT,profile TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_migrations(name TEXT PRIMARY KEY);
    ''')
    c.execute('INSERT OR IGNORE INTO semantic_settings VALUES(1,?)', (json.dumps(models.DEFAULTS),))
    if not c.execute("SELECT 1 FROM semantic_migrations WHERE name='model-side-order-v1'").fetchone():
        c.execute("UPDATE semantic_pairs AS p SET status='stale' WHERE NOT EXISTS(SELECT 1 FROM semantic_labels l WHERE l.pair_id=p.id AND " + LABEL_MATCH + ')')
        c.execute("UPDATE semantic_jobs SET status='queued',attempts=0,next_at=0,error='' WHERE phase='judge'")
        c.execute("INSERT INTO semantic_migrations VALUES('model-side-order-v1')")


def settings(c):
    return models.DEFAULTS | json.loads(c.execute('SELECT config FROM semantic_settings WHERE id=1').fetchone()[0])


def configure(c, values):
    old = settings(c)
    if not isinstance(values, dict) or set(values) - set(models.DEFAULTS):
        raise ValueError('无效的语义去重配置')
    config = old | values
    if type(config['enabled']) is not bool or config['mode'] not in ('review', 'auto'):
        raise ValueError('无效运行模式')
    for key in ('embedding_model', 'judge_model'):
        if not isinstance(config[key], str) or not config[key].strip() or len(config[key]) > 200:
            raise ValueError('请填写有效模型标识')
    for key in ('embedding_url', 'judge_url'):
        if not isinstance(config[key], str):
            raise ValueError('无效模型地址')
        models.endpoint(config[key])
    for key in ('candidate_threshold', 'auto_threshold'):
        if type(config[key]) not in (float, int) or not math.isfinite(config[key]) or not 0 <= config[key] <= 1:
            raise ValueError('阈值必须在0到1之间')
    for key, limit in (('top_k', 20), ('window_days', 90), ('daily_pair_limit', 5000)):
        if type(config[key]) is not int or not 1 <= config[key] <= limit:
            raise ValueError('无效的候选范围或处理预算')
    if config['mode'] == 'auto' and not auto_gate(c, config)['ready']:
        raise ValueError('自动折叠尚未通过当前模型的标注样本验证，请先使用人工复核模式')
    c.execute('UPDATE semantic_settings SET config=? WHERE id=1', (json.dumps(config),))
    if models.profile(old) != models.profile(config):
        c.execute("UPDATE semantic_pairs AS p SET status='stale' WHERE NOT EXISTS(SELECT 1 FROM semantic_labels l WHERE l.pair_id=p.id AND " + LABEL_MATCH + ')')
        rebuild(c)
    return config


def document(c, aid):
    r = c.execute("SELECT a.*,COALESCE(ac.body,'') AS body FROM articles a LEFT JOIN article_content ac ON ac.article_id=a.id WHERE a.id=?", (aid,)).fetchone()
    return dict(r) if r else None


def fingerprint(a):
    return hashlib.sha256(json.dumps([a.get(k) for k in ('title', 'excerpt', 'body', 'publisher', 'published_at', 'kind', 'language')], ensure_ascii=False).encode()).hexdigest()


def pair_id(a, b):
    return hashlib.sha256('|'.join(sorted((a, b))).encode()).hexdigest()[:32]


def current(c, p):
    a, b = document(c, p['left_id']), document(c, p['right_id'])
    return bool(a and b and fingerprint(a) == p['left_fp'] and fingerprint(b) == p['right_fp'])


def mark_dirty(c, aid, force=False):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_jobs'").fetchone():
        return False
    a = document(c, aid)
    if not a:
        return False
    fp, key = fingerprint(a), models.profile(settings(c))
    old = c.execute('SELECT fingerprint,profile FROM semantic_jobs WHERE article_id=?', (aid,)).fetchone()
    if not force and old and tuple(old) == (fp, key):
        return False
    c.execute("INSERT INTO semantic_jobs(article_id,fingerprint,profile,status,updated_at) VALUES(?,?,?,'queued',?) ON CONFLICT(article_id) DO UPDATE SET fingerprint=excluded.fingerprint,profile=excluded.profile,status='queued',phase='embed',attempts=0,next_at=0,error='',updated_at=excluded.updated_at", (aid, fp, key, time.time()))
    c.execute("UPDATE semantic_pairs SET status='stale' WHERE (left_id=? AND left_fp<>?) OR (right_id=? AND right_fp<>?)", (aid, fp, aid, fp))
    return True


def enqueue(c, topic_id=None, force=False):
    args = []
    clause = ''
    if topic_id:
        clause = ' WHERE EXISTS(SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)'
        args = [topic_id]
    count = sum(mark_dirty(c, r[0], force) for r in c.execute('SELECT id FROM articles' + clause, args).fetchall())
    rebuild(c)
    return count


def rebuild(c):
    """Original URL/title groups plus reviewed edges; automatic edges use complete linkage."""
    ids = [r[0] for r in c.execute('SELECT id FROM articles')]
    parent = {i: i for i in ids}
    members = {i: {i} for i in ids}
    blocked = {frozenset((r[0], r[1])) for r in c.execute('SELECT left_id,right_id FROM semantic_blocks')}
    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def join(a, b, allowed=None):
        if a not in parent or b not in parent:
            return
        x, y = root(a), root(b)
        if x == y:
            return
        cross = [frozenset((i, j)) for i in members[x] for j in members[y]]
        if any(p in blocked for p in cross) or (allowed is not None and any(p not in allowed for p in cross)):
            return
        parent[y] = x
        members[x] |= members.pop(y)
    baseline = {}
    for aid, group in c.execute('SELECT article_id,group_id FROM article_duplicates ORDER BY group_id,article_id'):
        if aid in parent:
            baseline.setdefault(group, []).append(aid)
    for group in baseline.values():
        # Respect explicit separation even within an old deterministic group.
        for i, aid in enumerate(group):
            for other in group[:i]:
                join(other, aid)
    allowed = {frozenset((i, j)) for group in members.values() for i in group for j in group if i != j}
    for label in c.execute("SELECT * FROM semantic_labels WHERE relation='duplicate'"):
        if current(c, label):
            join(label['left_id'], label['right_id'])
            allowed.add(frozenset((label['left_id'], label['right_id'])))
    automatic = [dict(r) for r in c.execute("SELECT * FROM semantic_pairs WHERE status='auto' AND relation='duplicate'") if current(c, r)]
    allowed |= {frozenset((r['left_id'], r['right_id'])) for r in automatic}
    for p in automatic:
        join(p['left_id'], p['right_id'], allowed)
    c.execute('DELETE FROM semantic_members')
    c.executemany('INSERT INTO semantic_members VALUES(?,?)', [(i, root(i)) for i in ids])


def remove(c, aid):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_jobs'").fetchone():
        return
    for table in ('semantic_jobs', 'semantic_vectors', 'semantic_members'):
        c.execute('DELETE FROM ' + table + ' WHERE article_id=?', (aid,))
    for table in ('semantic_pairs', 'semantic_labels', 'semantic_blocks'):
        c.execute('DELETE FROM ' + table + ' WHERE left_id=? OR right_id=?', (aid, aid))


def snapshot(c, targets):
    return {pid: {'label': dict(r) if (r := c.execute('SELECT * FROM semantic_labels WHERE pair_id=?', (pid,)).fetchone()) else None,
                  'block': dict(r) if (r := c.execute('SELECT * FROM semantic_blocks WHERE pair_id=?', (pid,)).fetchone()) else None}
            for pid in targets}


def audit(c, action, target, before, after):
    return c.execute('INSERT INTO semantic_audit(action,target,before_state,after_state,created_at) VALUES(?,?,?,?,?)',
        (action, target, json.dumps(before), json.dumps(after), time.time())).lastrowid


def review(c, pid, relation, note='', expected=None):
    if relation not in models.RELATIONS or not isinstance(note, str) or len(note) > 1000:
        raise ValueError('无效复核结果或备注')
    p = c.execute('SELECT * FROM semantic_pairs WHERE id=?', (pid,)).fetchone()
    if not p or not current(c, p):
        raise ValueError('资料或正文已变化，请重新分析后复核')
    if expected is not None and expected != p['updated_at']:
        raise ValueError('该判断已更新，请刷新后复核')
    before = snapshot(c, [pid])
    if relation == 'duplicate':
        # Manual confirmation explicitly joins the two shown groups; remove ONLY this pair's separation.
        c.execute('DELETE FROM semantic_blocks WHERE pair_id=?', (pid,))
    else:
        c.execute('INSERT OR REPLACE INTO semantic_blocks VALUES(?,?,?)', (pid, p['left_id'], p['right_id']))
    c.execute('INSERT OR REPLACE INTO semantic_labels VALUES(?,?,?,?,?,?,?,?)',
        (pid, p['left_id'], p['right_id'], p['left_fp'], p['right_fp'], relation, note, time.time()))
    rebuild(c)
    if relation == 'duplicate':
        groups = [r[0] for r in c.execute('SELECT group_id FROM semantic_members WHERE article_id IN (?,?)', (p['left_id'], p['right_id']))]
        if len(set(groups)) != 1:
            # A different split decision has precedence. Transaction is rolled back by the API.
            raise ValueError('组内存在已确认的拆分，请先撤销对应拆分记录')
    event = audit(c, 'review', pid, before, snapshot(c, [pid]))
    return {'ok': True, 'event_id': event}


def split(c, aid):
    r = c.execute('SELECT group_id FROM semantic_members WHERE article_id=?', (aid,)).fetchone()
    if not r:
        raise ValueError('资料不存在')
    other = [r[0] for r in c.execute('SELECT article_id FROM semantic_members WHERE group_id=? AND article_id<>?', (r[0], aid))]
    targets = [pair_id(aid, b) for b in other]
    before = snapshot(c, targets)
    for b, pid in zip(other, targets):
        left, right = sorted((aid, b))
        c.execute('INSERT OR REPLACE INTO semantic_blocks VALUES(?,?,?)', (pid, left, right))
    rebuild(c)
    event = audit(c, 'split', aid, before, snapshot(c, targets))
    return {'ok': True, 'separated': len(other), 'event_id': event}


def undo(c, event_id):
    event = c.execute('SELECT * FROM semantic_audit WHERE id=?', (event_id,)).fetchone()
    if not event or event['undone_by'] or event['action'] == 'undo':
        raise ValueError('该操作不存在或已撤销')
    after, before = json.loads(event['after_state']), json.loads(event['before_state'])
    for state in list(before.values()) + list(after.values()):
        for row in (state['label'], state['block']):
            if row and (not document(c, row['left_id']) or not document(c, row['right_id'])):
                raise ValueError('资料已被清理，该历史操作无法撤销')
    if snapshot(c, list(after)) != after:
        raise ValueError('这些资料已有后续复核，请先撤销后续操作')
    for pid, state in before.items():
        c.execute('DELETE FROM semantic_labels WHERE pair_id=?', (pid,))
        c.execute('DELETE FROM semantic_blocks WHERE pair_id=?', (pid,))
        if state['label']:
            c.execute('INSERT INTO semantic_labels VALUES(?,?,?,?,?,?,?,?)', tuple(state['label'].values()))
        if state['block']:
            c.execute('INSERT INTO semantic_blocks VALUES(?,?,?)', tuple(state['block'].values()))
    rebuild(c)
    new_id = audit(c, 'undo', str(event_id), after, before)
    c.execute('UPDATE semantic_audit SET undone_by=? WHERE id=?', (new_id, event_id))
    return {'ok': True}


def auto_gate(c, config):
    r = c.execute('SELECT report FROM semantic_evaluations WHERE profile=? ORDER BY id DESC LIMIT 1', (models.profile(config),)).fetchone()
    report = json.loads(r[0]) if r else {}
    ready = (report.get('count', 0) >= 100 and report.get('negatives', 0) >= 50
             and report.get('precision', 0) >= 0.99 and report.get('recall', 0) >= 0.80)
    return {'ready': ready, 'report': report, 'requirement': '当前模型至少100对独立标注样本，含50对非重复；重复精确率≥99%，召回率≥80%'}


def status(c):
    config = settings(c)
    jobs = {r[0]: r[1] for r in c.execute('SELECT status,count(*) FROM semantic_jobs GROUP BY status')}
    counts = {r[0]: r[1] for r in c.execute("SELECT relation,count(*) FROM semantic_pairs WHERE status<>'stale' GROUP BY relation")}
    reviewed = c.execute('SELECT count(*) FROM semantic_labels l JOIN semantic_jobs ja ON ja.article_id=l.left_id JOIN semantic_jobs jb ON jb.article_id=l.right_id WHERE ja.fingerprint=l.left_fp AND jb.fingerprint=l.right_fp').fetchone()[0]
    awaiting = c.execute("SELECT count(*) FROM semantic_pairs p WHERE status='suggested' AND NOT EXISTS(SELECT 1 FROM semantic_labels l WHERE l.pair_id=p.id AND " + LABEL_MATCH + ')').fetchone()[0]
    latest_error = c.execute("SELECT error FROM semantic_jobs WHERE error<>'' ORDER BY updated_at DESC LIMIT 1").fetchone()
    events = [dict(r) for r in c.execute('SELECT id,action,target,created_at,undone_by FROM semantic_audit ORDER BY id DESC LIMIT 15')]
    collapsed = c.execute('SELECT count(*)-count(DISTINCT group_id) FROM semantic_members').fetchone()[0]
    calls = [r[0] for r in c.execute('SELECT created_at FROM semantic_calls WHERE created_at>=? ORDER BY created_at', (time.time() - 86400,))]
    budget = dict(used=len(calls), limit=config['daily_pair_limit'],
                  resumes_at=calls[len(calls)-config['daily_pair_limit']] + 86400 if len(calls) >= config['daily_pair_limit'] else None)
    index = dict(total=c.execute('SELECT count(*) FROM articles').fetchone()[0],
                 indexed=c.execute('SELECT count(*) FROM semantic_vectors v JOIN semantic_jobs j ON j.article_id=v.article_id WHERE v.fingerprint=j.fingerprint AND v.model_key=?', (models.embedding_key(config),)).fetchone()[0])
    return dict(config=config, jobs=jobs, relations=counts, reviewed=reviewed, awaiting=awaiting,
                collapsed=collapsed, last_error=latest_error[0] if latest_error else '', events=events,
                auto_gate=auto_gate(c, config), policy=models.POLICY, budget=budget, index=index)


def pairs(c, query):
    args, where = [], ["p.status<>'stale'"]
    kind = query.get('status', 'review')
    if kind == 'review':
        where += ["p.status='suggested'", 'l.pair_id IS NULL']
    elif kind == 'reviewed':
        where += ['l.pair_id IS NOT NULL']
    elif kind != 'all':
        raise ValueError('无效复核筛选')
    if query.get('relation'):
        if query['relation'] not in models.RELATIONS:
            raise ValueError('无效关系筛选')
        where += ['COALESCE(l.relation,p.relation)=?']; args += [query['relation']]
    if query.get('watch_id'):
        # Both records must belong to the requested topic; do not expose cross-topic copies.
        where += ['EXISTS(SELECT 1 FROM article_watches WHERE topic_id=? AND article_id=p.left_id)',
                  'EXISTS(SELECT 1 FROM article_watches WHERE topic_id=? AND article_id=p.right_id)']
        args += [query['watch_id'], query['watch_id']]
    if query.get('article_id'):
        where += ['(p.left_id=? OR p.right_id=?)']; args += [query['article_id']] * 2
    offset = max(0, int(query.get('offset', 0)))
    base = ' FROM semantic_pairs p LEFT JOIN semantic_labels l ON l.pair_id=p.id AND ' + LABEL_MATCH + ' WHERE ' + ' AND '.join(where)
    total = c.execute('SELECT count(*)' + base, args).fetchone()[0]
    items = []
    for r in c.execute('SELECT p.*,l.relation AS reviewed_relation,l.note AS review_note' + base + ' ORDER BY p.updated_at DESC,p.id LIMIT 20 OFFSET ?', args + [offset]):
        p = dict(r)
        p['decision'] = json.loads(p['decision'])
        for side in ('left', 'right'):
            a = document(c, p[side + '_id'])
            p[side] = {k: a.get(k) for k in ('id', 'title', 'excerpt', 'url', 'publisher', 'language', 'published_at', 'kind')}
            scope = models.payload(a)
            p[side].update(review_text=scope['text'], has_full_text=scope['has_full_text'], truncated=scope['truncated'])
        items.append(p)
    return {'total': total, 'items': items}


def timestamp(a):
    try:
        return dt.datetime.fromisoformat((a.get('published_at') or a['collected_at']).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, KeyError):
        return None


def candidates(c, a, config):
    key = models.embedding_key(config)
    own = c.execute('SELECT vector,dimensions FROM semantic_vectors WHERE article_id=? AND model_key=? AND fingerprint=?', (a['id'], key, fingerprint(a))).fetchone()
    if not own:
        return []
    vector = array.array('f', own[0])
    group = c.execute('SELECT group_id FROM semantic_members WHERE article_id=?', (a['id'],)).fetchone()
    date = timestamp(a)
    found = []
    for r in c.execute("SELECT a.*,COALESCE(ac.body,'') body,v.vector,v.fingerprint,v.dimensions,m.group_id FROM semantic_vectors v JOIN articles a ON a.id=v.article_id LEFT JOIN article_content ac ON ac.article_id=a.id LEFT JOIN semantic_members m ON m.article_id=a.id WHERE v.model_key=? AND a.id<>?", (key, a['id'])):
        b = dict(r)
        if (group and b['group_id'] == group[0]) or b['dimensions'] != own[1] or b['fingerprint'] != fingerprint(b):
            continue
        other_date = timestamp(b)
        if date is not None and other_date is not None and abs(date - other_date) > config['window_days'] * 86400:
            continue
        score = max(-1.0, min(1.0, sum(x*y for x, y in zip(vector, array.array('f', b['vector'])))))
        if score >= config['candidate_threshold']:
            found.append((score, b))
    return sorted(found, key=lambda row: (-row[0], row[1]['id']))[:config['top_k']]


def save_decision(c, a, b, similarity, config, decision):
    # Keep model input order: Chinese reasoning may name A/B, so swapping only
    # quotes would make the explanation disagree with the displayed sources.
    # pair_id remains symmetric, preventing a second B/A inference.
    if not document(c, a['id']) or not document(c, b['id']):
        return False
    if fingerprint(document(c, a['id'])) != fingerprint(a) or fingerprint(document(c, b['id'])) != fingerprint(b) or models.profile(settings(c)) != models.profile(config):
        return False
    pid = pair_id(a['id'], b['id'])
    state = 'suggested' if decision['relation'] != 'unrelated' else 'unrelated'
    if (settings(c)['enabled'] and config['mode'] == 'auto' and decision['relation'] == 'duplicate'
            and decision['confidence'] >= config['auto_threshold'] and auto_gate(c, config)['ready']
            and not c.execute('SELECT 1 FROM semantic_blocks WHERE pair_id=?', (pid,)).fetchone()):
        state = 'auto'
    c.execute('INSERT OR REPLACE INTO semantic_pairs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        (pid, a['id'], b['id'], fingerprint(a), fingerprint(b), models.profile(config), similarity,
         decision['relation'], json.dumps(decision, ensure_ascii=False), config['judge_model'], state, time.time()))
    if state == 'auto':
        rebuild(c)
    return True


def start_worker(connect, db):
    return semantic_worker.start_worker(connect, db, workers=WORKERS,
        worker_lock=WORKER_LOCK, work=work)


def work(connect, db):
    return semantic_worker.work(connect, db, settings=settings, enqueue=enqueue,
        process_one=process_one)


def process_one(connect, config):
    return semantic_worker.process_one(connect, config, models=models, document=document,
        fingerprint=fingerprint, fail=fail, candidates=candidates, settings=settings,
        pair_id=pair_id, current=current, save_decision=save_decision)


def fail(c, row, error):
    attempts = row['attempts'] + 1
    c.execute('UPDATE semantic_jobs SET status=?,attempts=?,next_at=?,error=?,updated_at=? WHERE article_id=? AND fingerprint=? AND profile=?',
        ('failed' if attempts >= 3 else 'queued', attempts, time.time() + min(300, 15 * 2 ** attempts), error[:500], time.time(), row['article_id'], row['fingerprint'], row['profile']))


def evaluate(c, config, cases):
    """Independent human-labelled pairs; does not change grouping or model training."""
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ValueError('验证集需要1到1000对标注资料')
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or case.get('expected') not in models.RELATIONS:
            raise ValueError('验证样本缺少有效人工关系标签')
        a, b = case.get('left'), case.get('right')
        if not all(isinstance(x, dict) and isinstance(x.get('title'), str) and
                   all(x.get(k) is None or isinstance(x[k], str) for k in ('body', 'excerpt', 'publisher', 'language', 'kind', 'published_at')) for x in (a, b)):
            raise ValueError('验证样本缺少原始标题或包含无效字段')
        identity = tuple(sorted((fingerprint(a), fingerprint(b))))
        if identity in seen:
            raise ValueError('验证集包含重复资料对，请使用独立样本')
        seen.add(identity)
    tp = fp = fn = correct = negatives = 0
    predictions = []
    for case in cases:
        a, b = case['left'], case['right']
        d = models.judge(config, a, b)
        # Measure the actual automatic action, including its threshold and guards.
        positive = d['relation'] == 'duplicate' and d['confidence'] >= config['auto_threshold']
        truth = case['expected'] == 'duplicate'
        tp += positive and truth; fp += positive and not truth; fn += not positive and truth
        negatives += not truth; correct += d['relation'] == case['expected']
        predictions.append({'expected': case['expected'], 'decision': d})
    report = dict(count=len(cases), negatives=negatives, true_positive=tp, false_positive=fp,
                  false_negative=fn, precision=tp/(tp+fp) if tp+fp else 0,
                  recall=tp/(tp+fn) if tp+fn else 0, relation_accuracy=correct/len(cases),
                  auto_threshold=config['auto_threshold'], predictions=predictions)
    c.execute('INSERT INTO semantic_evaluations(profile,report,created_at) VALUES(?,?,?)', (models.profile(config), json.dumps(report, ensure_ascii=False), time.time()))
    return report


def export_labels(c):
    result = []
    for label in c.execute('SELECT * FROM semantic_labels'):
        if current(c, label):
            result.append({'left': models.payload(document(c, label['left_id'])) | {'excerpt': document(c, label['left_id']).get('excerpt'), 'body': document(c, label['left_id']).get('body')},
                           'right': models.payload(document(c, label['right_id'])) | {'excerpt': document(c, label['right_id']).get('excerpt'), 'body': document(c, label['right_id']).get('body')}, 'expected': label['relation']})
    return result
