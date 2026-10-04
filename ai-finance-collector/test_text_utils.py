"""Contracts for pure parsing and the existing content-store compatibility hooks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import content_store
import readable
import text_utils


class PureParsingTests(unittest.TestCase):
    def test_readable_and_transcript_import_without_content_store(self):
        collector = Path(__file__).resolve().parent
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / 'native'))
import text_utils
import readable
import transcribe
assert 'content_store' not in sys.modules
assert 'radar' not in sys.modules
assert readable.title('<title>A &amp; B</title>') == 'A & B'
assert transcribe.transcript('<p>Hello &amp; AI</p>')['text'] == 'Hello & AI'
assert not list(Path.cwd().iterdir())
"""
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, '-I', '-B', '-c', code, str(collector)],
                           cwd=folder, check=True, capture_output=True, text=True)

    def test_plain_text_wrapper_uses_current_parser_class(self):
        class Parser:
            def __init__(self):
                self.parts = []

            def feed(self, value):
                self.parts = ['overridden: ' + value]

        with patch.object(content_store, 'Text', Parser):
            self.assertEqual(content_store.plain_text('input'), 'overridden: input')
        self.assertEqual(text_utils.plain_text('<p>A &amp; B</p><script>hidden</script><p>C</p>'),
                         'A & B\nC')

    def test_feed_wrapper_uses_current_text_and_gate_hooks(self):
        raw = b'''<rss xmlns:content="urn:content"><channel><item>
        <link>https://example.org/post</link><content:encoded>&lt;p&gt;original&lt;/p&gt;</content:encoded>
        </item></channel></rss>'''
        rows = [{'url': 'https://example.org/post'}]
        with patch.object(content_store, 'plain_text', return_value='overridden') as to_text, \
                patch.object(readable, 'gated', return_value=True) as gate:
            result = content_store.feed_extras(raw, rows)
        self.assertIs(result, rows)
        to_text.assert_called_once_with('<p>original</p>')
        gate.assert_called_once_with('overridden')
        self.assertNotIn('body', rows[0])
        self.assertEqual(rows[0]['body_error'], '订阅仅提供会员预览；请连接该站点后获取全文')

    def test_opml_validation_and_name_fallback_stay_in_wrapper(self):
        raw = '<opml><body><outline xmlUrl="https://example.org/one"/>' \
              '<outline title="Two" xmlUrl="https://example.org/two"/></body></opml>'
        validate = Mock(side_effect=['https://validated.example/one', 'https://validated.example/two'])
        with patch.object(content_store.interests, 'validate_public_url', validate):
            result = content_store.opml(raw)
        self.assertEqual(result, [dict(name='https://validated.example/one', url='https://validated.example/one'),
                                  dict(name='Two', url='https://validated.example/two')])
        self.assertEqual([call.args[0] for call in validate.call_args_list],
                         ['https://example.org/one', 'https://example.org/two'])
        too_many = '<opml>' + '<outline xmlUrl="https://example.org/feed"/>' * 101 + '</opml>'
        with patch.object(content_store.interests, 'validate_public_url', side_effect=ValueError('invalid source')):
            with self.assertRaisesRegex(ValueError, 'invalid source'):
                content_store.opml(too_many)


if __name__ == '__main__':
    unittest.main()
