"""Read the permitted local We-MP-RSS cache without triggering upstream work."""
import re
import urllib.parse
import urllib.request


def read_feed(body):
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
