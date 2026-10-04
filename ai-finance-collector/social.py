"""Authorized social connectors. Credentials never enter the article database."""
import base64
import datetime as dt
import email.utils
import getpass
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('RADAR_CONNECTIONS_FILE',str(ROOT/'connections.local.json')))
REDDIT_LOCK = threading.Lock()
TOKEN = {}

class AccessIssue(Exception):
    def __init__(self, status, message, delay=0):
        self.status, self.delay = status, delay
        super().__init__(message)

def settings():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    for platform, key, env in [('x','bearer_token','X_BEARER_TOKEN'),('reddit','client_id','REDDIT_CLIENT_ID'),('reddit','client_secret','REDDIT_CLIENT_SECRET'),('reddit','refresh_token','REDDIT_REFRESH_TOKEN'),('reddit','user_agent','REDDIT_USER_AGENT')]:
        if os.environ.get(env):
            cfg.setdefault(platform,{})[key] = os.environ[env]
    return cfg

def connection_status():
    cfg = settings()
    r, x = cfg.get('reddit',{}), cfg.get('x',{})
    return {
      'reddit': {'credentials_configured':bool(r.get('client_id') and r.get('client_secret')), 'approval_confirmed':r.get('approved') is True, 'enabled':r.get('enabled') is True, 'user_agent_configured':bool(r.get('user_agent'))},
      'x': {'credentials_configured':bool(x.get('bearer_token')), 'paid_usage_enabled':x.get('enabled') is True, 'daily_request_limit':x.get('daily_requests',4), 'posts_per_request':x.get('max_results',20)},
      'xueqiu': {'mode':'browser-assisted', 'automatic_api_connected':False, 'message':'2026-09-08 已确认网页登录；搜索试读时浏览器连接丢失，帖子读取及入库尚未验证。登录状态留在浏览器。'},
    }

def effective_adapter(source, cfg=None):
    """Use the same connector selection for collection and its read-only description."""
    platform = source.get('platform')
    if (source.get('user_added') or source.get('connection_id')) and platform in ('reddit', 'x'):
        connection = (settings() if cfg is None else cfg).get(platform, {})
        if connection.get('enabled') is True and (platform == 'x' or connection.get('approved') is True):
            return platform
    return source['adapter']

def request_json(url, headers=None, body=None):
    # No redirect of bearer/basic credentials to an unexpected host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    req = urllib.request.Request(url, data=body, headers={'User-Agent':'PersonalAIIndustryRadar/0.2', **(headers or {})})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as r:
            data = r.read(5_000_001)
            if len(data)>5_000_000:
                raise AccessIssue('失败','接口响应超出大小限制')
            return json.loads(data)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raw=e.headers.get('Retry-After','')
            try:
                delay=max(60,int(raw))
            except ValueError:
                try:
                    retry=email.utils.parsedate_to_datetime(raw)
                    delay=max(60,int(retry.timestamp()-time.time()))
                except (ValueError,TypeError):
                    delay=900
            try:
                delay=max(delay,int(e.headers.get('x-rate-limit-reset','0'))-int(time.time()))
            except ValueError:
                pass
            raise AccessIssue('限流等待','平台返回 429；已暂停该平台请求，到期后再尝试。',delay) from None
        if e.code == 401:
            raise AccessIssue('待授权','凭据无效或过期，请重新配置。') from None
        if e.code == 402:
            raise AccessIssue('额度不足','平台余额或读取额度不足；未自动充值。') from None
        if e.code == 403:
            raise AccessIssue('权限不足','平台拒绝访问，请检查应用审批、接口权限或内容访问权限。') from None
        raise AccessIssue('失败','平台接口 HTTP '+str(e.code)) from None
    except (json.JSONDecodeError,UnicodeDecodeError):
        raise AccessIssue('失败','接口未返回有效 JSON；没有将登录页或错误页当作资料。') from None

def state_db(db):
    c=sqlite3.connect(db,timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS social_state(key TEXT PRIMARY KEY,value TEXT)')
    c.commit()
    return c

def cooldown(db, platform, delay=0):
    with state_db(db) as c:
        if delay:
            c.execute('INSERT OR REPLACE INTO social_state VALUES(?,?)',(platform+':retry',str(time.time()+delay)))
        else:
            r=c.execute('SELECT value FROM social_state WHERE key=?',(platform+':retry',)).fetchone()
            if r and float(r[0])>time.time():
                raise AccessIssue('限流等待','平台处于限流冷却期；没有发出新请求。')

def reddit_rows(s, cfg):
    c=cfg.get('reddit',{})
    if c.get('approved') is not True:
        raise AccessIssue('待审批','需要 Reddit Data API 审批；普通账号和浏览器登录不等于接口获批。')
    if not c.get('client_id') or not c.get('client_secret'):
        raise AccessIssue('待授权','请在本机运行 python3 social.py configure reddit，配置已获批应用。')
    if c.get('enabled') is not True:
        raise AccessIssue('未启用','Reddit 接口尚未启用。')
    ua=c.get('user_agent','')
    if not ua:
        raise AccessIssue('待配置','请设置能标识应用与联系账号的 Reddit User-Agent。')
    subreddit=s.get('subreddit','')
    if not re.fullmatch('[A-Za-z0-9_]{1,50}',subreddit):
        raise AccessIssue('待配置','无效 subreddit 名称')
    identity=(c['client_id'],c['client_secret'],c.get('refresh_token',''))
    if TOKEN.get('identity')!=identity or TOKEN.get('expires',0)<time.time()+60:
        grant={'grant_type':'refresh_token','refresh_token':c['refresh_token']} if c.get('refresh_token') else {'grant_type':'client_credentials'}
        auth=base64.b64encode((c['client_id']+':'+c['client_secret']).encode()).decode()
        data=request_json('https://www.reddit.com/api/v1/access_token',{'User-Agent':ua,'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded'},urllib.parse.urlencode(grant).encode())
        if not data.get('access_token'):
            raise AccessIssue('待授权','Reddit 未返回访问令牌；请检查应用与授权方式。')
        TOKEN.update(identity=identity,value=data['access_token'],expires=time.time()+int(data.get('expires_in',3600)))
    q=urllib.parse.urlencode({'limit':50,'raw_json':1})
    data=request_json('https://oauth.reddit.com/r/'+subreddit+'/new?'+q,{'User-Agent':ua,'Authorization':'Bearer '+TOKEN['value']})
    if not isinstance(data.get('data',{}).get('children'),list):
        raise AccessIssue('失败','Reddit 返回的内容不是帖子列表。')
    rows=[]
    for item in data['data']['children']:
        p=item.get('data',{})
        deleted=bool(p.get('removed_by_category') or p.get('selftext') in ('[removed]','[deleted]'))
        link=p.get('permalink','')
        if not link.startswith('/r/'):
            continue
        rows.append({'deleted':deleted, 'body':p.get('selftext','') if not deleted else '', 'title':p.get('title',''), 'url':'https://www.reddit.com'+link, 'excerpt':p.get('selftext','')[:1200], 'comment_count':p.get('num_comments'), 'outbound_url':p.get('url_overridden_by_dest') or p.get('url'), 'flair':p.get('link_flair_text') or '', 'publisher':'Reddit u/'+p.get('author','unknown'), 'published_at':dt.datetime.fromtimestamp(p['created_utc'],dt.timezone.utc).isoformat() if p.get('created_utc') else None})
    return rows

def x_rows(s, cfg, db):
    c=cfg.get('x',{})
    if not c.get('bearer_token'):
        raise AccessIssue('待授权','未配置 X Bearer Token；没有请求付费接口。')
    if c.get('enabled') is not True:
        raise AccessIssue('待启用','X 接口按用量计费；请在本机配置并明确启用后使用。')
    limit=int(c.get('daily_requests',4))
    count=int(c.get('max_results',20))
    if limit<1 or not 10<=count<=100:
        raise AccessIssue('待配置','X 请求上限必须为正数，每次帖子数须在 10–100 之间。')
    # Reserve a request before network I/O, including timeouts, to bound local use.
    with state_db(db) as conn:
        conn.execute('BEGIN IMMEDIATE')
        key='x:requests:'+dt.datetime.now(dt.timezone.utc).date().isoformat()
        row=conn.execute('SELECT value FROM social_state WHERE key=?',(key,)).fetchone()
        used=int(row[0]) if row else 0
        if used>=limit:
            raise AccessIssue('达到日上限','已达到本地 X 每日请求上限；次日 UTC 零点后恢复。')
        conn.execute('INSERT OR REPLACE INTO social_state VALUES(?,?)',(key,str(used+1)))
    params={'query':s['query'],'max_results':count,'tweet.fields':'created_at,author_id'}
    data=request_json('https://api.x.com/2/tweets/search/recent?'+urllib.parse.urlencode(params),{'Authorization':'Bearer '+c['bearer_token']})
    if data.get('errors'):
        raise AccessIssue('失败','X 返回部分或完整错误，未将本次结果标记为成功。')
    if 'data' not in data and data.get('meta',{}).get('result_count')!=0:
        raise AccessIssue('失败','X 响应格式异常。')
    return [{'title':p['text'][:240],'excerpt':p['text'],'url':'https://x.com/i/web/status/'+p['id'],'published_at':p.get('created_at'),'publisher':'X 用户 '+p.get('author_id','')} for p in data.get('data',[])]

def collect(s, db):
    platform=s['adapter']
    guard=REDDIT_LOCK if platform=='reddit' else threading.Lock()
    with guard:
        try:
            cooldown(db,platform)
            rows=reddit_rows(s,settings()) if platform=='reddit' else x_rows(s,settings(),db)
            return rows,'成功',''
        except AccessIssue as e:
            if platform=='reddit' and e.status=='待授权':
                TOKEN.clear()
            if e.delay:
                cooldown(db,platform,e.delay)
            return [],e.status,str(e)

def configure(platform):
    cfg=settings()
    if platform=='reddit':
        if input('是否已获得 Reddit Data API 审批？输入 yes 确认：').strip()!='yes':
            print('未配置：需要先申请 Reddit Data API 权限。');return
        c={'approved':True,'enabled':True}
        c['client_id']=getpass.getpass('Client ID（隐藏输入）：').strip()
        c['client_secret']=getpass.getpass('Client secret（隐藏输入）：').strip()
        c['refresh_token']=getpass.getpass('Refresh token（可留空，使用应用授权）：').strip()
        c['user_agent']=input('User-Agent，例如 desktop:ai-industry-radar:0.2 (by /u/你的账号)：').strip()
        if not c['client_id'] or not c['client_secret'] or not c['user_agent']:
            raise ValueError('必填项为空，未保存')
    else:
        print('X API 按读取资源计费。请先在 X 控制台设置费用上限；本地限制不能替代平台账单上限。')
        if input('是否启用付费 X 数据请求？输入 yes 确认：').strip()!='yes':
            print('未启用，也未请求接口。');return
        c={'enabled':True,'bearer_token':getpass.getpass('X Bearer Token（隐藏输入）：').strip()}
        c['daily_requests']=int(input('每日最多请求次数 [4]：') or '4')
        c['max_results']=int(input('每次最多帖子数 [20]：') or '20')
        if not c['bearer_token'] or c['daily_requests']<1 or not 10<=c['max_results']<=100:
            raise ValueError('配置无效，未保存')
    cfg[platform]=c
    temp=CONFIG.with_suffix('.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(cfg,f,ensure_ascii=False,indent=2)
    os.replace(temp,CONFIG)
    print('配置已保存到本机私有文件；没有打印凭据。运行采集命令测试实际权限。')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['status','configure'])
    p.add_argument('platform',nargs='?',choices=['reddit','x'])
    a=p.parse_args()
    if a.command=='status':
        print(json.dumps(connection_status(),ensure_ascii=False,indent=2))
    elif a.platform:
        configure(a.platform)
    else:
        p.error('configure 需要 reddit 或 x')
