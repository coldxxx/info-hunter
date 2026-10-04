"""Human-only browser sessions sharing the collector's isolated profile."""
import json
import os
from pathlib import Path
import subprocess


MESSAGE='请在普通专用窗口完成登录；随后关闭该平台的所有登录窗口，再点击确认登录'


class ManualLogin:
    def __init__(self,root):
        self.file=Path(root)/'manual-logins.json';self.children={}
        try:self.records=json.loads(self.file.read_text())
        except (OSError,ValueError):self.records={}
        if not isinstance(self.records,dict):self.records={}

    def save(self):
        tmp=self.file.with_suffix('.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:json.dump(self.records,out)
        tmp.replace(self.file)

    def in_use(self,cid):
        record=self.records.get(cid)
        if not record:return False
        child=self.children.get(cid)
        if child is not None:
            alive=child.poll() is None
        else:
            # Only inspect the saved PID's command, never cookies or profile contents.
            try:
                pid=int(record['pid'])
                if pid<=0:raise ValueError('invalid PID')
                command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=3).stdout.strip()
                alive=command.startswith(record['executable']) and ('--user-data-dir='+record['profile']) in command
            except (KeyError,ValueError,OSError,subprocess.TimeoutExpired):alive=False
        if not alive:
            self.records.pop(cid,None);self.children.pop(cid,None);self.save()
        return alive

    def open(self,cid,executable,profile,url):
        if self.in_use(cid):return
        command=[str(executable),'--user-data-dir='+str(profile),'--no-first-run','--no-default-browser-check','--new-window',url]
        child=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        self.children[cid]=child
        self.records[cid]=dict(pid=child.pid,executable=str(executable),profile=str(profile))
        self.save()
