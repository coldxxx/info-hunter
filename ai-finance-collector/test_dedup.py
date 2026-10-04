import json
import sqlite3
import unittest
from urllib.parse import urlencode
import dedup
import radar
import test_http
import test_radar
import watchlists

TITLE = 'Copilot code review: API support and new default effort level'
ORIGINAL = {'url': 'https://github.blog/changelog/copilot-review', 'title': TITLE,
            'excerpt': 'Request code review through the REST and GraphQL APIs.',
            'publisher': 'GitHub Changelog', 'published_at': '2026-10-02T19:13:50+00:00'}
INDEX = dict(ORIGINAL, url='https://news.google.com/rss/articles/copilot',
             title=TITLE + ' - The GitHub Blog', excerpt=TITLE + ' The GitHub Blog', publisher='The GitHub Blog')
DIRECT_SOURCE = dict(id='coding-changelog', name='GitHub Changelog', region='全球', language='en', kind='公司发布')
INDEX_SOURCE = dict(id='search-coding-agent-US', name='News index', region='全球', language='en-US', kind='新闻')


class DedupTests(unittest.TestCase):
    setUp = test_radar.RadarTests.setUp
    tearDown = test_radar.RadarTests.tearDown

    def test_actual_pair_in_both_arrival_orders_and_repeat_collection(self):
        for pair in [[(INDEX_SOURCE, INDEX), (DIRECT_SOURCE, ORIGINAL)], [(DIRECT_SOURCE, ORIGINAL), (INDEX_SOURCE, INDEX)]]:
            with radar.connect() as c:
                c.execute('DELETE FROM article_duplicates'); c.execute('DELETE FROM articles')
                for source, row in pair: radar.put(c, source, row)
                self.assertEqual(dedup.count(c), 1)
                self.assertEqual(dedup.page(c, '', [], 0)[0]['url'], ORIGINAL['url'])
                self.assertEqual(radar.put(c, DIRECT_SOURCE, ORIGINAL), 0)
                self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0], 2)
                self.assertEqual(dedup.count(c), 1)

    def test_conservative_identity_guards(self):
        a = dict(ORIGINAL, language='en', kind='公司发布')
        b = dict(INDEX, language='en-US', kind='新闻')
        self.assertTrue(dedup.same_article(a, b))
        for changed in [dict(b, publisher='Other Site', title=TITLE+' - Other Site'),
                        dict(b, published_at='2026-10-04T19:13:50+00:00'),
                        dict(b, published_at=None), dict(b, language='ja'),
                        dict(b, kind='论坛'), dict(b, title=TITLE.replace('API', 'CLI')+' - The GitHub Blog'),
                        dict(b, title=TITLE+' v2 - The GitHub Blog')]:
            with self.subTest(changed=changed): self.assertFalse(dedup.same_article(a, changed))
        self.assertFalse(dedup.same_article(dict(a, title='Daily update'), dict(b, title='Daily update - The GitHub Blog')))
        self.assertEqual(dedup.title_key(dict(a, title='A long technical announcement - implementation guide')), 'a long technical announcement - implementation guide')

    def test_no_date_chaining(self):
        with radar.connect() as c:
            for i in range(3):
                radar.put(c, INDEX_SOURCE, dict(INDEX, url=INDEX['url']+str(i), published_at=f'2026-10-0{2+i}T19:13:50+00:00'))
            self.assertEqual(dedup.count(c), 2)

    def test_migration_preserves_every_original_annotation_and_relation(self):
        with radar.connect() as c:
            radar.put(c, INDEX_SOURCE, INDEX); radar.put(c, DIRECT_SOURCE, ORIGINAL)
            c.execute("UPDATE articles SET starred=1,note='Keep my evidence',review='存疑' WHERE url=?", (INDEX['url'],))
            before = [tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')]
            sightings = [tuple(r) for r in c.execute('SELECT * FROM sightings ORDER BY article_id,source_id')]
            watches = [tuple(r) for r in c.execute('SELECT * FROM article_watches ORDER BY article_id,topic_id')]
            c.execute('DROP TABLE article_duplicates')
            dedup.bootstrap(c); dedup.bootstrap(c)
            self.assertEqual(before, [tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')])
            self.assertEqual(sightings, [tuple(r) for r in c.execute('SELECT * FROM sightings ORDER BY article_id,source_id')])
            self.assertEqual(watches, [tuple(r) for r in c.execute('SELECT * FROM article_watches ORDER BY article_id,topic_id')])
            self.assertEqual(dedup.page(c, '', [], 0)[0]['note'], 'Keep my evidence')


class DedupHttpTests(unittest.TestCase):
    setUp = test_http.HttpTests.setUp
    tearDown = test_http.HttpTests.tearDown
    request = test_http.HttpTests.request

    def pair(self):
        with radar.connect() as c:
            radar.put(c, INDEX_SOURCE, INDEX); radar.put(c, DIRECT_SOURCE, ORIGINAL)

    def query(self, **kw): return self.request('articles?'+urlencode(kw))

    def test_one_card_preferred_original_and_all_versions(self):
        self.pair()
        result = self.query(watch_id='coding-agent', q=TITLE)
        self.assertEqual(result['total'], 1)
        item = result['items'][0]
        self.assertEqual(item['url'], ORIGINAL['url'])
        self.assertEqual(item['duplicate_count'], 2)
        self.assertEqual(item['duplicates'][0]['url'], INDEX['url'])
        self.assertEqual(self.request('status?watch_id=coding-agent')['count'], 1)
        self.assertEqual(next(t for t in self.request('watch-topics') if t['id']=='coding-agent')['article_count'], 1)

    def test_filters_stars_notes_and_reviews_on_secondary_copy_survive(self):
        self.pair()
        index = self.query(source_id=INDEX_SOURCE['id'])['items'][0]
        self.assertEqual(index['url'], INDEX['url'])
        self.request('article', dict(id=index['id'], starred=1, note='secondary evidence', review='存疑', watch_id='coding-agent'))
        starred = self.query(watch_id='coding-agent', starred=1)
        self.assertEqual(starred['total'], 1)
        self.assertEqual(starred['items'][0]['note'], 'secondary evidence')
        self.assertEqual(self.query(q='secondary evidence')['total'], 1)
        original = self.query(source_id=DIRECT_SOURCE['id'])['items'][0]
        self.assertEqual(original['note'], '')
        self.assertEqual(original['duplicates'][0]['review'], '存疑')
        self.assertEqual(self.query(kind='新闻')['total'], 1)
        self.assertEqual(self.query(watch_id='coding-agent', engineering_category='工具更新')['total'], 1)

    def test_topic_scope_does_not_lose_or_expose_versions(self):
        self.pair()
        with radar.connect() as c:
            t=watchlists.save(c, {'name':'Custom', 'keywords':'not-matching', 'news_search':False})
            aid=c.execute('SELECT id FROM articles WHERE url=?',(INDEX['url'],)).fetchone()[0]
            c.execute('INSERT INTO article_watches VALUES(?,?,?)',(aid,t['id'],'手动收录'))
        result=self.query(watch_id=t['id'])
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['url'], INDEX['url'])
        self.assertEqual(result['items'][0]['duplicate_count'], 1)
        self.assertEqual(result['items'][0]['duplicates'], [])

    def test_dedup_happens_before_pagination(self):
        with radar.connect() as c:
            for i in range(55):
                radar.put(c, DIRECT_SOURCE, dict(ORIGINAL, title=TITLE+f' feature {i}',url=ORIGINAL['url']+str(i)))
                radar.put(c, INDEX_SOURCE, dict(INDEX, title=TITLE+f' feature {i} - The GitHub Blog',url=INDEX['url']+str(i)))
        first=self.query(); second=self.query(offset=50)
        self.assertEqual(first['total'], 55); self.assertEqual(len(first['items']), 50)
        self.assertEqual(len(second['items']), 5)
        ids=[a['id'] for a in first['items']+second['items']]
        self.assertEqual(len(set(ids)), 55)


if __name__ == '__main__': unittest.main()
