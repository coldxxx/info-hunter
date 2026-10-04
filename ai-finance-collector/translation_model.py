"""Local TranslateGemma requests and financial-number integrity checks."""
import json
import os
import re
import urllib.request


def protect_numbers(text):
    values={}
    pattern=r'[-+−]?\d[\d,，]*(?:[.．]\d+)?(?:\s*(?:兆|億|亿|万|千|조|억|만|천))?(?:\s*(?:円|日元|ドル|달러|ウォン|원|韩元|美元|%|％))?'
    def replace(m):
        raw=m.group(0)
        # Only fixed written units are localized; no exchange-rate conversion.
        for before,after in [('億','亿'),('조','万亿'),('억','亿'),('만','万'),('천','千'),('ウォン','韩元'),('달러','美元'),('ドル','美元'),('円','日元'),('원','韩元')]:raw=raw.replace(before,after)
        token='ZXQNUM'+str(len(values)).zfill(4)+'ZXQ'
        values[token]=raw;return token
    return re.sub(pattern,replace,text),values


def translate_text(text, lang, *, model, protect_numbers):
    if not text:return ''
    protected,values=protect_numbers(text)
    chunks=[];start=0
    while start<len(protected):
        end=min(start+600,len(protected))
        for m in re.finditer(r'ZXQNUM[0-9]+ZXQ',protected):
            if m.start()<end<m.end():end=m.start();break
        chunks.append(protected[start:end]);start=end
    output=[]
    endpoint=os.environ.get('RADAR_TRANSLATION_URL','http://127.0.0.1:1234/v1').rstrip('/')+'/completions'
    for chunk in chunks:
        prompt=(f'You are a professional {lang[0]} ({lang[1]}) to Chinese (Simplified) (zh-Hans) translator. Your goal is to accurately convey the meaning and nuances of the original {lang[0]} text while adhering to Chinese (Simplified) grammar, vocabulary, and cultural sensitivities.\n'
                f'Produce only the Chinese (Simplified) translation, without any additional explanations or commentary. Please translate the following {lang[0]} text into Chinese (Simplified):\n\n\n{chunk}')
        # Use the raw endpoint: TranslateGemma's structured Jinja input is not
        # expressible through LM Studio's ordinary OpenAI chat-content schema.
        raw='<bos><start_of_turn>user\n'+prompt+'<end_of_turn>\n<start_of_turn>model\n'
        body=json.dumps({'model':model(),'prompt':raw,'temperature':0.1,'max_tokens':1800,'stop':['<end_of_turn>','<eos>'],'stream':False}).encode()
        req=urllib.request.Request(endpoint,data=body,headers={'Content-Type':'application/json'})
        # Local model calls must bypass the user's outbound HTTP proxy.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=120) as r:result=json.load(r)
        choice=result['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError('译文超出长度限制，未保存不完整译文')
        content=choice['text']
        if not isinstance(content,str) or not content.strip():raise ValueError('模型未返回译文')
        output.append(content.strip())
    result='\n'.join(output)
    for token in values:
        if result.count(token)!=1:raise ValueError('数值占位校验失败')
    residue=re.sub(r'ZXQNUM[0-9]+ZXQ','',result)
    if re.search(r'\d',residue):raise ValueError('译文新增了原文未提供的数字')
    for token,value in values.items():result=result.replace(token,value)
    return result
