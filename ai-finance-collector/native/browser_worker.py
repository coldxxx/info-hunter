"""Persistent, dedicated browser contexts; no interaction with everyday profiles."""
import asyncio
import datetime as dt
import hashlib
import json
import re
import sys
import time
from urllib.parse import urlsplit
from pathlib import Path
from manual_login import ManualLogin,MESSAGE as LOGIN_MESSAGE


class Paused(Exception):
    def __init__(self, status, message, retry_at=0):
        self.status=status; self.retry_at=retry_at
        super().__init__(message)


def identity(platform, url):
    host=(urlsplit(url).hostname or '').lower()
    if platform=='x' and host not in ('x.com','www.x.com','twitter.com','www.twitter.com'): raise ValueError('X 连接仅允许 x.com')
    if platform=='reddit' and host not in ('reddit.com','www.reddit.com','old.reddit.com'): raise ValueError('Reddit 连接仅允许 reddit.com')
    if platform not in ('x','reddit','blog'): raise ValueError('未支持的平台')
    return platform if platform!='blog' else 'blog-'+hashlib.sha256(host.encode()).hexdigest()[:12]


def detect_block(text, url, code=200, retry_after=None):
    low=text.lower()
    if code==429:
        delay=3600
        try: delay=max(60,int(retry_after or 3600))
        except ValueError:
            from email.utils import parsedate_to_datetime
            try: delay=max(60,parsedate_to_datetime(retry_after).timestamp()-time.time())
            except (ValueError,TypeError): pass
        raise Paused('cooldown','平台限流，已停止访问',time.time()+delay)
    if code in (401,403): raise Paused('needs_login','访问被拒绝，请打开专用浏览器检查登录或账号限制')
    if code>=500: raise OSError('平台暂时不可用')
    if any(x in low for x in ('verify you are human','unusual activity','account suspended','confirm you are human','检测到异常','请完成验证','访问过于频繁','环境异常')):
        raise Paused('challenge','检测到验证或账号限制，等待人工处理')
    if re.search(r'/(?:i/flow/login|login|signin)(?:[/?]|$)',url):
        raise Paused('needs_login','登录已失效，请重新登录')


POSTS_JS = r'''(platform) => {
 const containers = platform === 'x' ? [...document.querySelectorAll('article[data-testid="tweet"]')] : [...document.querySelectorAll('shreddit-post, .thing[data-fullname]')];
 return containers.filter(el => !el.matches('[is-promoted="true"], [promoted="true"], .promoted')).map(el => {
   if (platform === 'x') {
     const a=[...el.querySelectorAll('a[href*="/status/"]')].find(a=>a.querySelector('time'));
     const text=el.querySelector('[data-testid="tweetText"]')?.innerText || '';
     return {url:a?.href,title:text.slice(0,140),body:text,excerpt:text.slice(0,1200),published_at:el.querySelector('time')?.dateTime,publisher:el.querySelector('[data-testid="User-Name"]')?.innerText?.replace(/\n/g,' ')};
   }
   const link=el.getAttribute('permalink') || el.querySelector('a.comments')?.getAttribute('href');
   const text=el.querySelector('[slot="text-body"], .usertext-body')?.innerText || '';
   const title=el.getAttribute('post-title') || el.querySelector('a.title')?.innerText || '';
   const comments=el.getAttribute('comment-count') ?? el.getAttribute('num-comments') ?? el.querySelector('a.comments')?.innerText ?? null;
   const outbound=el.getAttribute('content-href') || el.querySelector('a.title')?.href || null;
   return {url:link?new URL(link,location.origin).href:null,title,body:text,excerpt:text.slice(0,1200),comment_count:comments,outbound_url:outbound,flair:el.getAttribute('link-flair-text') || el.querySelector('[slot="post-flair"], .linkflairlabel')?.innerText || '',deleted:['[deleted]','[removed]'].includes(text.trim()),published_at:el.getAttribute('created-timestamp') || el.querySelector('time')?.dateTime,publisher:'Reddit u/'+(el.getAttribute('author')||el.querySelector('a.author')?.innerText||'unknown')};
 }).filter(x=>x.url&&x.title);
}'''


class Browsers:
    def __init__(self, root, db):
        self.root=Path(root); self.db=db; self.contexts={}; self.locks={}; self.playwright=None;self.manual=ManualLogin(root)
        with db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,platform TEXT,url TEXT,status TEXT DEFAULT 'needs_login',message TEXT DEFAULT '',retry_at REAL DEFAULT 0,last_success REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS visits(connection_id TEXT, source_id TEXT, at REAL);
            CREATE INDEX IF NOT EXISTS visits_time ON visits(at);
            CREATE TABLE IF NOT EXISTS seen(connection_id TEXT,url TEXT,at REAL,PRIMARY KEY(connection_id,url));''')
            for row in c.execute("SELECT id FROM connections WHERE status='login_open'").fetchall():
                if not self.manual.in_use(row[0]):c.execute("UPDATE connections SET status='needs_login', message='执行器已重启；请确认专用浏览器登录后恢复' WHERE id=?",(row[0],))
    def lock(self, cid): return self.locks.setdefault(cid,asyncio.Lock())
    def listing(self):
        with self.db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM connections')]
            day=dt.datetime.now(dt.timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            for row in rows:
                row['used_today']=c.execute('SELECT count(*) FROM visits WHERE connection_id=? AND at>=?',(row['id'],day)).fetchone()[0]
                row['daily_limit']=20; row['interval_hours']=6
                row['sources_next_at']={r[0]:r[1]+21600 for r in c.execute('SELECT source_id,max(at) FROM visits WHERE connection_id=? GROUP BY source_id',(row['id'],))}
                last=c.execute('SELECT max(at) FROM visits WHERE connection_id=?',(row['id'],)).fetchone()[0] or 0
                row['next_visit_at']=max(last+300, row['retry_at'], day+86400 if row['used_today']>=20 else 0)
            return rows
    def get(self,cid):
        with self.db() as c:
            r=c.execute('SELECT * FROM connections WHERE id=?',(cid,)).fetchone()
            if not r: raise ValueError('连接不存在')
            return dict(r)
    def create(self, platform, url):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import interests
        interests.validate_public_url(url,resolve=True)
        cid=identity(platform,url)
        with self.db() as c:
            c.execute('INSERT OR IGNORE INTO connections(id,platform,url) VALUES(?,?,?)',(cid,platform,url))
        return self.get(cid)
    def state(self,cid,status,message='',retry_at=0):
        with self.db() as c: c.execute('UPDATE connections SET status=?,message=?,retry_at=? WHERE id=?',(status,message,retry_at,cid))
    async def context(self,cid):
        if self.manual.in_use(cid):raise ValueError(LOGIN_MESSAGE)
        if cid in self.contexts:
            try:
                if self.contexts[cid].pages: return self.contexts[cid]
            except Exception: pass
            old=self.contexts.pop(cid,None)
            if old:
                try:await old.close()
                except Exception:pass
        if self.playwright is None:
            from playwright.async_api import async_playwright
            self.playwright=await async_playwright().start()
        profile=self.root/'profiles'/cid
        profile.mkdir(parents=True,exist_ok=True); profile.chmod(0o700)
        options=dict(headless=False,viewport={'width':1280,'height':900},accept_downloads=False)
        if sys.platform=='darwin':
            # Human login uses the real macOS keychain. Playwright's test keychain
            # cannot decrypt that profile's saved session on the next launch.
            options['ignore_default_args']=['--use-mock-keychain','--password-store=basic']
        ctx=await self.playwright.chromium.launch_persistent_context(str(profile),**options)
        self.contexts[cid]=ctx
        return ctx
    async def action(self,cid,action):
        async with self.lock(cid):
            row=self.get(cid)
            if action=='pause': self.state(cid,'paused','已手动暂停'); return self.get(cid)
            if action=='login':
                self.state(cid,'login_open',LOGIN_MESSAGE)
                if self.manual.in_use(cid):return self.get(cid)
                old=self.contexts.pop(cid,None)
                if old:await old.close()
                if self.playwright is None:
                    from playwright.async_api import async_playwright
                    self.playwright=await async_playwright().start()
                profile=self.root/'profiles'/cid;profile.mkdir(parents=True,exist_ok=True);profile.chmod(0o700)
                self.manual.open(cid,self.playwright.chromium.executable_path,profile,row['url'])
                return self.get(cid)
            if action in ('confirm','resume'):
                if self.manual.in_use(cid):raise ValueError(LOGIN_MESSAGE)
                ctx=await self.context(cid); page=ctx.pages[0]
                if urlsplit(page.url).hostname!=urlsplit(row['url']).hostname:
                    try:await page.goto(row['url'],wait_until='domcontentloaded',timeout=45000)
                    except Exception:
                        message='平台页面加载失败，请检查专用窗口和网络后确认恢复'
                        self.state(cid,'network_error',message)
                        raise ValueError(message) from None
                text=await page.locator('body').inner_text(timeout=15000)
                detect_block(text,page.url)
                # Confirm visible signed-in UI rather than trusting a button click.
                if row['platform']=='x':
                    try:await page.locator('[data-testid="SideNav_AccountSwitcher_Button"]').wait_for(state='visible',timeout=15000)
                    except Exception:raise ValueError('尚未检测到 X 已登录账号，请打开普通专用窗口完成登录') from None
                if row['platform']=='reddit':
                    logged_in=await page.locator('header a[href*="/user/"], #user-drawer-content a[href*="/user/"], form[action*="/logout"], .user .logout').count()
                    if not logged_in:
                        await page.bring_to_front()
                        raise ValueError('尚未检测到 Reddit 账号菜单，请在新打开的检查窗口展开个人菜单后再确认')
                self.state(cid,'ready','')
                return self.get(cid)
            raise ValueError('无效连接操作')
    def reserve(self,cid,sid):
        stamp=time.time(); day=dt.datetime.now(dt.timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=dict(c.execute('SELECT * FROM connections WHERE id=?',(cid,)).fetchone())
            if row['status']=='cooldown' and row['retry_at'] and row['retry_at']<=stamp:
                c.execute("UPDATE connections SET status='ready',message='' WHERE id=?",(cid,)); row['status']='ready'
            if row['status']!='ready': raise Paused(row['status'],row['message'] or '连接尚未就绪',row['retry_at'])
            recent=c.execute('SELECT max(at) FROM visits WHERE connection_id=? AND source_id=?',(cid,sid)).fetchone()[0]
            if recent and recent+21600>stamp: raise Paused('scheduled','尚未到下次巡检时间',recent+21600)
            count=c.execute('SELECT count(*) FROM visits WHERE connection_id=? AND at>=?',(cid,day)).fetchone()[0]
            if count>=20: raise Paused('budget','已达到每日20次巡检上限',day+86400)
            last=c.execute('SELECT max(at) FROM visits WHERE connection_id=?',(cid,)).fetchone()[0]
            if last and last+300>stamp: raise Paused('scheduled','账号巡检间隔至少5分钟',last+300)
            c.execute('INSERT INTO visits VALUES(?,?,?)',(cid,sid,stamp))
    async def collect(self,source):
        cid=source['connection_id']; row=self.get(cid)
        if identity(row['platform'],source['url'])!=cid: raise ValueError('来源与连接域名不匹配')
        async with self.lock(cid):
            try:
                self.reserve(cid,source['id'])
                ctx=await self.context(cid); page=ctx.pages[0] if ctx.pages else await ctx.new_page()
                url=source['url']
                if row['platform']=='reddit': url=url.rstrip('/')+'/new/' if not url.rstrip('/').endswith('/new') else url
                response=None
                for attempt in range(3):
                    try:
                        response=await page.goto(url,wait_until='domcontentloaded',timeout=45000)
                        await page.wait_for_timeout(2000)
                        text=await page.locator('body').inner_text(timeout=15000)
                        detect_block(text,page.url,response.status if response else 200,(await response.all_headers()).get('retry-after') if response else None)
                        break
                    except Paused: raise
                    except Exception:
                        if attempt==2: raise Paused('network_error','连接连续失败，请检查网络后恢复')
                        await asyncio.sleep(2**attempt*5)
                rows={}
                if row['platform'] in ('x','reddit'):
                    for scroll in range(3):
                        for item in await page.evaluate(POSTS_JS,row['platform']):
                            host=urlsplit(item['url']).hostname
                            if row['platform']=='x' and host not in ('x.com','www.x.com','twitter.com'): continue
                            if row['platform']=='x' and urlsplit(item['url']).path.split('/')[1].lower()!=urlsplit(source['url']).path.strip('/').split('/')[0].lower():continue
                            if row['platform']=='reddit' and host not in ('www.reddit.com','reddit.com','old.reddit.com'): continue
                            rows[item['url']]=item
                        if len(rows)>=20: break
                        if scroll<2:
                            await page.mouse.wheel(0,900); await asyncio.sleep(2)
                    if not rows:
                        empty=any(t in text.lower() for t in ('hasn’t posted','has not posted','no posts yet','还没有发布','there are no posts'))
                        if not empty: raise Paused('adapter_error','未识别到帖子结构，请检查页面；没有记为采集成功')
                else:
                    if not urlsplit(url).path.strip('/') or await page.locator('article').count()>1:
                        raise Paused('adapter_error','该入口是文章列表，请提供 RSS 或具体文章链接；没有将列表页归档为正文')
                    article=await page.locator('article, main [itemprop="articleBody"], .post-content, .entry-content').first.inner_text(timeout=15000)
                    if len(article)<200 or any(x in article.lower() for x in ('sign in to read','subscribe to continue','仅限会员','登录后阅读','付费解锁')):
                        raise Paused('needs_login','未取得完整正文，请登录或检查会员访问权限')
                    rows[url]=dict(url=url,title=await page.title(),body=article,excerpt=article[:1200],publisher=urlsplit(url).hostname)
                # Return seen posts as well to refresh Reddit retention. The database deduplicates.
                with self.db() as c:
                    for link in rows: c.execute('INSERT OR REPLACE INTO seen VALUES(?,?,?)',(cid,link,time.time()))
                    c.execute("UPDATE connections SET last_success=?,status='ready',message='' WHERE id=?",(time.time(),cid))
                return dict(rows=list(rows.values())[:20],status='成功',error='',next_at=time.time()+21600)
            except Paused as e:
                if e.status not in ('scheduled','budget'): self.state(cid,e.status,str(e),e.retry_at)
                labels={'needs_login':'待登录','login_open':'登录中','cooldown':'冷却中','challenge':'待验证','paused':'已暂停','adapter_error':'页面结构变化','network_error':'网络故障','scheduled':'等待调度','budget':'达到日上限'}
                return dict(rows=[],status=labels.get(e.status,e.status),error=str(e),next_at=e.retry_at)
            except Exception:
                self.state(cid,'adapter_error','浏览器或页面读取失败，请打开专用窗口检查')
                return dict(rows=[],status='页面读取失败',error='请检查专用浏览器并确认恢复')
    async def close(self):
        for ctx in self.contexts.values():
            try: await ctx.close()
            except Exception: pass
        if self.playwright: await self.playwright.stop()
