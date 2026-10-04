"""One cancellable subprocess per media job; bounded 10-minute ASR chunks."""
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import time
import wave
import urllib.request
import urllib.parse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import interests
import content_store
from model_config import model_path


def download(url, path, maximum=512*1024*1024):
    interests.validate_public_url(url,resolve=True)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            interests.validate_public_url(newurl,resolve=True)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    req=urllib.request.Request(url,headers={'User-Agent':'SignalRadar/1.0 (personal reader)'})
    total=0
    with urllib.request.build_opener(Redirect()).open(req,timeout=30) as r, open(path,'wb') as out:
        if int(r.headers.get('Content-Length',0))>maximum: raise ValueError('媒体超过512 MB限制，请上传精简音轨')
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>maximum: raise ValueError('文件超过大小限制')
            out.write(chunk)
    return Path(path)


def seconds(value):
    result=0.0
    for x in value.replace(',','.').split(':'): result=result*60+float(x)
    return result


def transcript(text, mime=''):
    segments=[]
    if 'json' in mime or text.lstrip().startswith('{'):
        obj=json.loads(text)
        if 'events' in obj:
            segments=[dict(start=e.get('tStartMs',0)/1000,end=(e.get('tStartMs',0)+e.get('dDurationMs',0))/1000,text=''.join(s.get('utf8','') for s in e.get('segs',[])).strip()) for e in obj['events'] if e.get('segs')]
        else:
            segments=[dict(start=float(s['startTime']),end=float(s['endTime']),text=s['body']) for s in obj.get('segments',[])]
    elif '-->' in text:
        pattern=r'([\d:,\.]+)\s+-->\s+([\d:,\.]+)[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
        segments=[dict(start=seconds(a),end=seconds(b),text=content_store.plain_text(t)) for a,b,t in re.findall(pattern,text,re.S)]
    if segments:
        segments=[s for s in segments if s['text']]
        return {'text':'\n'.join(s['text'] for s in segments),'segments':segments}
    text=content_store.plain_text(text) if '<' in text else text.strip()
    if not text: raise ValueError('文字稿为空')
    return {'text':text,'segments':[]}


def youtube_id(url):
    p=urllib.parse.urlsplit(url)
    if p.hostname in ('youtu.be','www.youtu.be'): value=p.path.strip('/')
    elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
        value=urllib.parse.parse_qs(p.query).get('v',[''])[0]
        if not value and p.path.startswith(('/shorts/','/live/')): value=p.path.split('/')[2]
    else: return None
    return value if re.fullmatch(r'[A-Za-z0-9_-]{11}',value or '') else None


def prepare(spec, folder, progress):
    if spec.get('file'): return Path(spec['file']),None
    media=spec.get('media',{})
    if media.get('transcript_url'):
        try:
            path=download(media['transcript_url'],folder/'publisher-transcript.txt',20*1024*1024)
            result=transcript(path.read_text(),media.get('transcript_type',''))
            result['origin']='publisher-transcript'; return None,result
        except Exception:
            if not media.get('url'): raise ValueError('节目文字稿不可用，且未提供音频；请上传媒体文件') from None
    vid=youtube_id(spec.get('url',''))
    if vid:
        from yt_dlp import YoutubeDL
        def bounded_download(event):
            if event.get('downloaded_bytes',0)>512*1024*1024:raise ValueError('音轨超过512 MB限制')
            import shutil
            if shutil.disk_usage(folder).free<1024**3:raise ValueError('磁盘不足，请清理媒体缓存')
        class Quiet:
            def debug(self,*args): pass
            def warning(self,*args): pass
            def error(self,*args): pass
        opts={'quiet':True,'logger':Quiet(),'noplaylist':True,'socket_timeout':25,'retries':2,'fragment_retries':2,'format':'bestaudio/best','outtmpl':str(folder/'audio.%(ext)s'),'max_filesize':512*1024*1024,'progress_hooks':[bounded_download],'js_runtimes':{'node':{}},'allowed_extractors':['youtube']}
        url='https://www.youtube.com/watch?v='+vid
        with YoutubeDL(opts) as ydl:
            try: info=ydl.extract_info(url,download=False)
            except Exception: raise ValueError('YouTube 媒体不可获取；可能需要验证或受到访问限制。可上传已有音频，不会自动使用日常账号。') from None
            for field,origin in (('subtitles','manual-caption'),('automatic_captions','automatic-caption')):
                tracks=info.get(field) or {}
                keys=sorted(tracks,key=lambda k:(not k.startswith(('zh','en')),k!=info.get('language'),k))
                for language in keys[:3]:
                    formats=sorted(tracks[language],key=lambda t: {'json3':0,'vtt':1,'srt':2}.get(t.get('ext'),9))
                    track=next((t for t in formats if t.get('ext') in ('json3','vtt','srt')),None)
                    if not track: continue
                    try:
                        path=download(track['url'],folder/'captions.txt',20*1024*1024)
                        result=transcript(path.read_text(),'json' if track['ext']=='json3' else track['ext']);result['origin']=origin
                        return None,result
                    except Exception: continue
            progress(10,'下载音轨')
            try:
                info=ydl.extract_info(url,download=True)
                path=Path(ydl.prepare_filename(info))
                if not path.exists(): raise ValueError('missing media')
                return path,None
            except Exception: raise ValueError('YouTube 音轨下载失败；任务已停止，可改为上传已有媒体文件') from None
    if media.get('url'):
        return download(media['url'],folder/'audio.media'),None
    raise ValueError('没有可用音频地址；请导入单集 RSS 或上传媒体文件')


def decode_audio(command, chunks, maximum=2*1024**3):
    """Stop the decoder before corrupt/very long media exhausts the disk."""
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    started=time.monotonic()
    try:
        while True:
            status=process.poll()
            size=sum(file.stat().st_size for file in chunks.glob('*.wav'))
            if size>maximum:raise ValueError('解码音频超过2 GB，请分成较短的媒体后上传')
            if shutil.disk_usage(chunks).free<1024**3:raise ValueError('磁盘不足，音频解码已停止；请清理媒体缓存')
            if status is not None:
                if status:raise ValueError('媒体解码失败')
                return
            if time.monotonic()-started>1800:raise ValueError('媒体解码超过处理时限')
            time.sleep(.2)
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run(spec, folder):
    import imageio_ffmpeg
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    binary=folder/'bin';binary.mkdir(exist_ok=True)
    link=binary/'ffmpeg'
    if not link.exists():link.symlink_to(ffmpeg)
    os.environ['PATH']=str(binary)+os.pathsep+os.environ.get('PATH','')
    def progress(percent,stage):
        tmp=folder/'progress.tmp';tmp.write_text(json.dumps(dict(progress=percent,stage=stage)));tmp.replace(folder/'progress.json')
    progress(2,'检查文字稿')
    path,result=prepare(spec,folder,progress)
    if result: return result
    progress(15,'音频分段')
    chunks=folder/'chunks';chunks.mkdir(exist_ok=True)
    # Each chunk is at most 600 seconds (19 MB PCM), never one enormous decoded array.
    command=[ffmpeg,'-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-f','segment','-segment_time','600','-reset_timestamps','1',str(chunks/'%05d.wav')]
    decode_audio(command,chunks)
    files=sorted(chunks.glob('*.wav'))
    if not files: raise ValueError('媒体没有音轨')
    import mlx_whisper
    cached_model=model_path()
    result={'text':'','segments':[],'origin':'local-asr','model':spec['model']}
    offset=0
    for i,file in enumerate(files):
        progress(20+int(i/len(files)*75),f'转写第 {i+1}/{len(files)} 段')
        import numpy as np
        with wave.open(str(file)) as w:
            rate=w.getframerate(); duration=w.getnframes()/rate
            pcm=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16)
        # Discard only near-digital silence (-66 dBFS), with 400 ms speech margins.
        # Whisper can hallucinate repeated text when a short utterance is padded with silence.
        active=np.flatnonzero(np.abs(pcm.astype(np.int32))>16)
        if not len(active):
            offset+=duration;file.unlink();continue
        left=max(0,int(active[0])-int(rate*.4));right=min(len(pcm),int(active[-1])+int(rate*.4)+1)
        audio=pcm[left:right].astype(np.float32)/32768.0
        part=mlx_whisper.transcribe(audio,path_or_hf_repo=str(cached_model),language=spec.get('language') or None,condition_on_previous_text=False,verbose=False)
        for segment in part['segments']:
            if segment.get('no_speech_prob',0)>0.8 and segment.get('avg_logprob',0)<-1: continue
            a=max(0,int(segment['start']*rate));b=min(len(audio),int(segment['end']*rate))
            if b<=a or float(np.max(np.abs(audio[a:b])))<16/32768:continue
            result['segments'].append(dict(start=round(offset+left/rate+segment['start'],3),end=round(min(offset+duration,offset+left/rate+segment['end']),3),text=segment['text'].strip()))
        offset+=duration; file.unlink()
    result['text']='\n'.join(s['text'] for s in result['segments'])
    result['duration']=offset
    return result


if __name__=='__main__':
    folder=Path(sys.argv[1]);spec=json.loads((folder/'spec.json').read_text())
    try:
        result=run(spec,folder)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        (folder/'error.json').write_text(json.dumps({'error':str(e)[:350]},ensure_ascii=False))
        sys.exit(1)
