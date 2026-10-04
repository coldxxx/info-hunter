"""Cached Japanese/Korean translation through the configured local LM Studio API."""
import hashlib
import json
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.request
import watchlists
import translation_model

JOBS=queue.Queue(maxsize=200)
WORKER_LOCK=threading.Lock()
WORKER=None

def model():return os.environ.get('RADAR_TRANSLATION_MODEL','')
def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS translations(article_id TEXT, model TEXT, fingerprint TEXT, status TEXT, title TEXT DEFAULT '', excerpt TEXT DEFAULT '', error TEXT DEFAULT '', updated_at REAL, PRIMARY KEY(article_id,model))''')
def language(a):
    text=a['title']+' '+(a.get('excerpt') or '')
    if re.search('[\uac00-\ud7af]',text):return ('Korean','ko')
    if re.search('[\u3040-\u30ff]',text):return ('Japanese','ja')
    value=(a.get('language') or '').lower().split('-')[0]
    return {'ja':('Japanese','ja'),'ko':('Korean','ko')}.get(value)
def fingerprint(a):return hashlib.sha256(json.dumps([a['title'],a.get('excerpt'),a.get('language')],ensure_ascii=False).encode()).hexdigest()
def cached(c,a):
    if not model() or not language(a):return None
    row=c.execute('SELECT status,title,excerpt,error FROM translations WHERE article_id=? AND model=? AND fingerprint=?',(a['id'],model(),fingerprint(a))).fetchone()
    return dict(zip(('status','title','excerpt','error'),row)) if row else {'status':'待翻译','title':'','excerpt':'','error':''}
def protect_numbers(text):
    return translation_model.protect_numbers(text)

def translate_text(text,lang):
    return translation_model.translate_text(text, lang, model=model, protect_numbers=protect_numbers)
def process(connect,a,expected_model):
    if model()!=expected_model:return
    try:
        lang=language(a)
        title=translate_text(a['title'],lang)
        excerpt=translate_text(a.get('excerpt') or '',lang)
        status,error='完成',''
    except Exception as e:
        title=excerpt='';status='失败'
        error='本地模型连接失败，请确认LM Studio服务及TranslateGemma已加载' if isinstance(e,(OSError,urllib.error.URLError)) else '译文未通过完整性或数值校验，保留原文；可重试翻译'
    with connect() as c:
        c.execute('UPDATE translations SET status=?,title=?,excerpt=?,error=?,updated_at=? WHERE article_id=? AND model=? AND fingerprint=?',(status,title,excerpt,error,time.time(),a['id'],expected_model,fingerprint(a)))
        if status=='完成':watchlists.reindex_article(c,a['id'])
def work():
    while True:
        connect,a,m=JOBS.get()
        try:process(connect,a,m)
        finally:JOBS.task_done()
def enqueue(connect,articles,retry=False):
    global WORKER
    if not model():return 0
    with WORKER_LOCK:
        if WORKER is None or not WORKER.is_alive():
            WORKER=threading.Thread(target=work,daemon=True);WORKER.start()
        count=0
        with connect() as c:
            for a in articles:
                a=dict(a)
                if not language(a):continue
                old=c.execute('SELECT status,updated_at,fingerprint FROM translations WHERE article_id=? AND model=?',(a['id'],model())).fetchone()
                same=old and old[2]==fingerprint(a)
                if same and (old[0] in ('完成','排队中') or (old[0]=='失败' and not retry and time.time()-old[1]<300)):continue
                if JOBS.full():break
                c.execute('INSERT OR REPLACE INTO translations VALUES(?,?,?,?,?,?,?,?)',(a['id'],model(),fingerprint(a),'排队中','','','',time.time()))
                # Commit before a worker can finish this job and write its result.
                c.commit();JOBS.put_nowait((connect,a,model()));count+=1
        return count
def recover(c):
    c.execute("UPDATE translations SET status='失败',error='服务重启，可重新翻译',updated_at=0 WHERE status='排队中'")
