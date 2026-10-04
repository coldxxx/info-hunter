import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from model_config import MODEL


class Jobs:
    def __init__(self,root,db):
        self.root=Path(root)/'jobs';self.root.mkdir(parents=True,exist_ok=True)
        self.db=db;self.lock=threading.Lock();self.stop=threading.Event();self.active=None
        with db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT,spec TEXT,result TEXT,error TEXT DEFAULT \'\',created_at REAL,updated_at REAL)')
            c.execute("UPDATE jobs SET status='queued' WHERE status='running'")
    def submit(self,spec,file=None):
        spec=dict(spec,model=MODEL,language=spec.get('language') or None)
        if spec['language'] not in (None,'zh','en'): raise ValueError('语言只支持自动、zh 或 en')
        if file:
            digest=hashlib.sha256()
            with open(file,'rb') as inp:
                for block in iter(lambda:inp.read(1024*1024),b''):digest.update(block)
            identity=digest.hexdigest()
        else:
            from transcribe import youtube_id
            identity=youtube_id(spec.get('url','')) or spec.get('media',{}).get('url') or spec.get('media',{}).get('transcript_url') or spec.get('url')
            if not identity: raise ValueError('没有媒体内容')
        ident=hashlib.sha256(json.dumps([identity,spec['model'],spec['language'],'segment-silence-v2'],sort_keys=True).encode()).hexdigest()[:32]
        with self.lock, self.db() as c:
            old=c.execute('SELECT status FROM jobs WHERE id=?',(ident,)).fetchone()
            if old and old[0]=='cancelled' and self.active==ident:
                raise ValueError('正在停止原任务，请稍后重试')
            if old and old[0] not in ('failed','cancelled'):
                if file: Path(file).unlink(missing_ok=True)
                return self.get(ident)
            folder=self.root/ident;folder.mkdir(exist_ok=True)
            for name in ('result.json','error.json','progress.json'): (folder/name).unlink(missing_ok=True)
            if file:
                target=folder/'upload.media';shutil.move(str(file),target);spec['file']=str(target)
            elif old:
                # Retry a previously uploaded task only when its cache still exists.
                previous=json.loads(c.execute('SELECT spec FROM jobs WHERE id=?',(ident,)).fetchone()[0])
                if previous.get('file'):spec['file']=previous['file']
            (folder/'spec.json').write_text(json.dumps(spec))
            c.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?,?,?)',(ident,'queued',json.dumps(spec),None,'',time.time(),time.time()))
        return self.get(ident)
    def get(self,ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('无效任务 ID')
        with self.db() as c:
            row=c.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
            if not row: raise ValueError('任务不存在')
            result=dict(row);result.pop('spec');result['result']=json.loads(result['result']) if result['result'] else None
            progress=self.root/ident/'progress.json'
            if progress.exists():
                try: result.update(json.loads(progress.read_text()))
                except (ValueError,OSError):pass
            if result['status']=='completed':result.update(progress=100,stage='处理完成')
            return result
    def cancel(self,ident):
        self.get(ident)
        with self.db() as c:
            c.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=? AND status IN ('queued','running')",(time.time(),ident))
        return self.get(ident)
    def cleanup(self):
        removed=0;cutoff=time.time()-7*86400
        with self.db() as c: rows=c.execute("SELECT id FROM jobs WHERE updated_at<? AND status IN ('completed','failed','cancelled')",(cutoff,)).fetchall()
        for row in rows:
            folder=self.root/row[0]
            if not folder.exists():continue
            for file in folder.iterdir():
                if file.name not in ('result.json','spec.json'):
                    if file.is_dir():shutil.rmtree(file)
                    else: removed+=file.stat().st_size;file.unlink()
        return removed
    def usage(self):
        used=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        return dict(bytes=used,free_bytes=shutil.disk_usage(self.root).free,retention_days=7)
    def worker(self):
        cleaned=0
        while not self.stop.wait(1):
            if time.time()-cleaned>3600:self.cleanup();cleaned=time.time()
            with self.lock, self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                if not row:continue
                ident=row[0];self.active=ident;c.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(time.time(),ident))
            folder=self.root/ident
            try:
                if shutil.disk_usage(folder).free < 2*1024**3:raise ValueError('磁盘剩余不足2 GB，请清理缓存')
                chunks=folder/'chunks'
                if chunks.exists():shutil.rmtree(chunks)
                with (folder/'worker.log').open('wb') as log:
                    proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('transcribe.py')),str(folder)],stdout=log,stderr=log,start_new_session=True)
                    started=time.time()
                    while proc.poll() is None:
                        if self.stop.wait(0.5) or self.get(ident)['status']=='cancelled' or time.time()-started>12*3600:
                            os.killpg(proc.pid,signal.SIGTERM)
                            try:proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                            break
                if self.stop.is_set():
                    with self.db() as c:c.execute("UPDATE jobs SET status='queued' WHERE id=? AND status='running'",(ident,))
                    return
                if self.get(ident)['status']=='cancelled':continue
                result=folder/'result.json'
                if proc.returncode==0 and result.exists():
                    payload=json.loads(result.read_text())
                    with self.db() as c:c.execute("UPDATE jobs SET status='completed',result=?,updated_at=? WHERE id=? AND status='running'",(json.dumps(payload,ensure_ascii=False),time.time(),ident))
                else:
                    error=folder/'error.json'
                    raise ValueError(json.loads(error.read_text())['error'] if error.exists() else '处理失败或超时，请重试')
            except Exception as e:
                with self.db() as c:c.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=? AND status='running'",(str(e)[:350],time.time(),ident))
            finally:
                with self.lock:self.active=None
