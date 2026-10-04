import http.client
import ssl
import unittest
import urllib.error
from unittest.mock import Mock, patch

import radar


class FetchTests(unittest.TestCase):
    url = 'https://example.org/feed'

    def setUp(self):
        def start(patcher):
            result = patcher.start()
            self.addCleanup(patcher.stop)
            return result
        self.validate = start(patch.object(radar.interests, 'validate_public_url'))
        self.opener = start(patch.object(radar.urllib.request, 'build_opener')).return_value
        self.sleep = start(patch.object(radar.time, 'sleep'))
        self.response = Mock()
        self.response.headers = {'Content-Type': 'application/rss+xml', 'ETag': 'version2'}
        self.response.read.return_value = b'<rss><channel/></rss>'
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.opener.open.return_value = self.response

    def test_temporary_transport_failure_recovers_and_keeps_conditional_headers(self):
        errors = [urllib.error.URLError(ssl.SSLEOFError(8, 'TLS EOF')),
                  urllib.error.URLError(TimeoutError('timeout')), ConnectionResetError('reset')]
        for error in errors:
            with self.subTest(error=error):
                self.opener.open.reset_mock()
                self.sleep.reset_mock()
                self.opener.open.side_effect = [error, self.response]
                result = radar.fetch(self.url, {'If-None-Match': 'version1'})
                self.assertEqual(result, b'<rss><channel/></rss>')
                self.assertEqual(self.opener.open.call_count, 2)
                self.sleep.assert_called_once_with(0.5)
                for call in self.opener.open.call_args_list:
                    self.assertEqual(call.args[0].get_header('If-none-match'), 'version1')
                self.assertEqual(radar.fetch.metadata.value['ETag'], 'version2')

    def test_repeated_failure_stops_after_three_attempts(self):
        self.opener.open.side_effect = urllib.error.URLError(ssl.SSLEOFError(8, 'TLS EOF'))
        radar.fetch.metadata.value = {'ETag': 'stale'}
        with self.assertRaises(urllib.error.URLError):
            radar.fetch(self.url)
        self.assertEqual(self.opener.open.call_count, 3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [0.5, 1.0])
        self.assertEqual(radar.fetch.metadata.value, {})

    def test_certificate_and_other_tls_errors_are_not_retried(self):
        for reason in [ssl.SSLCertVerificationError(1, 'hostname mismatch'),
                       ssl.SSLError(1, 'TLS handshake rejected')]:
            with self.subTest(reason=reason):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = urllib.error.URLError(reason)
                with self.assertRaises(urllib.error.URLError):
                    radar.fetch(self.url)
                self.assertEqual(self.opener.open.call_count, 1)
        self.sleep.assert_not_called()

    def test_http_errors_including_not_modified_and_limits_are_not_retried(self):
        for code in [304, 401, 403, 404, 429, 503]:
            with self.subTest(code=code):
                self.opener.open.reset_mock()
                error = urllib.error.HTTPError(self.url, code, 'HTTP response', {}, None)
                self.opener.open.side_effect = error
                with self.assertRaises(urllib.error.HTTPError) as result:
                    radar.fetch(self.url)
                self.assertIs(result.exception, error)
                self.assertEqual(self.opener.open.call_count, 1)
        self.sleep.assert_not_called()

    def test_incomplete_payload_is_discarded_before_retry(self):
        self.response.read.side_effect = [http.client.IncompleteRead(b'partial', 10),
                                          b'<rss><channel/></rss>']
        self.assertEqual(radar.fetch(self.url), b'<rss><channel/></rss>')
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertEqual(self.response.__exit__.call_count, 2)

    def test_retry_revalidates_dns_and_stops_if_address_becomes_private(self):
        self.validate.side_effect = [None, ValueError('private address')]
        self.opener.open.side_effect = urllib.error.URLError(TimeoutError('timeout'))
        with self.assertRaisesRegex(ValueError, 'private address'):
            radar.fetch(self.url)
        self.assertEqual(self.validate.call_count, 2)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_redirects_are_validated_before_following(self):
        radar.fetch(self.url)
        handler = radar.urllib.request.build_opener.call_args.args[0]
        self.validate.side_effect = ValueError('private redirect')
        with self.assertRaisesRegex(ValueError, 'private redirect'):
            handler.redirect_request(Mock(), Mock(), 302, 'redirect', {}, 'http://127.0.0.1/')

    def test_response_limit_does_not_retry_or_publish_metadata(self):
        self.response.headers = {'Content-Type': 'text/html', 'ETag': 'invalid'}
        self.response.read.return_value = b'x' * 5_000_001
        with self.assertRaisesRegex(ValueError, '5 MB'):
            radar.fetch(self.url)
        self.assertEqual(self.opener.open.call_count, 1)
        self.sleep.assert_not_called()
        self.assertEqual(radar.fetch.metadata.value, {})


if __name__ == '__main__':
    unittest.main()
