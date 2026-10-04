import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import radar

class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = patch.object(radar,'DB',Path(self.tmp.name)/'data'/'test.db')
        self.db.start()
        radar.init()

    def tearDown(self):
        self.db.stop()
        self.tmp.cleanup()

    def test_rss_and_atom_preserve_dates(self):
        rss=b'<rss><channel><item><title>GPU &amp; HBM</title><link>https://example.com/a</link><description>&lt;b&gt;Revenue&lt;/b&gt;</description><pubDate>Tue, 08 Sep 2026 08:00:00 +0900</pubDate></item></channel></rss>'
        a=radar.parse_feed(rss)[0]
        self.assertEqual(a['title'],'GPU & HBM')
        self.assertEqual(a['excerpt'],'Revenue')
        self.assertEqual(a['published_at'],'2026-09-07T23:00:00+00:00')
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI</title><link href="https://example.com/atom"/><updated>2026-09-08T01:00:00Z</updated></entry></feed>'
        self.assertEqual(radar.parse_feed(atom)[0]['url'],'https://example.com/atom')
        with self.assertRaises(ValueError):radar.parse_feed(b'<html><body>blocked</body></html>')

    def test_dedup_preserves_notes_and_all_sources(self):
        s=dict(id='test',name='Test',region='日本',language='ja',kind='新闻')
        a=dict(url='https://example.com/a?utm_source=x',title='GPU earnings',excerpt='revenue',published_at=None)
        with radar.connect() as c:
            self.assertEqual(radar.put(c,s,a),1)
            c.execute("UPDATE articles SET note='my research',starred=1")
            s['id']='other'
            a['url']='https://example.com/a'
            self.assertEqual(radar.put(c,s,a),0)
            self.assertEqual(c.execute('SELECT note FROM articles').fetchone()[0],'my research')
            self.assertEqual(c.execute('SELECT count(*) FROM sightings').fetchone()[0],2)

    def test_multilingual_topics_and_word_boundaries(self):
        self.assertIn('算力与芯片',radar.classify('HBM 반도체 半導体'))
        self.assertFalse(radar.matches('retail','ai'))
        self.assertTrue(radar.matches('ai revenue','ai'))
        self.assertIsNone(radar.date('not a date'))
        with self.assertRaises(ValueError):radar.canonical('javascript:alert(1)')

    def test_source_failure_recorded_without_erasing_articles(self):
        with patch.object(radar,'collect_source',side_effect=ValueError('blocked')),patch.object(radar,'backup',return_value='test'):
            result=radar.collect('nvidia')
        self.assertEqual(result['results'][0]['status'],'失败')
        with radar.connect() as c:
            self.assertIn('blocked',c.execute("SELECT error FROM sources WHERE id='nvidia'").fetchone()[0])

    def test_missing_x_token_does_not_fetch(self):
        with patch.dict('os.environ',{},clear=True),patch.object(radar,'fetch') as f:
            rows,status,_=radar.collect_source({'adapter':'x'})
            self.assertEqual(status,'待授权')
            self.assertEqual(rows,[])
            f.assert_not_called()

    def test_backup_restores_database(self):
        with patch.object(radar,'ROOT',Path(self.tmp.name)):
            dest=radar.backup()
        with sqlite3.connect(dest) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertGreater(c.execute('SELECT count(*) FROM sources').fetchone()[0],0)

if __name__=='__main__':unittest.main()
