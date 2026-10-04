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
    values={}
    pattern=r'[-+−]?\d[\d,，]*(?:[.．]\d+)?(?:\s*(?:兆|億|亿|万|千|조|억|만|천))?(?:\s*(?:円|日元|ドル|달러|ウォン|원|韩元|美元|%|％))?'
    def replace(m):
        raw=m.group(0)
        # Only fixed written units are localized; no exchange-rate conversion.
        for before,after in [('億','亿'),('조','万亿'),('억','亿'),('만','万'),('천','千'),('ウォン','韩元'),('달러','美元'),('ドル','美元'),('円','日元'),('원','韩元')]:raw=raw.replace(before,after)
        token='ZXQNUM'+str(len(values)).zfill(4)+'ZXQ'
        values[token]=raw;return token
    return re.sub(pattern,replace,text),values

def translate_text(text,lang):
    if not text:return ''
    protected,values=protect_numbers(text)
    chunks=[];start=0
    while start<len(protected):
        end=min(start+600,len(protected))
        for m in re.finditer(r'ZXQNUM[0-9]+ZXQ',protected):
            if m.start()<end<m.end():end=m.start();break
        chunks.append(protected[start:end]);start=end
    output=[]
    endpoint=os.environ.get('RADAR_TRANSLATION_URL','http://127.0.0.1:1234/v1').rstrip('/')+'/completions'
    for chunk in chunks:
        prompt=(f'You are a professional {lang[0]} ({lang[1]}) to Chinese (Simplified) (zh-Hans) translator. Your goal is to accurately convey the meaning and nuances of the original {lang[0]} text while adhering to Chinese (Simplified) grammar, vocabulary, and cultural sensitivities.\n'
                f'Produce only the Chinese (Simplified) translation, without any additional explanations or commentary. Please translate the following {lang[0]} text into Chinese (Simplified):\n\n\n{chunk}')
        # Use the raw endpoint: TranslateGemma's structured Jinja input is not
        # expressible through LM Studio's ordinary OpenAI chat-content schema.
        raw='<bos><start_of_turn>user\n'+prompt+'<end_of_turn>\n<start_of_turn>model\n'
        body=json.dumps({'model':model(),'prompt':raw,'temperature':0.1,'max_tokens':1800,'stop':['<end_of_turn>','<eos>'],'stream':False}).encode()
        req=urllib.request.Request(endpoint,data=body,headers={'Content-Type':'application/json'})
        # Local model calls must bypass the user's outbound HTTP proxy.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=120) as r:result=json.load(r)
        choice=result['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError('译文超出长度限制，未保存不完整译文')
        content=choice['text']
        if not isinstance(content,str) or not content.strip():raise ValueError('模型未返回译文')
        output.append(content.strip())
    result='\n'.join(output)
    for token in values:
        if result.count(token)!=1:raise ValueError('数值占位校验失败')
    residue=re.sub(r'ZXQNUM[0-9]+ZXQ','',result)
    if re.search(r'\d',residue):raise ValueError('译文新增了原文未提供的数字')
    for token,value in values.items():result=result.replace(token,value)
    return result
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
