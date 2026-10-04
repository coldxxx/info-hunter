import unittest
from unittest.mock import patch
import capture
import radar


class CaptureTests(unittest.TestCase):
    def test_rss_forums_share_reader_and_standard_post_mapping(self):
        feed=b'<rss><channel><item><title>GPU discussion</title><link>https://example.org/post</link><description>&lt;b&gt;SDK workflow&lt;/b&gt;</description></item></channel></rss>'
        sources=[{'adapter':'rss','kind':'论坛','url':'https://one.example.org/feed'}, {'adapter':'rss','kind':'论坛','url':'https://two.example.org/forum','feed_url':'https://two.example.org/rss'}]
        with patch.object(radar,'fetch',return_value=feed) as fetch:
            results=[radar.collect_source(s) for s in sources]
        self.assertEqual([c.args[0] for c in fetch.call_args_list],['https://one.example.org/feed','https://two.example.org/rss'])
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0][0][0]['excerpt'],'SDK workflow')
        self.assertEqual(capture.describe(sources[0])['id'],capture.describe(sources[1])['id'])

    def test_reddit_boards_reuse_adapter_with_different_parameters(self):
        posts=[{'title':'A reproducible inference model benchmark and dataset release','url':'https://www.reddit.com/r/stocks/comments/a/','outbound_url':'https://github.com/test/benchmark','published_at':None}]
        with patch.object(capture.social,'collect',return_value=(posts,'成功','')) as read:
            for subreddit in ['stocks','LocalLLaMA']:
                source={'adapter':'reddit','url':'https://www.reddit.com/r/'+subreddit,'subreddit':subreddit}
                self.assertEqual(radar.collect_source(source)[0],posts)
        self.assertEqual([c.args[0]['subreddit'] for c in read.call_args_list],['stocks','LocalLLaMA'])
        self.assertTrue(all(c.args[0]['adapter']=='reddit' for c in read.call_args_list))

    def test_assisted_source_does_not_start_network_capture(self):
        with patch.object(radar,'fetch') as fetch,patch.object(capture.social,'collect') as api:
            self.assertEqual(radar.collect_source({'adapter':'browser','url':'https://example.org/forum'})[1],'浏览器辅助')
            fetch.assert_not_called();api.assert_not_called()

    def test_unknown_adapter_is_not_treated_as_rss(self):
        with patch.object(radar,'fetch') as fetch:
            with self.assertRaises(ValueError):radar.collect_source({'adapter':'unknown','url':'https://example.org/'})
            fetch.assert_not_called()


if __name__=='__main__':unittest.main()
