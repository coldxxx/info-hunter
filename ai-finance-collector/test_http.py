import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import radar

class HttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.p=patch.object(radar,'DB',Path(self.tmp.name)/'data'/'db.sqlite3');self.p.start();radar.init()
  self.server=radar.ThreadingHTTPServer(('127.0.0.1',0),radar.Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.base='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.p.stop();self.tmp.cleanup()
 def request(self,path,data=None,headers=None):
  req=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def test_import_search_bookmark_note_and_duplicate(self):
  item={'title':'HBM earnings 核验','url':'https://example.com/report','publisher':'Test','region':'韩国','excerpt':'AI revenue','kind':'研报'}
  self.assertEqual(self.request('import',item)['added'],1)
  a=self.request('articles?q=HBM&region='+urllib.parse.quote('韩国'))['items'][0]
  self.request('article',dict(a,starred=1,note='证据待核验',review='存疑'))
  self.assertEqual(self.request('import',item)['added'],0)
  found=self.request('articles?starred=1')['items']
  self.assertEqual(found[0]['note'],'证据待核验')
  self.assertEqual(self.request('articles?region='+urllib.parse.quote('日本'))['total'],0)
  self.assertEqual(self.request('status')['count'],1)
 def test_reject_cross_origin_and_invalid_url(self):
  with self.assertRaises(urllib.error.HTTPError) as error:
   self.request('import',{'title':'x','url':'https://example.com'}, {'Origin':'https://evil.example'})
  self.assertEqual(error.exception.code,403)
  with self.assertRaises(urllib.error.HTTPError) as error:
   self.request('import',{'title':'x','url':'javascript:alert(1)'})
  self.assertEqual(error.exception.code,400)
  self.assertEqual(self.request('status')['count'],0)

 def test_source_detail_endpoint_and_missing_source(self):
  result=self.request('source-detail?id=nvidia&watch_id=ai')
  self.assertEqual(result['source_id'],'nvidia')
  self.assertEqual(result['effective_adapter'],'rss')
  self.assertIn('steps',result)
  with self.assertRaises(urllib.error.HTTPError) as error:
   self.request('source-detail?id=missing')
  self.assertEqual(error.exception.code,404)

 def test_global_library_and_batch_follow_for_new_topic(self):
  topic=self.request('watch-topic',{'name':'Shared sources','keywords':'GPU','news_search':False})
  tid=topic['id']
  self.assertEqual(self.request('sources?watch_id='+tid),[])
  library=self.request('sources?all=1&watch_id='+tid)
  nvidia=next(s for s in library if s['id']=='nvidia')
  self.assertFalse(nvidia['followed'])
  self.assertIn('ai',{t['id'] for t in nvidia['topics']})
  self.assertEqual(self.request('watch-sources',{'watch_id':tid,'source_ids':['nvidia','coding-hn']})['added'],2)
  self.assertEqual({s['id'] for s in self.request('sources?watch_id='+tid)},{'nvidia','coding-hn'})
  shared=next(s for s in self.request('sources?all=1&watch_id=ai') if s['id']=='nvidia')
  self.assertEqual({t['id'] for t in shared['topics']},{'ai',tid})
  self.assertEqual(self.request('watch-sources',{'watch_id':tid,'source_ids':['nvidia']})['added'],0)
  self.request('watch-source',{'watch_id':tid,'source_id':'nvidia','follow':False})
  self.assertTrue(next(s for s in self.request('sources?watch_id=ai') if s['id']=='nvidia')['followed'])

 def test_global_source_can_be_saved_without_implicit_ai_binding(self):
  with patch.object(radar.interests,'discover',return_value={'url':'https://example.org/feed','name':'Shared feed','adapter':'rss','platform':'web','kind':'论坛'}):
   result=self.request('source',{'url':'https://example.org/feed','watch_id':None})
  source=next(s for s in self.request('sources?all=1&watch_id=coding-agent') if s['id']==result['source_id'])
  self.assertFalse(source['followed'])
  self.assertEqual(source['topics'],[])
  self.assertNotIn(source['id'],{s['id'] for s in self.request('sources?watch_id=ai')})

if __name__=='__main__':unittest.main()
