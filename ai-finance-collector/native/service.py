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
import state as native_state
import wechat_bridge
import media_api

ROOT=Path(os.environ.get('RADAR_NATIVE_DATA',str(Path(__file__).resolve().parents[1]/'data'/'native')))
TOKEN_PATH,TOKEN=native_state.prepare(ROOT)
os.environ.setdefault('HF_HOME',str(ROOT/'models'))
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'browsers'))

def db():
    return native_state.open_database(ROOT)

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
    return await media_api.upload(file, language, ROOT, jobs)
@app.post('/v1/media-jobs')
def media(body:dict):
    return media_api.submit(body, jobs)
@app.get('/v1/transcription-jobs/{ident}')
def status(ident:str):return jobs.get(ident)
@app.post('/v1/transcription-jobs/{ident}/cancel')
def cancel(ident:str):return jobs.cancel(ident)
@app.post('/v1/cache/cleanup')
def cleanup():return dict(removed_bytes=jobs.cleanup(),storage=jobs.usage())
@app.post('/v1/wechat/feed')
def wechat_feed(body:dict):
    return wechat_bridge.read_feed(body)
