"""Bounded native media intake; jobs and storage are supplied by the service."""
import os
from pathlib import Path
import tempfile


async def upload(file, language, root, jobs):
    fd,name=tempfile.mkstemp(dir=root,suffix='.upload');os.close(fd)
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


def submit(body, jobs):
    from transcribe import youtube_id
    from interests import validate_public_url
    media=body.get('media') or {}
    if not isinstance(media,dict):raise ValueError('无效媒体')
    for key in ('url','transcript_url'):
        if media.get(key):validate_public_url(media[key],resolve=True)
    if not media.get('url') and not media.get('transcript_url') and not youtube_id(body.get('url','')):raise ValueError('没有可用音轨；请上传媒体文件')
    return jobs.submit({'url':body.get('url',''),'media':media,'language':body.get('language')})
