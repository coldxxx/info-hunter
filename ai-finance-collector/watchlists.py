"""User-defined watch topics, source bindings, and explainable archive matching."""
import engineering
import dedup
import reddit_quality
import hashlib
import datetime as dt
import json
import re
import uuid
from urllib.parse import urlencode

REGIONS={'全球':('en-US','US','US:en'),'中国大陆':('zh-CN','CN','CN:zh-Hans'),'日本':('ja','JP','JP:ja'),'韩国':('ko','KR','KR:ko'),'台湾':('zh-TW','TW','TW:zh-Hant')}
CODING_WORDS=['AI coding', 'coding assistant', 'software engineering', 'developer tools', 'AI agent', 'coding agent', 'agentic', 'agent engineering', 'agent framework', 'MCP server', 'Model Context Protocol', 'tool calling', 'Claude Code', 'Codex', 'Cursor', 'GitHub Copilot', 'GitHub', '软件开发', '软件工程', '开发工具', '智能体', '代码生成', '编程助手', 'AI编程', '代码审查', 'AIエージェント', 'コーディング', 'AI 에이전트', '코딩']

LEGACY_CODING_WORDS=CODING_WORDS[:]
CODING_WORDS=CODING_WORDS+['code review']

def schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS watch_topics(id TEXT PRIMARY KEY,config TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS watch_sources(topic_id TEXT,source_id TEXT,include_all INTEGER DEFAULT 0,PRIMARY KEY(topic_id,source_id));
    CREATE TABLE IF NOT EXISTS article_watches(article_id TEXT,topic_id TEXT,reason TEXT,PRIMARY KEY(article_id,topic_id));
    CREATE TABLE IF NOT EXISTS article_focus(article_id TEXT,profile TEXT,eligible INTEGER,category TEXT,reason TEXT,evidence TEXT,version INTEGER,PRIMARY KEY(article_id,profile));
    CREATE INDEX IF NOT EXISTS focus_category ON article_focus(profile,category,article_id);
    CREATE TABLE IF NOT EXISTS watch_migrations(name TEXT PRIMARY KEY);
    CREATE INDEX IF NOT EXISTS watches_topic ON article_watches(topic_id,article_id);
    ''')
def matches(text,word):
    low=text.lower();word=word.lower()
    return bool(re.search(r'\b'+re.escape(word)+r'\b',low)) if word.isascii() else word in low

def terms(value):
    if isinstance(value,str):value=re.split(r'[\n,，;；、]+',value)
    if not isinstance(value,list) or any(not isinstance(x,str) for x in value):raise ValueError('关键词须为文本或文本列表')
    result=list(dict.fromkeys(x.strip() for x in value if x.strip()))
    if len(result)>70 or any(len(x)>100 or any(ord(ch)<32 for ch in x) for x in result):raise ValueError('每组最多70个词，每个词最多100字')
    return result

def get(c,ident):
    row=c.execute('SELECT config FROM watch_topics WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('主题不存在')
    return json.loads(row[0])
def configs(c):return [json.loads(row[0]) for row in c.execute('SELECT config FROM watch_topics ORDER BY created_at,id')]
def listing(c):
    out=[]
    for t in configs(c):
        out.append(dict(t,article_count=dedup.count(c,' WHERE '+reddit_quality.VISIBLE+' AND EXISTS(SELECT 1 FROM article_watches aw WHERE aw.article_id=articles.id AND aw.topic_id=?)',[t['id']]),source_count=c.execute('SELECT count(*) FROM watch_sources WHERE topic_id=?',(t['id'],)).fetchone()[0]))
    return out

def bind(c,topic_id,source_id,include_all=False):
    get(c,topic_id)
    if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(source_id,)).fetchone():raise ValueError('来源不存在')
    c.execute('INSERT OR REPLACE INTO watch_sources VALUES(?,?,?)',(topic_id,source_id,int(bool(include_all))))

def bind_many(c,topic_id,source_ids,include_all=False):
    """Add global sources to a topic without cloning sources or replacing existing rules."""
    get(c,topic_id)
    if not isinstance(source_ids,list) or not 1<=len(source_ids)<=100 or any(not isinstance(s,str) or not s for s in source_ids):
        raise ValueError('每次选择1—100个已有来源')
    ids=list(dict.fromkeys(source_ids))
    # Validate the complete selection before making any changes.
    for sid in ids:
        if not c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NULL',(sid,)).fetchone():raise ValueError('来源不存在')
    added=0
    for sid in ids:
        added+=c.execute('INSERT OR IGNORE INTO watch_sources VALUES(?,?,?)',(topic_id,sid,int(include_all))).rowcount
    reindex(c,topic_id)
    return {'added':added,'already_followed':len(ids)-added}

def applies(t,a,text,include_all=False,legacy=False,manual=False):
    # Region and exclusions always take precedence over source-wide inclusion.
    if t.get('content_profile','standard')!='developer' and t.get('regions') and a.get('region') not in t['regions']:return None
    if any(matches(text,w) for w in t.get('exclude',[])):return None
    hit=[w for w in t['keywords'] if matches(text,w)]
    if manual:return '手动收录'
    if t.get('content_profile')=='developer':
        decision=engineering.assess(a,text)
        if not decision['eligible'] or not (hit or include_all):return None
        return decision['category']+' · '+decision['reason']
    if legacy:return '原AI资料库'+('；关键词：'+'、'.join(hit[:6]) if hit else '')
    if hit:return '关键词：'+ '、'.join(hit[:6])
    if include_all:return '关注来源：全部内容'
    if legacy:return '原AI资料库'
    return None

def reindex_article(c,article_id,only=None):
    row=c.execute('SELECT * FROM articles WHERE id=?',(article_id,)).fetchone()
    if not row:return
    a=dict(row);text=a['title']+' '+(a['excerpt'] or '')
    # Use every completed local translation as another matchable text, never as verification.
    fp=hashlib.sha256(json.dumps([a['title'],a.get('excerpt'),a.get('language')],ensure_ascii=False).encode()).hexdigest()
    for r in c.execute("SELECT title,excerpt FROM translations WHERE article_id=? AND status='完成' AND fingerprint=?",(article_id,fp)):text+=' '+r[0]+' '+r[1]
    source_ids=[r[0] for r in c.execute('SELECT source_id FROM sightings WHERE article_id=?',(article_id,))]
    selected=[get(c,only)] if only else configs(c)
    if any(t.get('content_profile')=='developer' for t in selected):
        assessment=engineering.assess(a,text)
        c.execute('INSERT OR REPLACE INTO article_focus VALUES(?,?,?,?,?,?,?)',(article_id,'developer',int(assessment['eligible']),assessment['category'],assessment['reason'],json.dumps(assessment['evidence'],ensure_ascii=False),engineering.VERSION))
    for t in selected:
        includes=any(c.execute('SELECT include_all FROM watch_sources WHERE topic_id=? AND source_id=?',(t['id'],sid)).fetchone()[0] for sid in source_ids if c.execute('SELECT 1 FROM watch_sources WHERE topic_id=? AND source_id=?',(t['id'],sid)).fetchone())
        old=c.execute('SELECT reason FROM article_watches WHERE topic_id=? AND article_id=?',(t['id'],article_id)).fetchone()
        legacy=t['id']=='ai' and old and old[0].startswith('原AI资料库')
        reason=applies(t,a,text,includes,legacy,bool(old and old[0]=='手动收录'))
        if reason:c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(article_id,t['id'],reason))
        else:c.execute('DELETE FROM article_watches WHERE article_id=? AND topic_id=?',(article_id,t['id']))
def reindex(c,topic_id):
    for row in c.execute('SELECT id FROM articles').fetchall():reindex_article(c,row[0],topic_id)

def search_sources(c,t):
    wanted=set()
    if t['news_search']:
        query=' OR '.join('"'+w.replace('"','')+'"' for w in t['keywords'])
        query='('+query+')'
        if t.get('content_profile')=='developer':query+=' ('+' OR '.join(engineering.SEARCH_TERMS)+')'
        query=query+''.join(' -"'+w.replace('"','')+'"' for w in t['exclude'])+' when:7d'
        for region in (t['regions'] or ['全球','中国大陆']):
            hl,gl,ceid=REGIONS[region]
            sid='search-'+t['id']+'-'+gl
            if c.execute('SELECT 1 FROM sources WHERE id=? AND deleted_at IS NOT NULL',(sid,)).fetchone():continue
            wanted.add(sid)
            edition=({'全球':'英文技术检索','中国大陆':'中文技术检索','日本':'日文技术检索','韩国':'韩文技术检索','台湾':'繁体中文技术检索'}[region] if t.get('content_profile')=='developer' else region+'资讯检索')
            s={'id':sid,'name':t['name']+' · '+edition,'url':'https://news.google.com/rss/search?'+urlencode({'q':query,'hl':hl,'gl':gl,'ceid':ceid}),'adapter':'rss','region':region,'language':hl,'kind':'新闻','focused':True,'enabled':True,'user_added':True,'search_topic':t['id'],'note':'公开新闻索引，非全网搜索或原文全文；覆盖可能不完整。'}
            c.execute('INSERT INTO sources(id,config) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config',(sid,json.dumps(s,ensure_ascii=False)))
            bind(c,t['id'],sid,False)
    # Preserve archived sources but stop collecting search editions removed from this topic.
    for row in c.execute('SELECT id,config FROM sources').fetchall():
        s=json.loads(row[1])
        if s.get('search_topic')==t['id'] and row[0] not in wanted:
            c.execute('DELETE FROM watch_sources WHERE topic_id=? AND source_id=?',(t['id'],row[0]))

def save(c,body):
    ident=body.get('id') or 'topic-'+uuid.uuid4().hex[:16]
    old=get(c,ident) if body.get('id') else {}
    name=str(body.get('name',old.get('name',''))).strip()
    words=terms(body.get('keywords',old.get('keywords',[])))
    if not name or len(name)>80:raise ValueError('主题名称须为1—80字')
    if not words:raise ValueError('至少填写一个关键词')
    regions=body.get('regions',old.get('regions',[]))
    if not isinstance(regions,list) or any(r not in REGIONS for r in regions):raise ValueError('地区须从已有地区中选择')
    for key in ('enabled','news_search'):
        if key in body and not isinstance(body[key],bool):raise ValueError(key+'须为布尔值')
    profile=body.get('content_profile',old.get('content_profile','standard'))
    if profile not in ('standard','developer'):raise ValueError('无效的内容侧重')
    if profile=='developer':regions=[]
    t={'content_profile':profile,'id':ident,'name':name,'description':str(body.get('description',old.get('description','')))[:500],'keywords':words,'exclude':terms(body.get('exclude',old.get('exclude',[]))),'regions':list(dict.fromkeys(regions)),'enabled':body.get('enabled',old.get('enabled',True)),'news_search':body.get('news_search',old.get('news_search',True))}
    c.execute('INSERT INTO watch_topics VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config',(ident,json.dumps(t,ensure_ascii=False),dt.datetime.now(dt.timezone.utc).isoformat()))
    search_sources(c,t);reindex(c,ident)
    return t

def bootstrap(c,ai_words):
    schema(c)
    # One-time migration; init must never overwrite user-edited topics or associations.
    if c.execute("SELECT 1 FROM watch_topics WHERE id='ai'").fetchone():
        migrate_profiles(c)
        return
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    ai={'id':'ai','name':'AI 产业','description':'大模型、算力、资本开支与供应链；保留原研究资料和来源。','keywords':ai_words,'exclude':[],'regions':[],'enabled':True,'news_search':False}
    c.execute('INSERT INTO watch_topics VALUES(?,?,?)',('ai',json.dumps(ai,ensure_ascii=False),stamp))
    for row in c.execute('SELECT id,config FROM sources').fetchall():bind(c,'ai',row[0],json.loads(row[1]).get('focused',False))
    c.execute("INSERT OR IGNORE INTO article_watches SELECT id,'ai','原AI资料库' FROM articles")
    coding={'content_profile':'developer','id':'coding-agent','name':'Coding 与 Agent','description':'编程助手、Agent工程、MCP、工具调用、开发工具和实际工程经验。','keywords':CODING_WORDS,'exclude':[],'regions':[],'enabled':True,'news_search':True}
    c.execute('INSERT INTO watch_topics VALUES(?,?,?)',('coding-agent',json.dumps(coding,ensure_ascii=False),stamp))
    sources=[('coding-github','GitHub 官方博客','https://github.blog/feed/','新闻'),('coding-changelog','GitHub Changelog','https://github.blog/changelog/feed/','公司发布'),('coding-hn','Hacker News · 技术讨论','https://hnrss.org/frontpage','论坛')]
    for sid,name,url,kind in sources:
        s={'id':sid,'name':name,'url':url,'region':'全球','language':'en','kind':kind,'adapter':'rss','enabled':True,'user_added':True,'focused':False,'note':'公开订阅源；按所选主题关键词匹配，归档标题、摘要与链接。'}
        c.execute('INSERT OR IGNORE INTO sources(id,config) VALUES(?,?)',(sid,json.dumps(s,ensure_ascii=False)));bind(c,coding['id'],sid,False)
    for row in c.execute('SELECT id,config FROM sources').fetchall():
        if 'latent.space' in json.loads(row[1]).get('url',''):bind(c,coding['id'],row[0],False)
    search_sources(c,coding);reindex(c,coding['id'])
    migrate_profiles(c)

def migrate_profiles(c):
    marker='developer-focus-'+str(engineering.VERSION)
    if c.execute('SELECT 1 FROM watch_migrations WHERE name=?',(marker,)).fetchone():return
    # Add the default once. A later explicit choice of standard must survive restart.
    for t in configs(c):
        if t['id']=='coding-agent' and 'content_profile' not in t:t['content_profile']='developer'
        if t.get('content_profile')=='developer':
            if t['id']=='coding-agent' and t['keywords']==LEGACY_CODING_WORDS:t['keywords']=CODING_WORDS[:]
            t['regions']=[]
            c.execute('UPDATE watch_topics SET config=? WHERE id=?',(json.dumps(t,ensure_ascii=False),t['id']))
            search_sources(c,t)
            reindex(c,t['id'])
    c.execute('INSERT INTO watch_migrations VALUES(?)',(marker,))

def collection_sources(c,topic_id=None):
    ts=[get(c,topic_id)] if topic_id else configs(c)
    active={t['id']:t for t in ts if t['enabled']}
    result=[]
    for row in c.execute('SELECT id,config FROM sources WHERE deleted_at IS NULL'):
        bindings=[dict(r) for r in c.execute('SELECT * FROM watch_sources WHERE source_id=?',(row[0],)) if r['topic_id'] in active]
        if not bindings:continue
        s=json.loads(row[1]);s['_watch_rules']=[dict(active[b['topic_id']],include_all=bool(b['include_all'])) for b in bindings];result.append(s)
    return result

def accepts(s,a):
    text=a['title']+' '+a.get('excerpt','')
    return any(applies(t,dict(a,region=s['region']),text,t['include_all']) for t in s['_watch_rules'])
