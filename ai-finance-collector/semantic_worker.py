"""Semantic job execution with caller-supplied state and model operations."""
import array
import fcntl
from pathlib import Path
import threading
import time


def start_worker(connect, db, *, workers, worker_lock, work):
    key = str(Path(db).resolve())
    with worker_lock:
        if key in workers and workers[key].is_alive():
            return
        thread = threading.Thread(target=work, args=(connect, Path(db)), name='semantic-dedup', daemon=True)
        workers[key] = thread
        thread.start()


def work(connect, db, *, settings, enqueue, process_one):
    lock = (db.parent / 'semantic-worker.lock').open('a')
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with connect() as c:
            c.execute("UPDATE semantic_jobs SET status='queued',error='服务重启后恢复任务' WHERE status='running'")
        scanned = 0
        while True:
            try:
                with connect() as c:
                    config = settings(c)
                    if config['enabled'] and time.time() - scanned > 120:
                        enqueue(c); scanned = time.time()
                if not config['enabled']:
                    time.sleep(2); continue
                if not process_one(connect, config):
                    time.sleep(2)
            except Exception as e:
                print('Semantic worker:', type(e).__name__, flush=True)
                time.sleep(5)
    finally:
        lock.close()


def process_one(connect, config, *, models, document, fingerprint, fail, candidates, settings, pair_id, current, save_decision):
    key, ekey = models.profile(config), models.embedding_key(config)
    with connect() as c:
        # Index all queued originals before making decisions so backfill is order-independent.
        rows = c.execute("SELECT * FROM semantic_jobs WHERE status='queued' AND phase='embed' AND profile=? AND next_at<=? ORDER BY updated_at LIMIT 8", (key, time.time())).fetchall()
        if rows:
            docs = [document(c, r['article_id']) for r in rows]
            pending = [a for a in docs if a and not c.execute('SELECT 1 FROM semantic_vectors WHERE article_id=? AND fingerprint=? AND model_key=?', (a['id'], fingerprint(a), ekey)).fetchone()]
            for r in rows:
                c.execute("UPDATE semantic_jobs SET status='running' WHERE article_id=?", (r['article_id'],))
    if rows:
        try:
            vectors = models.embed(config, [models.embedding_text(a) for a in pending]) if pending else []
            with connect() as c:
                for a, v in zip(pending, vectors):
                    latest = document(c, a['id'])
                    if latest and fingerprint(latest) == fingerprint(a):
                        c.execute('INSERT OR REPLACE INTO semantic_vectors VALUES(?,?,?,?,?,?)', (a['id'], fingerprint(a), ekey, len(v), array.array('f', v).tobytes(), time.time()))
                for row in rows:
                    c.execute("UPDATE semantic_jobs SET status='queued',phase='judge',error='',attempts=0,updated_at=? WHERE article_id=? AND fingerprint=? AND profile=?", (time.time(), row['article_id'], row['fingerprint'], key))
        except ValueError as e:
            with connect() as c:
                for row in rows:
                    fail(c, row, str(e))
        return True
    with connect() as c:
        row = c.execute("SELECT * FROM semantic_jobs WHERE status='queued' AND phase='judge' AND profile=? AND next_at<=? ORDER BY updated_at LIMIT 1", (key, time.time())).fetchone()
        if not row:
            return False
        # Daily cap is checked for each uncached pair below, so cached and
        # candidate-free jobs can still complete after the budget is exhausted.
        a = document(c, row['article_id'])
        if not a:
            c.execute('DELETE FROM semantic_jobs WHERE article_id=?', (row['article_id'],)); return True
        found = candidates(c, a, config)
        c.execute("UPDATE semantic_jobs SET status='running' WHERE article_id=?", (a['id'],))
    try:
        for similarity, b in found:
            with connect() as c:
                if not settings(c)['enabled'] or models.profile(settings(c)) != key:
                    c.execute("UPDATE semantic_jobs SET status='queued' WHERE article_id=?", (a['id'],)); return True
                pid = pair_id(a['id'], b['id'])
                old = c.execute('SELECT * FROM semantic_pairs WHERE id=?', (pid,)).fetchone()
                if old and old['profile'] == key and old['status'] != 'stale' and current(c, old):
                    continue
                if c.execute('SELECT count(*) FROM semantic_calls WHERE created_at>=?', (time.time() - 86400,)).fetchone()[0] >= config['daily_pair_limit']:
                    c.execute("UPDATE semantic_jobs SET status='queued' WHERE article_id=?", (a['id'],)); return False
                c.execute('INSERT INTO semantic_calls(profile,created_at) VALUES(?,?)', (key, time.time()))
                c.execute('DELETE FROM semantic_calls WHERE created_at<?', (time.time() - 7 * 86400,))
            decision = models.judge(config, a, b)
            with connect() as c:
                save_decision(c, a, b, similarity, config, decision)
        with connect() as c:
            c.execute("UPDATE semantic_jobs SET status='completed',error='',updated_at=? WHERE article_id=? AND fingerprint=? AND profile=?", (time.time(), a['id'], row['fingerprint'], key))
    except ValueError as e:
        with connect() as c:
            fail(c, row, str(e))
    return True
