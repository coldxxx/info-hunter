import unittest
from unittest.mock import patch
import test_radar
from browser_import import import_batch


class BrowserImportTests(unittest.TestCase):
    setUp = test_radar.RadarTests.setUp
    tearDown = test_radar.RadarTests.tearDown
    def test_batch_validation_and_preservation(self):
        import radar
        row = {'url': 'https://x.com/example/status/123', 'title': 'GPU demand',
               'author': 'example', 'excerpt': 'Test fixture only'}
        with patch.object(radar, 'backup', return_value='test'):
            with self.assertRaises(ValueError):
                import_batch('x-ai', [row, dict(row, url='https://example.com/a')])
            with radar.connect() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0], 0)
            self.assertEqual(import_batch('x-ai', [row])['added'], 1)
            with radar.connect() as c:
                c.execute("UPDATE articles SET note='keep',starred=1")
            self.assertEqual(import_batch('x-ai', [row])['duplicates'], 1)
            with radar.connect() as c:
                saved = c.execute('SELECT * FROM articles').fetchone()
                self.assertEqual(saved['note'], 'keep')
                self.assertEqual(saved['source_id'], 'x-ai')
                self.assertIsNone(saved['published_at'])

    def test_browser_mode_never_fetches(self):
        import radar
        with patch.object(radar, 'fetch') as fetch, patch.object(radar.social, 'collect') as social:
            self.assertEqual(radar.collect_source({'adapter': 'browser'})[1], '浏览器辅助')
            fetch.assert_not_called()
            social.assert_not_called()
