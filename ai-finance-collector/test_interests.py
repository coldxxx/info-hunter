import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import interests
import radar
from test_http import HttpTests

FEED=b'<rss><channel><title>AI podcast</title><item><title>GPU discussion</title><link>https://example.org/episode</link><description>inference</description></item></channel></rss>'
CID='UC'+'a'*22

class InterestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(radar,'DB',Path(self.tmp.name)/'radar.db');self.p.start();radar.init()
    def tearDown(self):
        self.p.stop();self.tmp.cleanup()
    def add(self,url='https://example.org/feed.xml'):
        s=interests.discover(url,lambda _:FEED,radar.parse_feed,radar.canonical)
        with radar.connect() as c:return interests.register(c,s,url,radar.canonical)
    def test_author_identity_and_duplicate_share_reward(self):
        s=interests.identify('https://x.com/AUTHOR/status/123?utm_source=test')
        with radar.connect() as c:
            a=interests.register(c,s,'https://x.com/AUTHOR/status/123',radar.canonical)
            b=interests.register(c,s,'https://x.com/AUTHOR/status/123',radar.canonical)
            self.assertEqual(a['source_id'],b['source_id']);self.assertEqual(b['preference']['signals']['share'],1)
            d=interests.register(c,s,'https://x.com/author/status/456',radar.canonical)
            self.assertGreater(d['preference']['score'],b['preference']['score'])
        radar.init()
        with radar.connect() as c:self.assertTrue(c.execute('SELECT 1 FROM sources WHERE id=?',(a['source_id'],)).fetchone())
    def test_existing_reddit_is_not_duplicated(self):
        with radar.connect() as c:
            a=interests.register(c,interests.identify('https://reddit.com/r/localllama/comments/a/title'),'https://reddit.com/r/localllama/comments/a/title',radar.canonical)
            self.assertEqual(a['source_id'],'reddit-local');self.assertEqual(a['config']['adapter'],'browser')

    def test_cross_topic_reuse_preserves_verified_global_capture_config(self):
        import watchlists
        source={'url':'https://example.org/shared-feed','name':'Shared forum','adapter':'rss','platform':'web','kind':'论坛','feed_url':'https://example.org/shared-feed'}
        with radar.connect() as c:
            first=interests.register(c,source,source['url'],radar.canonical)
            topic=watchlists.save(c,{'name':'Another topic','keywords':'GPU','news_search':False})
            failed=dict(source,name='Another label',adapter='manual',note='temporary network error')
            second=interests.register(c,failed,source['url'],radar.canonical,topic['id'])
            self.assertEqual(first['source_id'],second['source_id'])
            self.assertEqual(second['config']['adapter'],'rss')
            self.assertEqual(second['config']['name'],'Shared forum')
            self.assertEqual(c.execute('SELECT count(*) FROM watch_sources WHERE source_id=?',(first['source_id'],)).fetchone()[0],2)

    def test_verified_feed_upgrade_keeps_original_global_source_identity(self):
        source={'url':'https://example.org/forum','name':'Forum','adapter':'manual','platform':'web','kind':'论坛'}
        with radar.connect() as c:
            first=interests.register(c,source,source['url'],radar.canonical,topic_id=None)
            upgraded=dict(source,url=source['url']+'/feed',feed_url=source['url']+'/feed',adapter='rss')
            second=interests.register(c,upgraded,source['url'],radar.canonical,topic_id='coding-agent')
            self.assertEqual(first['source_id'],second['source_id'])
            self.assertEqual(second['config']['adapter'],'rss')
    def test_feed_discovery_from_articles_groups_blog(self):
        def fetch(url):
            return FEED if url.endswith('/feed.xml') else b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        ids=[]
        with radar.connect() as c:
            for url in ['https://example.org/posts/a','https://example.org/posts/b']:
                s=interests.discover(url,fetch,radar.parse_feed,radar.canonical)
                self.assertEqual(s['feed_url'],'https://example.org/feed.xml')
                ids.append(interests.register(c,s,url,radar.canonical)['source_id'])
        self.assertEqual(ids[0],ids[1])
    def test_youtube_channel_and_video_map_to_same_feed(self):
        html=('<meta itemprop="channelId" content="'+CID+'">').encode()
        def fetch(url):return FEED if '/feeds/videos.xml' in url else html
        channels=[]
        for url in ['https://www.youtube.com/channel/'+CID,'https://www.youtube.com/@creator','https://youtu.be/video123']:
            s=interests.discover(url,fetch,radar.parse_feed,radar.canonical)
            self.assertEqual(s['adapter'],'rss');channels.append(s['url'])
        self.assertEqual(len(set(channels)),1)
    def test_feed_metadata_does_not_imply_played_or_verified(self):
        a=self.add()
        with radar.connect() as c:s=json.loads(c.execute('SELECT config FROM sources WHERE id=?',(a['source_id'],)).fetchone()[0])
        with patch.object(radar,'fetch',return_value=FEED),patch.object(radar,'backup',return_value='test'):
            radar.collect(a['source_id']);radar.collect(a['source_id'])
        with radar.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT review FROM articles').fetchone()[0],'未核验')
            self.assertEqual(interests.policy(c,a['source_id'])['signals'],{'share':1})
    def test_decay_and_feedback_do_not_reward_toggling(self):
        sid=self.add()['source_id'];at=dt.datetime.now(dt.timezone.utc)
        with radar.connect() as c:
            interests.signal(c,sid,'star:1','star',True)
            before=interests.policy(c,sid,at)['score']
            interests.signal(c,sid,'star:1','star',False);interests.signal(c,sid,'star:1','star',True)
            self.assertEqual(interests.policy(c,sid,at)['score'],before)
            later=interests.policy(c,sid,at+dt.timedelta(days=30))['score']
            self.assertAlmostEqual(later-10,(before-10)/2,places=2)
    def test_scheduler_budget_exploration_and_pause(self):
        sources=[]
        with radar.connect() as c:
            for i in range(12):
                a=interests.register(c,{'url':f'https://example.org/{i}/feed','name':str(i),'adapter':'rss','platform':'web','kind':'新闻'},f'https://example.org/{i}',radar.canonical)
                sid=a['source_id'];s=a['config'];sources.append(s)
                for j in range(i):interests.signal(c,sid,'star:'+str(j),'star')
            chosen=interests.plan(c,sources);self.assertEqual(len(chosen),8)
            self.assertIn(max(sources,key=lambda x:interests.policy(c,x['id'])['score'])['id'],[x['id'] for x in chosen])
            self.assertTrue(any(interests.policy(c,x['id'])['score']<30 for x in chosen))
            c.execute('INSERT INTO source_controls VALUES(?,0)',(chosen[0]['id'],))
            self.assertNotIn(chosen[0]['id'],[x['id'] for x in interests.plan(c,sources)])
            now=radar.now();c.execute('UPDATE sources SET checked_at=?',(now,))
            self.assertEqual(interests.plan(c,sources,scheduled=True),[])
    def test_private_urls_and_redirect_targets_rejected(self):
        for url in ['http://127.0.0.1/a','http://169.254.169.254/','http://localhost/a','http://10.0.0.1','http://example.org:8080/feed','https://user:pass@example.org/feed']:
            with self.assertRaises(ValueError):interests.validate_public_url(url)
        with patch.object(interests.socket,'getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
            with self.assertRaises(ValueError):interests.validate_public_url('https://example.org/feed',resolve=True)
    def test_fake_dns_is_opt_in_and_never_allows_literal_or_private_ip(self):
        dns=[(2,1,6,'',('198.18.0.133',443))]
        with patch.object(interests.socket,'getaddrinfo',return_value=dns),patch.dict(interests.os.environ,{'RADAR_FAKE_DNS':'0'}):
            with self.assertRaises(ValueError):interests.validate_public_url('https://example.org/feed',resolve=True)
        with patch.object(interests.socket,'getaddrinfo',return_value=dns),patch.dict(interests.os.environ,{'RADAR_FAKE_DNS':'1'}):
            self.assertEqual(interests.validate_public_url('https://example.org/feed',resolve=True),'https://example.org/feed')
            with self.assertRaises(ValueError):interests.validate_public_url('https://198.18.0.133/feed',resolve=True)
        with patch.object(interests.socket,'getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]),patch.dict(interests.os.environ,{'RADAR_FAKE_DNS':'1'}):
            with self.assertRaises(ValueError):interests.validate_public_url('https://example.org/feed',resolve=True)
    def test_restricted_social_never_enables_paid_requests(self):
        a=interests.identify('https://x.com/researcher/status/1');a['user_added']=True
        with patch.object(radar.social,'settings',return_value={'x':{'bearer_token':'test'}}),patch.object(radar.social,'collect') as fetch:
            self.assertEqual(radar.collect_source(a)[1],'浏览器辅助');fetch.assert_not_called()
    def test_access_failure_keeps_source_with_honest_status(self):
        def denied(url):raise OSError('HTTP 403')
        s=interests.discover('https://example.org/',denied,radar.parse_feed,radar.canonical)
        self.assertEqual(s['adapter'],'manual');self.assertIn('403',s['note'])
        with radar.connect() as c:
            a=interests.register(c,s,'https://example.org/',radar.canonical)
            self.assertTrue(c.execute('SELECT 1 FROM sources WHERE id=?',(a['source_id'],)).fetchone())

class PreferenceHttpTests(HttpTests):
    def test_source_feedback_persists_pause_and_does_not_change_truth(self):
        with patch.object(radar,'fetch',return_value=FEED):a=self.request('source',{'url':'https://example.org/feed'})
        sid=a['source_id']
        score=self.request('source-feedback',{'source_id':sid,'action':'prefer'})['score']
        self.assertEqual(self.request('source-feedback',{'source_id':sid,'action':'prefer'})['score'],score)
        self.request('source-feedback',{'source_id':sid,'action':'pause'});radar.init()
        source=next(x for x in self.request('sources') if x['id']==sid)
        self.assertFalse(source['config']['enabled'])
        self.request('source-feedback',{'source_id':sid,'action':'resume'})
        self.request('source-feedback',{'source_id':sid,'action':'reset'})
        self.assertEqual(self.request('status')['count'],0)
        self.assertEqual(next(x for x in self.request('sources') if x['id']==sid)['preference']['score'],10)
    def test_pause_reason_is_visible_without_claiming_collection_success(self):
        with patch.object(radar,'fetch',return_value=FEED):a=self.request('source',{'url':'https://example.org/feed'})
        sid=a['source_id']
        self.request('source-feedback',{'source_id':sid,'action':'pause','reason':'上游频率限制，等待人工恢复'})
        source=next(x for x in self.request('sources') if x['id']==sid)
        self.assertFalse(source['config']['enabled'])
        self.assertEqual(source['error'],'上游频率限制，等待人工恢复')
        self.assertEqual(source['status'],'未采集')
    def test_source_cross_origin_and_internal_address_rejected(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):self.request('source',{'url':'http://127.0.0.1/feed'})
        with self.assertRaises(urllib.error.HTTPError):self.request('source',{'url':'https://example.org'}, {'Origin':'https://evil.example'})
    def test_search_chinese_translation_keeps_original(self):
        import translation
        self.request('import',{'title':'半導体のニュース','url':'https://example.org/jp','excerpt':'売上増加','language':'ja'})
        with radar.connect() as c:
            a=dict(c.execute('SELECT * FROM articles').fetchone())
            c.execute('INSERT INTO translations VALUES(?,?,?,?,?,?,?,?)',(a['id'],'test-gemma',translation.fingerprint(a),'完成','半导体新闻','营收增加','',0))
        with patch.dict(translation.os.environ,{'RADAR_TRANSLATION_MODEL':'test-gemma'}):
            found=self.request('articles?q='+radar.urllib.parse.quote('半导体'))
            self.assertEqual(found['total'],1)
            self.assertEqual(found['items'][0]['title'],'半導体のニュース')
            self.assertEqual(self.request('translations?ids='+a['id'])['items'][a['id']]['title'],'半导体新闻')
            with patch.object(translation,'enqueue',return_value=1) as enqueue:
                self.assertEqual(self.request('translate',{'ids':[a['id']]})['queued'],1)
                enqueue.assert_called_once()
    def test_static_path_traversal_and_asset_serving(self):
        import urllib.request,urllib.error
        folder=Path(self.tmp.name)/'static';folder.mkdir();(folder/'index.html').write_text('<h1>radar</h1>');(Path(self.tmp.name)/'secret').write_text('private')
        with patch.object(radar,'STATIC',folder):
            self.assertIn(b'radar',urllib.request.urlopen(self.base+'/').read())
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(self.base+'/%2e%2e/secret')
            self.assertEqual(e.exception.code,404)

if __name__=='__main__':unittest.main()
