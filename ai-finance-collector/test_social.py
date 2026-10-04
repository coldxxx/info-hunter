import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import social

class SocialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.db=Path(self.tmp.name)/'db.sqlite3'
  social.TOKEN.clear()
 def tearDown(self):
  social.TOKEN.clear();self.tmp.cleanup()
 def test_missing_approval_makes_no_request(self):
  with patch.object(social,'settings',return_value={}),patch.object(social,'request_json') as call:
   rows,status,_=social.collect({'adapter':'reddit'},self.db)
   self.assertEqual(status,'待审批');self.assertEqual(rows,[]);call.assert_not_called()
 def test_x_token_alone_does_not_authorize_spend(self):
  with patch.object(social,'settings',return_value={'x':{'bearer_token':'test-secret'}}),patch.object(social,'request_json') as call:
   self.assertEqual(social.collect({'adapter':'x'},self.db)[1],'待启用');call.assert_not_called()
 def test_reddit_refresh_and_public_post_mapping(self):
  cfg={'reddit':{'approved':True,'enabled':True,'client_id':'id','client_secret':'secret','refresh_token':'refresh','user_agent':'desktop:test:1 (by /u/test)'}}
  post={'data':{'children':[{'data':{'title':'GPU','selftext':'Revenue','author':'test','created_utc':1000,'permalink':'/r/LocalLLaMA/comments/abc/title/','num_comments':4,'url_overridden_by_dest':'https://arxiv.org/abs/1234.5678','link_flair_text':'Research'}},{'data':{'title':'removed','selftext':'[removed]'}}]}}
  with patch.object(social,'settings',return_value=cfg),patch.object(social,'request_json',side_effect=[{'access_token':'test-token','expires_in':3600},post]) as call:
   rows,status,_=social.collect({'adapter':'reddit','subreddit':'LocalLLaMA'},self.db)
   self.assertEqual(status,'成功');self.assertEqual(len(rows),1)
   self.assertTrue(rows[0]['url'].startswith('https://www.reddit.com/r/LocalLLaMA/comments/'))
   self.assertEqual(rows[0]['comment_count'],4)
   self.assertEqual(rows[0]['outbound_url'],'https://arxiv.org/abs/1234.5678')
   self.assertEqual(rows[0]['flair'],'Research')
   self.assertIn(b'grant_type=refresh_token',call.call_args_list[0].args[2])
   self.assertEqual(call.call_args_list[1].args[1]['Authorization'],'Bearer test-token')
 def test_x_reserves_daily_quota_even_on_timeout(self):
  cfg={'x':{'enabled':True,'bearer_token':'test-secret','max_results':10,'daily_requests':1}}
  with patch.object(social,'settings',return_value=cfg),patch.object(social,'request_json',side_effect=TimeoutError) as call:
   with self.assertRaises(TimeoutError):social.collect({'adapter':'x','query':'GPU'},self.db)
   self.assertEqual(social.collect({'adapter':'x','query':'GPU'},self.db)[1],'达到日上限')
   self.assertEqual(call.call_count,1)
 def test_shared_platform_cooldown_blocks_next_source(self):
  cfg={'reddit':{'approved':True,'enabled':True,'client_id':'id','client_secret':'s','user_agent':'test'}}
  with patch.object(social,'settings',return_value=cfg),patch.object(social,'request_json',side_effect=social.AccessIssue('限流等待','429',900)) as call:
   self.assertEqual(social.collect({'adapter':'reddit','subreddit':'stocks'},self.db)[1],'限流等待')
   self.assertEqual(social.collect({'adapter':'reddit','subreddit':'LocalLLaMA'},self.db)[1],'限流等待')
   self.assertEqual(call.call_count,1)
 def test_status_never_exposes_secrets(self):
  cfg={'x':{'bearer_token':'SECRET_VALUE'},'reddit':{'client_id':'SECRET_VALUE','client_secret':'SECRET_VALUE'}}
  with patch.object(social,'settings',return_value=cfg):
   self.assertNotIn('SECRET_VALUE',json.dumps(social.connection_status()))

if __name__=='__main__':unittest.main()
