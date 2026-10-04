"""Private RPC to the native macOS worker. Never export its authentication key."""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error

def upload_file(path,language=''):
    """Stream multipart media to the same API used by independent HTTP clients."""
    import http.client,secrets,urllib.parse
    path=Path(path)
    if not path.is_file() or path.stat().st_size>512*1024*1024:raise ValueError('需要不超过512 MB的媒体文件')
    boundary='radar-'+secrets.token_hex(16)
    prefix=(f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="media"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    suffix=f'\r\n--{boundary}--\r\n'.encode()
    target=urllib.parse.urlsplit(base());conn=http.client.HTTPConnection(target.hostname,target.port,timeout=180)
    try:
        conn.putrequest('POST','/v1/transcription-jobs');conn.putheader('Authorization','Bearer '+key())
        conn.putheader('Content-Type','multipart/form-data; boundary='+boundary);conn.putheader('Content-Length',str(len(prefix)+path.stat().st_size+len(suffix)));conn.endheaders();conn.send(prefix)
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):conn.send(chunk)
        conn.send(suffix);r=conn.getresponse();result=json.loads(r.read(1_000_000))
        if r.status!=200:raise ValueError(result.get('detail','上传失败'))
        return result
    finally:conn.close()


def base():
    return os.environ.get('RADAR_NATIVE_URL', 'http://host.docker.internal:43202' if os.environ.get('RADAR_DATA_DIR') == '/data' else 'http://127.0.0.1:43202')


def key():
    root = Path(os.environ.get('RADAR_DATA_DIR', str(Path(__file__).parent / 'data')))
    try:
        return (root / 'native' / 'token').read_text().strip()
    except FileNotFoundError:
        raise ValueError('本机执行器尚未启动，请运行 native/start.sh') from None


def call(path, body=None, timeout=15):
    req = urllib.request.Request(base() + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + key(), 'Content-Type': 'application/json'})
    # Internal endpoint is configured by the operator, never by a source URL.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read(10000)).get('detail', '本机执行器请求失败')
        except (ValueError, UnicodeError):
            detail = '本机执行器请求失败'
        raise ValueError(str(detail)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('本机执行器未连接；请检查 native/start.sh 是否运行') from None

# Read-only connection snapshots for lists; avoids launching a browser or probing a platform.
_snapshot = (0, {})
def snapshot():
    global _snapshot
    import time
    if _snapshot[0]+5>time.time():return _snapshot[1]
    try:result={r['id']:r for r in call('/v1/connections',timeout=2)['items']}
    except ValueError:result={}
    _snapshot=(time.time(),result)
    return result
