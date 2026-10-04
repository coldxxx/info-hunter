import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch,MagicMock
import radar
import translation as t

class TranslationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(radar,'DB',Path(self.tmp.name)/'db.sqlite3');self.p.start()
  self.env=patch.dict(t.os.environ,{'RADAR_TRANSLATION_MODEL':'test-gemma','RADAR_TRANSLATION_URL':'http://127.0.0.1:1234/v1'});self.env.start();radar.init()
  self.a={'id':'a','title':'半導体の売上高は20%増加','excerpt':'AI投資は100億円。','language':'ja'}
 def tearDown(self):self.env.stop();self.p.stop();self.tmp.cleanup()
 def test_translation_detection_does_not_translate_chinese(self):
  self.assertEqual(t.language(self.a)[1],'ja')
  self.assertEqual(t.language({'title':'매출 증가','excerpt':'','language':'未知'})[1],'ko')
  self.assertIsNone(t.language({'title':'半导体营收','excerpt':'','language':'zh'}))
 def test_queue_dedup_and_content_change(self):
  q=queue.Queue(200);worker=MagicMock();worker.is_alive.return_value=True
  with patch.object(t,'JOBS',q),patch.object(t,'WORKER',worker):
   self.assertEqual(t.enqueue(radar.connect,[self.a]),1)
   self.assertEqual(t.enqueue(radar.connect,[self.a]),0)
   with patch.object(t,'translate_text',side_effect=['半导体营收增长20%','AI投资100亿日元。']):t.process(radar.connect,self.a,'test-gemma')
   with radar.connect() as c:self.assertEqual(t.cached(c,self.a)['title'],'半导体营收增长20%')
   self.assertEqual(t.enqueue(radar.connect,[self.a]),0)
   changed=dict(self.a,title='新しい見通し')
   with radar.connect() as c:self.assertEqual(t.cached(c,changed)['status'],'待翻译')
   self.assertEqual(t.enqueue(radar.connect,[changed]),1)
 def test_failed_translation_retains_original_and_can_retry(self):
  q=queue.Queue(200);worker=MagicMock();worker.is_alive.return_value=True
  with patch.object(t,'JOBS',q),patch.object(t,'WORKER',worker):
   t.enqueue(radar.connect,[self.a])
   with patch.object(t,'translate_text',side_effect=OSError('offline')):t.process(radar.connect,self.a,'test-gemma')
   with radar.connect() as c:self.assertEqual(t.cached(c,self.a)['status'],'失败')
   self.assertEqual(t.enqueue(radar.connect,[self.a]),0)
   self.assertEqual(t.enqueue(radar.connect,[self.a],retry=True),1)
   self.assertEqual(self.a['title'],'半導体の売上高は20%増加')
 def test_official_prompt_and_truncation_rejected(self):
  response=MagicMock();response.__enter__.return_value=response
  response.read.return_value=json.dumps({'choices':[{'text':'译文','finish_reason':'stop'}]}).encode()
  opener=MagicMock();opener.open.return_value=response
  with patch.object(t.urllib.request,'build_opener',return_value=opener):
   self.assertEqual(t.translate_text('売上',('Japanese','ja')),'译文')
   body=json.loads(opener.open.call_args.args[0].data)
   self.assertTrue(body['prompt'].startswith('<bos><start_of_turn>user\n'))
   self.assertTrue(body['prompt'].endswith('<start_of_turn>model\n'))
   self.assertIn('(zh-Hans)',body['prompt'])
   self.assertIn('\n\n\n売上',body['prompt'])
   response.read.return_value=json.dumps({'choices':[{'text':'半句','finish_reason':'length'}]}).encode()
   with self.assertRaises(ValueError):t.translate_text('売上20%',('Japanese','ja'))
 def test_financial_numbers_and_units_are_protected(self):
  protected,values=t.protect_numbers('売上20%増。100億円。100억 원。')
  self.assertNotIn('100',protected)
  self.assertIn('100亿日元',values.values())
  self.assertTrue(any('韩元' in v and '100' in v for v in values.values()))
  opener=MagicMock();response=MagicMock();response.__enter__.return_value=response;opener.open.return_value=response
  response.read.return_value=json.dumps({'choices':[{'text':'销售额增长ZXQNUM0000ZXQ。投资ZXQNUM0001ZXQ。','finish_reason':'stop'}]}).encode()
  with patch.object(t.urllib.request,'build_opener',return_value=opener):
   self.assertEqual(t.translate_text('売上20%増。投資100億円。',('Japanese','ja')),'销售额增长20%。投资100亿日元。')
   response.read.return_value=json.dumps({'choices':[{'text':'销售额增长10%。投资1亿日元。','finish_reason':'stop'}]}).encode()
   with self.assertRaises(ValueError):t.translate_text('売上20%増。投資100億円。',('Japanese','ja'))
 def test_restart_recovers_jobs(self):
  worker=MagicMock();worker.is_alive.return_value=True
  with patch.object(t,'JOBS',queue.Queue(200)),patch.object(t,'WORKER',worker):t.enqueue(radar.connect,[self.a])
  with radar.connect() as c:t.recover(c)
  with radar.connect() as c:self.assertEqual(t.cached(c,self.a)['status'],'失败')

if __name__=='__main__':unittest.main()
