"""Pure HTML text and subscription parsing, independent of storage and workers."""
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET


class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.skip+=1
        if tag in ('p','br','div','li','h1','h2','h3'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def plain_text(html, *, parser_factory=None):
    parser=(Text if parser_factory is None else parser_factory)(); parser.feed(html)
    return '\n'.join(re.sub(r'\s+',' ',line).strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def gated(text):
    return any(x in text.lower() for x in ('sign in to read','subscribe to continue','this post is for paid subscribers','仅限会员','登录后阅读','付费解锁'))


def feed_extras(data, rows, *, to_text=None, is_gated=None):
    to_text = plain_text if to_text is None else to_text
    is_gated = gated if is_gated is None else is_gated
    root = ET.fromstring(data)
    local = lambda tag: tag.rsplit('}',1)[-1]
    by_url = {r['url']:r for r in rows}
    for item in root.iter():
        if local(item.tag) not in ('item','entry'): continue
        link = next((ch.get('href') or ''.join(ch.itertext()) for ch in item if local(ch.tag)=='link' and ch.get('rel','alternate')=='alternate'), '').strip()
        row=by_url.get(link)
        if row is None: continue
        media={}
        for ch in item:
            tag=local(ch.tag)
            if tag=='enclosure' or (tag=='link' and ch.get('rel')=='enclosure'):
                url=ch.get('url') or ch.get('href')
                if url and (ch.get('type','').startswith(('audio/','video/')) or (not ch.get('type') and re.search(r'\.(?:mp3|m4a|aac|wav|ogg|opus|mp4|webm)(?:[?]|$)',url,re.I))):
                    media.update(url=url, mime=ch.get('type',''), type='podcast')
            elif tag=='duration': media['duration']=''.join(ch.itertext())
            elif tag=='transcript' and ch.get('url'):
                media['transcript_url']=ch.get('url'); media['transcript_type']=ch.get('type','text/plain')
            elif tag=='videoId': media.update(type='youtube', video_id=ch.text)
        if 'youtube.com/watch' in link: media['type']='youtube'
        if media: row['media']=media
        # RSS content:encoded is a full body, description/summary may be an excerpt.
        full=next((''.join(ch.itertext()) for ch in item if local(ch.tag)=='encoded'), '')
        if full:
            text=to_text(full)
            if is_gated(text):row['body_error']='订阅仅提供会员预览；请连接该站点后获取全文'
            else:row['body']=text
    return rows


def opml_entries(text):
    """Read outline fields; the caller validates URLs and applies import limits."""
    root = ET.fromstring(text)
    return [dict(name=outline.get('text') or outline.get('title'), url=outline.get('xmlUrl'))
            for outline in root.iter('outline') if outline.get('xmlUrl')]
