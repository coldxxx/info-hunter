import json
import unittest
from unittest.mock import patch
import radar
import source_details
import test_radar
import watchlists
import interests


class SourceDetailTests(unittest.TestCase):
    setUp = test_radar.RadarTests.setUp
    tearDown = test_radar.RadarTests.tearDown

    def test_shared_schedule_and_url_dedup_counts(self):
        with radar.connect() as c:
            watchlists.bind(c, 'coding-agent', 'nvidia', True)
            interests.signal(c, 'nvidia', 'prefer', 'prefer', topic_id='coding-agent')
            source = json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            article = {'title': 'NVIDIA SDK tool calling workflow', 'url': 'https://example.com/sdk?utm_source=a', 'excerpt': 'API implementation'}
            radar.put(c, source, article)
            radar.put(c, source, dict(article, url='https://example.com/sdk'))
            row = dict(c.execute("SELECT * FROM sources WHERE id='nvidia'").fetchone())
            result = source_details.describe(c, row, 'ai')
            self.assertEqual(result['stats']['archived'], 1)
            self.assertEqual(result['schedule']['interval_hours'], 12)
            self.assertFalse(result['schedule']['baseline'])
            self.assertEqual(len(result['recent']), 1)
            self.assertEqual({t['id'] for t in result['topics']}, {'ai', 'coding-agent'})
            c.execute("INSERT INTO source_controls VALUES('nvidia',0)")
            self.assertFalse(source_details.describe(c, row, 'ai')['schedule']['enabled'])

    def test_latest_result_is_for_this_source(self):
        with radar.connect() as c:
            for result in [[{'source': 'nvidia', 'status': '成功', 'found': 12, 'added': 2, 'error': ''}], [{'source': 'coding-hn', 'status': '成功', 'found': 3, 'added': 1, 'error': ''}]]:
                c.execute('INSERT INTO runs(started_at,finished_at,result) VALUES(?,?,?)', (radar.now(), radar.now(), json.dumps(result)))
            row = dict(c.execute("SELECT * FROM sources WHERE id='nvidia'").fetchone())
            self.assertEqual(source_details.describe(c, row)['last_run']['added'], 2)

    def test_authorized_connector_selection_and_no_secrets_or_network(self):
        secret = 'private-test-token'
        with radar.connect() as c:
            row = dict(c.execute("SELECT * FROM sources WHERE id='x-ai'").fetchone())
            source = json.loads(row['config'])
            source.update(user_added=True, platform='x', adapter='browser')
            row['config'] = json.dumps(source)
            with patch.object(radar.social, 'settings', return_value={'x': {'enabled': True, 'bearer_token': secret}}), patch.object(radar.social, 'request_json') as request:
                result = source_details.describe(c, row)
                self.assertEqual(result['effective_adapter'], 'x')
                self.assertTrue(result['access']['ready'])
                self.assertNotIn(secret, json.dumps(result))
                request.assert_not_called()
            with patch.object(radar.social, 'settings', return_value={'x': {'enabled': False, 'bearer_token': secret}}):
                result = source_details.describe(c, row)
                self.assertEqual(result['effective_adapter'], 'browser')
                self.assertFalse(result['access']['ready'])

    def test_manual_path_does_not_claim_feed_fetch(self):
        with radar.connect() as c:
            row = dict(c.execute("SELECT * FROM sources WHERE id='nvidia'").fetchone())
            source = json.loads(row['config']); source['adapter'] = 'manual'; row['config'] = json.dumps(source)
            result = source_details.describe(c, row)
            self.assertFalse(result['access']['ready'])
            self.assertFalse(any(s['title'] == '读取公开订阅' for s in result['steps']))

    def test_reddit_browser_and_api_explain_shared_quality_gate(self):
        with radar.connect() as c:
            row=dict(c.execute("SELECT * FROM sources WHERE id='reddit-local'").fetchone())
            for adapter in ('reddit','browser-auto'):
                source=json.loads(row['config']);source['adapter']=adapter;source['platform']='reddit'
                row['config']=json.dumps(source)
                result=source_details.describe(c,row)
                gate=next(step for step in result['steps'] if step['title']=='Reddit 内容门槛')
                self.assertIn('10 条评论',gate['detail'])
                self.assertIn('不读取评论树',gate['detail'])
    def test_wechat_flow_uses_cached_feed_and_bridge_recovery(self):
        with radar.connect() as c:
            source=dict(url='https://mp.weixin.qq.com/s/example',name='公众号',adapter='wechat-rss',platform='wechat',kind='公众号',bridge_feed='http://127.0.0.1:43203/feed/MP_WXS_1234567890.rss')
            saved=interests.register(c,source,source['url'],radar.canonical,'ai',False)
            row=dict(c.execute('SELECT * FROM sources WHERE id=?',(saved['source_id'],)).fetchone())
            result=source_details.describe(c,row,'ai')
            self.assertEqual(result['entry_url'],source['bridge_feed'])
            self.assertEqual(result['schedule']['interval_hours'],12)
            self.assertIn('is_update=false',next(s['detail'] for s in result['steps'] if s['title']=='读取本机缓存'))
            self.assertIn('扫码',next(s['detail'] for s in result['steps'] if s['title']=='上游更新与恢复'))


if __name__ == '__main__':
    unittest.main()
