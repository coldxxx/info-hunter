import json
import unittest
import urllib.error
from unittest.mock import patch
import interests
import radar
import source_lifecycle
import test_http
import test_radar
import watchlists


class SourceLifecycleTests(unittest.TestCase):
    setUp = test_radar.RadarTests.setUp
    tearDown = test_radar.RadarTests.tearDown

    def test_delete_preserves_archive_and_removes_all_topic_controls(self):
        with radar.connect() as c:
            source = json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            watchlists.bind(c, 'coding-agent', 'nvidia', True)
            radar.put(c, source, dict(title='NVIDIA SDK implementation', url='https://example.org/sdk',
                                     body='Full source text', excerpt='API tutorial'))
            c.execute("UPDATE articles SET note='Research note',starred=1,review='存疑'")
            c.execute("INSERT INTO source_connections VALUES('nvidia','shared-blog','rss-browser')")
            c.execute("INSERT INTO source_controls VALUES('nvidia',1)")
            interests.signal(c, 'nvidia', 'prefer', 'prefer')
            c.execute("INSERT INTO submitted_links VALUES('https://example.org/sdk','nvidia','today')")
            tables = ['articles', 'sightings', 'article_content', 'article_watches', 'translations', 'article_duplicates']
            before = {table: [tuple(r) for r in c.execute('SELECT * FROM '+table)] for table in tables}
            result = source_lifecycle.delete(c, 'nvidia')
            self.assertEqual(result['removed_topics'], 2)
            self.assertTrue(c.execute("SELECT deleted_at FROM sources WHERE id='nvidia'").fetchone()[0])
            for table in tables:
                self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM '+table)], before[table])
            for table in ['watch_sources', 'source_connections', 'source_controls', 'source_signals', 'submitted_links']:
                self.assertEqual(c.execute('SELECT count(*) FROM '+table+' WHERE source_id=?', ('nvidia',)).fetchone()[0], 0)
            self.assertTrue(source_lifecycle.delete(c, 'nvidia')['already_deleted'])

    def test_bundled_source_stays_deleted_after_restart(self):
        with radar.connect() as c: source_lifecycle.delete(c, 'nvidia')
        radar.init()
        with radar.connect() as c:
            self.assertTrue(c.execute("SELECT deleted_at FROM sources WHERE id='nvidia'").fetchone()[0])
            self.assertNotIn('nvidia', [s['id'] for s in watchlists.collection_sources(c)])
            with self.assertRaises(ValueError): watchlists.bind(c, 'ai', 'nvidia')
            with self.assertRaises(ValueError): watchlists.bind_many(c, 'ai', ['coding-hn', 'nvidia'])
            self.assertFalse(c.execute("SELECT 1 FROM watch_sources WHERE topic_id='ai' AND source_id='coding-hn'").fetchone())

    def test_generated_search_stays_deleted_when_topic_is_saved(self):
        sid = 'search-coding-agent-US'
        with radar.connect() as c:
            source_lifecycle.delete(c, sid)
            watchlists.save(c, {'id': 'coding-agent', 'description': 'Edited topic'})
            self.assertTrue(c.execute('SELECT deleted_at FROM sources WHERE id=?', (sid,)).fetchone()[0])
            self.assertFalse(c.execute('SELECT 1 FROM watch_sources WHERE source_id=?', (sid,)).fetchone())

    def test_explicit_readding_restores_same_source_and_only_selected_topic(self):
        with radar.connect() as c:
            source = json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            watchlists.bind(c, 'coding-agent', 'nvidia', True)
            c.execute("UPDATE sources SET status='失败',error='old failure',last_count=10 WHERE id='nvidia'")
            source_lifecycle.delete(c, 'nvidia')
            result = interests.register(c, source, source['url'], radar.canonical, topic_id='coding-agent')
            self.assertEqual(result['source_id'], 'nvidia')
            row = c.execute("SELECT deleted_at,status,error,last_count FROM sources WHERE id='nvidia'").fetchone()
            self.assertEqual(tuple(row), (None, '未采集', '', 0))
            self.assertEqual([r[0] for r in c.execute("SELECT topic_id FROM watch_sources WHERE source_id='nvidia'")], ['coding-agent'])

    def test_deleted_stale_source_is_never_fetched(self):
        with radar.connect() as c:
            source = json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            source_lifecycle.delete(c, 'nvidia')
        with patch.object(radar, 'fetch') as fetch, patch.object(radar, 'backup'):
            self.assertEqual(radar.collect_source(source), ([], '已删除', ''))
            self.assertEqual(radar.collect('nvidia')['results'], [])
            fetch.assert_not_called()

    def test_source_deleted_during_fetch_cannot_write_late_results(self):
        def fetched(source):
            with radar.connect() as c: source_lifecycle.delete(c, source['id'])
            return [dict(title='GPU', url='https://example.org/late')], '成功', ''
        with patch.object(radar, 'collect_source', side_effect=fetched), patch.object(radar, 'backup'):
            result = radar.collect('nvidia')
        self.assertEqual(result['results'][0]['status'], '已删除')
        with radar.connect() as c: self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0], 0)

    def test_unknown_or_invalid_deletion_does_not_change_registry(self):
        with radar.connect() as c:
            for sid in [None, [], '', 'missing']:
                with self.assertRaises(ValueError): source_lifecycle.delete(c, sid)
            self.assertEqual(c.execute('SELECT count(*) FROM sources WHERE deleted_at IS NOT NULL').fetchone()[0], 0)


class SourceDeleteHttpTests(unittest.TestCase):
    setUp = test_http.HttpTests.setUp
    tearDown = test_http.HttpTests.tearDown
    request = test_http.HttpTests.request

    def test_delete_hidden_from_library_and_detail_but_archive_remains(self):
        with radar.connect() as c:
            source = json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            radar.put(c, source, dict(title='GPU SDK', url='https://example.org/archive'))
        self.assertTrue(self.request('source-delete', {'source_id': 'nvidia'})['ok'])
        self.assertNotIn('nvidia', [s['id'] for s in self.request('sources?all=1')])
        archive = self.request('articles?source_id=nvidia')
        self.assertEqual(archive['total'], 1)
        self.assertEqual(archive['items'][0]['source_name'], 'NVIDIA 官方博客')
        with self.assertRaises(urllib.error.HTTPError) as error: self.request('source-detail?id=nvidia')
        self.assertEqual(error.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError): self.request('source-connection', {'source_id': 'nvidia'})

    def test_cross_origin_cannot_delete_and_article_id_is_exact(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('source-delete', {'source_id': 'nvidia'}, {'Origin': 'https://evil.example'})
        self.assertEqual(error.exception.code, 403)
        self.assertIn('nvidia', [s['id'] for s in self.request('sources?all=1')])
        self.request('import', {'title': 'SDK archive', 'url': 'https://example.org/one'})
        self.request('import', {'title': 'Another archive', 'url': 'https://example.org/two'})
        article = self.request('articles')['items'][0]
        found = self.request('articles?id='+article['id'])
        self.assertEqual(found['total'], 1)
        self.assertEqual(found['items'][0]['id'], article['id'])
        self.assertEqual(self.request('articles?id=missing')['total'], 0)


if __name__ == '__main__': unittest.main()
