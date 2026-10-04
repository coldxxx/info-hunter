"""Native companion: authenticated loopback API, isolated browsers and reusable ASR."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
import re
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sqlite3
import tempfile
import threading
import urllib.parse
import urllib.request
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from browser_worker import Browsers, Paused
from jobs import Jobs

ROOT=Path(os.environ.get('RADAR_NATIVE_DATA',str(Path(__file__).resolve().parents[1]/'data'/'native')))
ROOT.mkdir(parents=True,exist_ok=True);ROOT.chmod(0o700)
os.environ.setdefault('HF_HOME',str(ROOT/'models'))
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'browsers'))
TOKEN_PATH=ROOT/'token'
if not TOKEN_PATH.exists():
    fd=os.open(TOKEN_PATH,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as out:out.write(secrets.token_urlsafe(48))
TOKEN=TOKEN_PATH.read_text().strip()

def db():
    c=sqlite3.connect(ROOT/'native.sqlite3',timeout=30);c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL');return c

browsers=Browsers(ROOT,db); jobs=Jobs(ROOT,db)
@asynccontextmanager
async def lifespan(app):
    thread=threading.Thread(target=jobs.worker,daemon=True);thread.start()
    yield
    jobs.stop.set();await browsers.close();thread.join(timeout=10)

app=FastAPI(title='Signal Radar Native',version='1.0',lifespan=lifespan,docs_url=None,redoc_url=None)
@app.middleware('http')
async def auth(request: Request, call_next):
    supplied=request.headers.get('authorization','')
    if not secrets.compare_digest(supplied,'Bearer '+TOKEN):return JSONResponse({'detail':'需要本机访问令牌'},status_code=401)
    if request.headers.get('origin'):return JSONResponse({'detail':'请通过信息雷达或本地客户端访问'},status_code=403)
    try:return await call_next(request)
    except ValueError as e:return JSONResponse({'detail':str(e)},status_code=400)

@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)
@app.exception_handler(KeyError)
async def missing_field(request,exc):return JSONResponse({'detail':'缺少必要字段'},status_code=400)
@app.exception_handler(Paused)
async def paused_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=409)

@app.get('/v1/health')
def health():return {'ready':True,'model':'mlx-community/whisper-large-v3-turbo','storage':jobs.usage()}
@app.get('/v1/connections')
def listing():return {'items':browsers.listing(),'storage':jobs.usage()}
@app.post('/v1/connections')
def create(body:dict):return browsers.create(body['platform'],body['url'])
@app.post('/v1/connections/{cid}/{action}')
async def action(cid:str,action:str):return await browsers.action(cid,action)
@app.post('/v1/browser/collect')
async def collect(body:dict):return await browsers.collect(body)
@app.post('/v1/transcription-jobs')
async def upload(file:UploadFile=File(...),language:str=Form('')):
    fd,name=tempfile.mkstemp(dir=ROOT,suffix='.upload');os.close(fd)
    try:
        size=0
        with open(name,'wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>512*1024*1024:raise ValueError('文件不能超过512 MB')
                out.write(chunk)
        if not size:raise ValueError('文件为空')
        return jobs.submit({'language':language},name)
    finally:
        Path(name).unlink(missing_ok=True)
        await file.close()
@app.post('/v1/media-jobs')
def media(body:dict):
    from transcribe import youtube_id
    from interests import validate_public_url
    media=body.get('media') or {}
    if not isinstance(media,dict):raise ValueError('无效媒体')
    for key in ('url','transcript_url'):
        if media.get(key):validate_public_url(media[key],resolve=True)
    if not media.get('url') and not media.get('transcript_url') and not youtube_id(body.get('url','')):raise ValueError('没有可用音轨；请上传媒体文件')
    return jobs.submit({'url':body.get('url',''),'media':media,'language':body.get('language')})
@app.get('/v1/transcription-jobs/{ident}')
def status(ident:str):return jobs.get(ident)
@app.post('/v1/transcription-jobs/{ident}/cancel')
def cancel(ident:str):return jobs.cancel(ident)
@app.post('/v1/cache/cleanup')
def cleanup():return dict(removed_bytes=jobs.cleanup(),storage=jobs.usage())
@app.post('/v1/wechat/feed')
def wechat_feed(body:dict):
    url=body.get('url','');p=urllib.parse.urlsplit(url)
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost') or p.port!=43203 or p.username or p.password:
        raise ValueError('公众号桥接订阅必须来自 http://127.0.0.1:43203')
    if not re.fullmatch(r'/(?:api/v1/wx/)?feed/[A-Za-z0-9_-]+\.(rss|xml|atom)',p.path):raise ValueError('请使用公众号桥接的 /feed/… .rss 或 .xml 订阅地址')
    query=dict(urllib.parse.parse_qsl(p.query));query['is_update']='false'
    url=urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(query),''))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(url,timeout=30) as r:
            raw=r.read(32_000_001)
            if len(raw)>32_000_000:raise ValueError('订阅超过32 MB')
            return {'feed':raw.decode('utf-8')}
    except Exception:raise ValueError('公众号桥接未连接或订阅不可用，请检查扫码授权与订阅地址') from None
