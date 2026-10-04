import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

import content_store
import radar
import reddit_quality as quality
import test_http
import test_radar
import watchlists

URL = 'https://www.reddit.com/r/ArtificialInteligence/comments/1wxijdw/is_it_me_or_did_the_producers_of_coward_the_dog/'
TITLE = 'Is it me or did the producers of Coward the dog predict the modern AI assistant?'
BODY = ('We tested inference latency on the same GPU using a fixed dataset and recorded 25% lower memory usage. '
        'The benchmark covers prompt length, batch size, warmup, baseline, throughput, reproducibility, hardware, software versions, '
        'precision, sample selection, variance, input distribution and output accuracy. Results depend on the configuration; '
        'our implementation and measurement scripts describe the limitations and show how to reproduce the evaluation.')


class PolicyTests(unittest.TestCase):
    def test_reported_empty_four_comment_post_rejected(self):
        self.assertFalse(quality.assess(dict(title=TITLE, body='', comment_count=4))['eligible'])

    def test_popularity_alone_and_padding_do_not_pass(self):
        for body in ('', 'benchmark '*300, 'Great AI assistant! '*300):
            with self.subTest(body=body[:20]):
                self.assertFalse(quality.assess(dict(title=TITLE, body=body, comment_count=1000))['eligible'])

    def test_ordinary_substantive_discussion_needs_ten_comments(self):
        self.assertFalse(quality.assess(dict(title='AI benchmark', body=BODY, comment_count=9))['eligible'])
        self.assertTrue(quality.assess(dict(title='AI benchmark', body=BODY, comment_count=10))['eligible'])

    def test_firsthand_code_and_detailed_measurement_exceptions(self):
        project=dict(title='Reproducible inference benchmark model and dataset release', outbound_url='https://github.com/example/benchmark', comment_count=0)
        self.assertTrue(quality.assess(project)['eligible'])
        self.assertTrue(quality.assess(dict(title='AI benchmark', body=BODY+' '+BODY, comment_count=1))['eligible'])
        self.assertFalse(quality.assess(dict(project, outbound_url='https://example.com/promotion'))['eligible'])
        self.assertFalse(quality.assess(dict(project, outbound_url='https://github.com/'))['eligible'])

    def test_entertainment_flair_overrides_popularity_and_resource(self):
        post=dict(title='New inference model release and reproducible benchmark', body=BODY+' '+BODY, comment_count=100, outbound_url='https://arxiv.org/abs/1234.5678', flair='Meme / Humor')
        self.assertFalse(quality.assess(post)['eligible'])

    def test_unknown_is_not_zero_and_legacy_excerpt_is_not_substance(self):
        self.assertIsNone(quality.assess(dict(title=TITLE))['comment_count'])
        self.assertFalse(quality.assess(dict(title='AI benchmark', excerpt='仅保存列表标题；未读取正文。'+BODY, comment_count=20))['eligible'])

    def test_comment_counts_and_configurable_boundary(self):
        for raw, expected in [(4,4),('4',4),('1.2k comments',1200),('1,234 comments',1234),('0 comments',0),(None,None),('',None),('vote',None),(True,None),(-1,None),('4.5',None)]:
            with self.subTest(raw=raw):self.assertEqual(quality.comment_count(raw),expected)
        self.assertTrue(quality.assess(dict(title='benchmark',body=BODY,comment_count=5),{'reddit_min_comments':5})['eligible'])
        self.assertFalse(quality.assess(dict(title='benchmark',body=BODY,comment_count=5),{'reddit_min_comments':True})['eligible'])

    def test_exact_host(self):
        self.assertFalse(quality.is_reddit('https://example.com/?url=reddit.com/'))
        self.assertFalse(quality.is_reddit('https://reddit.com.attacker.org/post'))
        self.assertTrue(quality.is_reddit(URL))


class StorageTests(unittest.TestCase):
    setUp = test_radar.RadarTests.setUp
    tearDown = test_radar.RadarTests.tearDown

    def source(self,c):
        return json.loads(c.execute("SELECT config FROM sources WHERE id='reddit-local'").fetchone()[0])

    def old_post(self,c):
        source=self.source(c)
        manual=dict(source,id='manual-import')
        radar.put(c,manual,dict(url=URL,title=TITLE,excerpt=''))
        aid=hashlib.sha256(URL.encode()).hexdigest()[:24]
        c.execute("UPDATE articles SET source_id='reddit-local' WHERE id=?",(aid,))
        c.execute("UPDATE sightings SET source_id='reddit-local' WHERE article_id=?",(aid,))
        return aid

    def test_entire_board_cannot_bypass_gate_and_deleted_status_passes(self):
        with radar.connect() as c:
            source=self.source(c)
            source['_watch_rules']=[dict(watchlists.get(c,'ai'),include_all=True)]
        rejected=dict(url=URL,title=TITLE,body='',comment_count=4)
        deleted=dict(rejected,deleted=True)
        accepted=dict(url=URL+'benchmark',title='AI benchmark',body=BODY,comment_count=10)
        with patch.object(radar.capture,'read',return_value=([rejected,deleted,accepted],'成功','')):
            rows,status,_=radar.collect_source(source)
        self.assertEqual(status,'成功');self.assertEqual(rows,[deleted,accepted])

    def test_put_defends_other_automatic_import_paths(self):
        with radar.connect() as c:
            self.assertEqual(radar.put(c,self.source(c),dict(url=URL,title=TITLE,comment_count=4)),0)
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],0)

    def test_historical_migration_preserves_original_and_annotations(self):
        with radar.connect() as c:
            aid=self.old_post(c)
            c.execute("UPDATE articles SET note='my research',starred=1,review='存疑' WHERE id=?",(aid,))
            before=dict(c.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone())
            quality.bootstrap(c);quality.bootstrap(c)
            self.assertEqual(dict(c.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()),before)
            self.assertEqual(c.execute('SELECT eligible FROM article_quality WHERE article_id=?',(aid,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM articles WHERE '+quality.VISIBLE).fetchone()[0],1)
            c.execute("UPDATE articles SET note='',starred=0,review='未核验'")
            self.assertEqual(c.execute('SELECT count(*) FROM articles WHERE '+quality.VISIBLE).fetchone()[0],0)

    def test_seen_again_refreshes_quality_and_preserves_partial_metadata(self):
        with radar.connect() as c:
            source=self.source(c)
            post=dict(url=URL,title='AI benchmark',body=BODY,comment_count=12)
            self.assertEqual(radar.put(c,source,post),1)
            aid=c.execute('SELECT id FROM articles').fetchone()[0]
            self.assertEqual(radar.put(c,source,dict(url=URL,title='AI benchmark')),0)
            self.assertEqual(c.execute('SELECT comment_count,eligible FROM article_quality WHERE article_id=?',(aid,)).fetchone()[:],(12,1))
            self.assertEqual(radar.put(c,source,dict(post,comment_count=4)),0)
            self.assertEqual(c.execute('SELECT eligible FROM article_quality WHERE article_id=?',(aid,)).fetchone()[0],0)
            self.assertEqual(radar.put(c,source,dict(post,comment_count=15)),0)
            self.assertEqual(c.execute('SELECT eligible FROM article_quality WHERE article_id=?',(aid,)).fetchone()[0],1)
            content_store.remove(c,aid)
            self.assertIsNone(c.execute('SELECT 1 FROM article_quality WHERE article_id=?',(aid,)).fetchone())

    def test_backup_scrubs_quality_with_provider_content(self):
        with radar.connect() as c:radar.put(c,self.source(c),dict(url=URL,title='AI benchmark',body=BODY,comment_count=12))
        with patch.dict('os.environ',{'RADAR_BACKUP_DIR':self.tmp.name}):dest=radar.backup()
        with sqlite3.connect(dest) as c:self.assertEqual(c.execute('SELECT count(*) FROM article_quality').fetchone()[0],0)


class VisibilityTests(unittest.TestCase):
    setUp = test_http.HttpTests.setUp
    tearDown = test_http.HttpTests.tearDown
    request = test_http.HttpTests.request

    def test_feed_status_topic_counts_and_direct_access_agree(self):
        with radar.connect() as c:
            source=json.loads(c.execute("SELECT config FROM sources WHERE id='reddit-local'").fetchone()[0])
            radar.put(c,dict(source,id='manual-import'),dict(url=URL,title=TITLE))
            aid=c.execute('SELECT id FROM articles').fetchone()[0]
            c.execute("UPDATE articles SET source_id='reddit-local'")
            c.execute("INSERT OR REPLACE INTO article_watches VALUES(?, 'ai','test')",(aid,))
            quality.bootstrap(c)
        self.assertEqual(self.request('articles?watch_id=ai')['total'],0)
        self.assertEqual(self.request('articles?collapse=0')['total'],0)
        self.assertEqual(self.request('status?watch_id=ai')['count'],0)
        self.assertEqual(next(t for t in self.request('watch-topics') if t['id']=='ai')['article_count'],0)
        direct=self.request('articles?id='+aid)['items'][0]
        self.assertEqual(direct['title'],TITLE)
        self.assertFalse(direct['reddit_quality']['eligible'])
        self.request('article',dict(direct,starred=1))
        self.assertEqual(self.request('articles?starred=1')['total'],1)
        self.assertEqual(self.request('status?watch_id=ai')['count'],1)


if __name__=='__main__':unittest.main()
