"""Conservative semantic article extraction. Never archive login/paywall screens."""
from html.parser import HTMLParser
import re
import text_utils

class Article(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if not self.depth and (tag=='article' or attrs.get('id')=='js_content' or attrs.get('itemprop')=='articleBody' or any(x in attrs.get('class','').split() for x in ('entry-content','post-content','article-content','body','available-content'))):self.depth=1
        elif self.depth and tag not in ('br','img','hr','input','meta','link','source','wbr'):self.depth+=1
        if self.depth:
            if tag in ('script','style','nav','footer'):self.skip+=1
            if tag in ('p','br','div','h1','h2','li'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('br','img','hr','input','meta','link','source','wbr'):return
        if self.depth:
            if tag in ('script','style','nav','footer'):self.skip=max(0,self.skip-1)
            self.depth-=1
    def handle_data(self,data):
        if self.depth and not self.skip:self.parts.append(data)

def title(html):
    match=re.search(r'<title[^>]*>(.*?)</title>',html,re.S|re.I)
    return text_utils.plain_text(match[1]) if match else ''

def extract(html):
    parser=Article();parser.feed(html)
    text='\n'.join(re.sub(r'\s+',' ',p).strip() for p in ''.join(parser.parts).splitlines() if p.strip())
    if len(text)<200 or gated(text):
        raise ValueError('未取得完整正文；可能需要登录、会员权限或站点适配。没有保存登录页或付费提示。')
    return text

def gated(text):
    return text_utils.gated(text)
