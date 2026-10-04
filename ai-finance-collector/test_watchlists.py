import json
import unittest
from unittest.mock import patch
import test_radar
import radar, watchlists, interests

class WatchTests(unittest.TestCase):
    setUp=test_radar.RadarTests.setUp
    tearDown=test_radar.RadarTests.tearDown
    def test_custom_topic_collects_non_ai_and_excludes(self):
        with radar.connect() as c:
            t=watchlists.save(c,{'name':'摄影','keywords':'摄影, camera','exclude':'广告','regions':['全球'],'news_search':False})
            watchlists.bind(c,t['id'],'nvidia')
            sources=watchlists.collection_sources(c,t['id'])
            self.assertEqual(len(sources),1)
            s=sources[0]
            self.assertTrue(watchlists.accepts(s,{'title':'New camera workflow'}))
            self.assertFalse(watchlists.accepts(s,{'title':'camera 广告'}))
            self.assertFalse(watchlists.accepts(s,{'title':'unrelated'}))
            a={'url':'https://example.com/camera','title':'camera workflow','excerpt':'','published_at':None}
            radar.put(c,s,a)
            self.assertEqual(c.execute('SELECT count(*) FROM article_watches WHERE topic_id=?',(t['id'],)).fetchone()[0],1)
            watchlists.save(c,{'id':t['id'],'enabled':False})
            self.assertEqual(watchlists.collection_sources(c,t['id']),[])
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],1)

    def test_preference_is_separate_for_each_topic(self):
        with radar.connect() as c:
            interests.signal(c,'nvidia','prefer','prefer',topic_id='coding-agent')
            self.assertGreater(interests.policy(c,'nvidia',topic_id='coding-agent')['score'],interests.policy(c,'nvidia',topic_id='ai')['score'])

    def test_global_source_binding_does_not_clone_or_reset_topic_rules(self):
        with radar.connect() as c:
            topic=watchlists.save(c,{'name':'GPU tools','keywords':'GPU','news_search':False})
            count=c.execute('SELECT count(*) FROM sources').fetchone()[0]
            original=c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0]
            self.assertEqual(watchlists.bind_many(c,topic['id'],['nvidia','coding-hn','nvidia'],True),{'added':2,'already_followed':0})
            self.assertEqual(watchlists.bind_many(c,topic['id'],['nvidia'],False),{'added':0,'already_followed':1})
            self.assertEqual(c.execute('SELECT count(*) FROM sources').fetchone()[0],count)
            self.assertEqual(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0],original)
            self.assertEqual(c.execute('SELECT include_all FROM watch_sources WHERE topic_id=? AND source_id=?',(topic['id'],'nvidia')).fetchone()[0],1)
            self.assertEqual(sum(s['id']=='nvidia' for s in watchlists.collection_sources(c)),1)
            source=next(s for s in watchlists.collection_sources(c) if s['id']=='nvidia')
            self.assertIn(topic['id'],{t['id'] for t in source['_watch_rules']})
            radar.put(c,source,{'title':'GPU tools SDK','url':'https://example.com/shared-sdk','excerpt':'inference GPU','published_at':None})
            self.assertEqual(c.execute('SELECT count(*) FROM article_watches WHERE topic_id=?',(topic['id'],)).fetchone()[0],1)
            self.assertEqual(c.execute("SELECT count(*) FROM article_watches WHERE topic_id='ai'").fetchone()[0],1)
            c.execute('DELETE FROM watch_sources WHERE topic_id=? AND source_id=?',(topic['id'],'nvidia'))
            self.assertTrue(c.execute("SELECT 1 FROM watch_sources WHERE topic_id='ai' AND source_id='nvidia'").fetchone())
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],1)

    def test_invalid_batch_has_no_partial_bindings(self):
        with radar.connect() as c:
            topic=watchlists.save(c,{'name':'Test','keywords':'GPU','news_search':False})
            with self.assertRaises(ValueError):watchlists.bind_many(c,topic['id'],['nvidia','missing'])
            self.assertEqual(c.execute('SELECT count(*) FROM watch_sources WHERE topic_id=?',(topic['id'],)).fetchone()[0],0)

    def test_bootstrap_is_idempotent_and_manual_import_survives(self):
        with radar.connect() as c:
            watchlists.save(c,{'id':'coding-agent','name':'My engineering','keywords':'coding','news_search':False})
            radar.put(c,{'id':'manual','name':'Me','region':'全球','language':'en','kind':'论坛'},{'url':'https://example.com/manual','title':'Personal workflow','excerpt':'','published_at':None})
            aid=c.execute('SELECT id FROM articles').fetchone()[0]
            c.execute('INSERT INTO article_watches VALUES(?,?,?)',(aid,'coding-agent','手动收录'))
            watchlists.reindex(c,'coding-agent')
            self.assertEqual(c.execute('SELECT reason FROM article_watches WHERE article_id=?',(aid,)).fetchone()[0],'手动收录')
            watchlists.bootstrap(c,radar.AI_WORDS)
            self.assertEqual(watchlists.get(c,'coding-agent')['name'],'My engineering')

    def test_translation_matches_only_current_content(self):
        import translation
        with radar.connect() as c:
            t=watchlists.save(c,{'name':'工具','keywords':'编程助手','news_search':False})
            radar.put(c,{'id':'manual','name':'Me','region':'日本','language':'ja','kind':'新闻'},{'url':'https://example.com/ja','title':'新しい道具','excerpt':'','published_at':None})
            a=dict(c.execute('SELECT * FROM articles').fetchone())
            c.execute('INSERT INTO translations VALUES(?,?,?,?,?,?,?,?)',(a['id'],'test','stale','完成','编程助手','','',0))
            watchlists.reindex(c,t['id'])
            self.assertEqual(c.execute('SELECT count(*) FROM article_watches WHERE topic_id=?',(t['id'],)).fetchone()[0],0)
            c.execute('UPDATE translations SET fingerprint=?',(translation.fingerprint(a),))
            watchlists.reindex(c,t['id'])
            self.assertEqual(c.execute('SELECT count(*) FROM article_watches WHERE topic_id=?',(t['id'],)).fetchone()[0],1)

    def test_legacy_contents_and_annotations_remain_unchanged(self):
        with radar.connect() as c:
            radar.put(c,{'id':'manual','name':'Me','region':'全球','language':'en','kind':'新闻'},{'url':'https://example.com/legacy','title':'Old research','excerpt':'','published_at':None})
            c.execute("UPDATE articles SET note='my note',starred=1")
            aid=c.execute('SELECT id FROM articles').fetchone()[0]
            c.execute('INSERT INTO article_watches VALUES(?,?,?)',(aid,'ai','原AI资料库'))
            before=tuple(c.execute('SELECT * FROM articles').fetchone())
            watchlists.save(c,{'id':'ai','keywords':'Old'})
            watchlists.save(c,{'id':'ai','keywords':'newkeyword'})
            self.assertEqual(tuple(c.execute('SELECT * FROM articles').fetchone()),before)
            self.assertTrue(c.execute('SELECT reason FROM article_watches WHERE article_id=?',(aid,)).fetchone()[0].startswith('原AI资料库'))
