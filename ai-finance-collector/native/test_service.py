"""Isolated native HTTP boundaries without a lifespan worker or external access."""
import importlib
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse

import httpx


class NativeServiceHTTPTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='info-hunter-native-http-')
        cls.root = Path(cls.temporary.name)
        cls.environment = patch.dict(os.environ, {
            'RADAR_NATIVE_DATA': str(cls.root / 'native'),
            'RADAR_DATA_DIR': str(cls.root / 'data'),
            'RADAR_BACKUP_DIR': str(cls.root / 'backups'),
            'RADAR_CONNECTIONS_FILE': str(cls.root / 'connections.local.json'),
            'HF_HOME': str(cls.root / 'models'),
            'PLAYWRIGHT_BROWSERS_PATH': str(cls.root / 'browsers'),
            'HF_HUB_OFFLINE': '1',
        })
        cls.environment.start()
        cls.previous_path = list(sys.path)
        native = Path(__file__).resolve().parent
        sys.path[:0] = [str(native), str(native.parent)]
        cls.previous_service = sys.modules.pop('service', None)
        try:
            cls.service = importlib.import_module('service')
        except BaseException:
            sys.path[:] = cls.previous_path
            cls.environment.stop()
            cls.temporary.cleanup()
            if cls.previous_service is not None:
                sys.modules['service'] = cls.previous_service
            raise
        cls.native_root = cls.service.ROOT
        cls.worker = patch.object(cls.service.jobs, 'worker', side_effect=AssertionError('worker must stay stopped'))
        cls.worker_mock = cls.worker.start()
        cls.dns = patch('socket.getaddrinfo', side_effect=AssertionError('external DNS is disabled'))
        cls.dns.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.worker_mock.assert_not_called()
        finally:
            cls.worker.stop()
            cls.dns.stop()
            cls.service.jobs.stop.set()
            sys.modules.pop('service', None)
            if cls.previous_service is not None:
                sys.modules['service'] = cls.previous_service
            sys.path[:] = cls.previous_path
            cls.environment.stop()
            cls.temporary.cleanup()

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.service.app),
            base_url='http://native.test',
        )
        self.headers = {'Authorization': 'Bearer ' + self.service.TOKEN}

    async def asyncTearDown(self):
        await self.client.aclose()

    def assert_uploads_cleaned(self):
        self.assertEqual(list(self.native_root.glob('*.upload')), [])

    async def test_authentication_and_origin_rejected(self):
        for headers in ({}, {'Authorization': 'Bearer synthetic-invalid'}):
            response = await self.client.get('/v1/health', headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {'detail': '需要本机访问令牌'})
        response = await self.client.get('/v1/health', headers={
            **self.headers, 'Origin': 'http://127.0.0.1:43187',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'detail': '请通过信息雷达或本地客户端访问'})

    async def test_token_is_private_and_reused(self):
        import state
        token_path, token = state.prepare(self.native_root)
        self.assertEqual(token_path, self.service.TOKEN_PATH)
        self.assertEqual(token, self.service.TOKEN)
        self.assertTrue(token)
        self.assertEqual(self.native_root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    async def test_health_and_connections_without_worker(self):
        health = await self.client.get('/v1/health', headers=self.headers)
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()['ready'])
        self.assertIn('storage', health.json())
        connections = await self.client.get('/v1/connections', headers=self.headers)
        self.assertEqual(connections.status_code, 200)
        self.assertEqual(connections.json()['items'], [])
        self.assertIn('storage', connections.json())

    async def test_uploaded_bytes_forwarded_and_temporary_removed(self):
        captured = {}
        def submit(spec, filename):
            captured.update(spec=spec, payload=Path(filename).read_bytes())
            return {'id': 'a' * 32, 'status': 'queued'}
        with patch.object(self.service.jobs, 'submit', side_effect=submit) as submit_job:
            response = await self.client.post('/v1/transcription-jobs', headers=self.headers,
                files={'file': ('synthetic.wav', b'synthetic-media', 'audio/wav')},
                data={'language': 'zh'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'queued')
        self.assertEqual(captured, {'spec': {'language': 'zh'}, 'payload': b'synthetic-media'})
        submit_job.assert_called_once()
        self.assert_uploads_cleaned()

    async def test_empty_upload_rejected_and_temporary_removed(self):
        with patch.object(self.service.jobs, 'submit') as submit_job:
            response = await self.client.post('/v1/transcription-jobs', headers=self.headers,
                files={'file': ('empty.wav', b'', 'audio/wav')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'detail': '文件为空'})
        submit_job.assert_not_called()
        self.assert_uploads_cleaned()

    async def test_upload_limit_closes_file_and_removes_temporary(self):
        import media_api
        class OversizedChunk:
            def __len__(self):
                return 512 * 1024 * 1024 + 1
        class Upload:
            closed = False
            async def read(self, maximum):
                return OversizedChunk()
            async def close(self):
                self.closed = True
        upload = Upload()
        with patch.object(self.service.jobs, 'submit') as submit_job:
            with self.assertRaisesRegex(ValueError, '文件不能超过512 MB'):
                await media_api.upload(upload, '', self.native_root, self.service.jobs)
        self.assertTrue(upload.closed)
        submit_job.assert_not_called()
        self.assert_uploads_cleaned()

    async def test_media_urls_resolved_and_spec_preserved(self):
        body = {'url': '', 'media': {
            'url': 'https://media.example.test/audio.mp3',
            'transcript_url': 'https://media.example.test/transcript.vtt',
        }, 'language': 'en'}
        answer = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 443))]
        with patch('socket.getaddrinfo', return_value=answer) as resolve, \
                patch.object(self.service.jobs, 'submit', return_value={'status': 'queued'}) as submit_job:
            response = await self.client.post('/v1/media-jobs', headers=self.headers, json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve.call_count, 2)
        submit_job.assert_called_once_with(body)

    async def test_media_private_destination_rejected_before_submission(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', 443))]
        with patch('socket.getaddrinfo', return_value=answer), \
                patch.object(self.service.jobs, 'submit') as submit_job:
            response = await self.client.post('/v1/media-jobs', headers=self.headers,
                json={'media': {'url': 'https://media.example.test/audio.mp3'}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'detail': '来源不能指向本机或内部网络'})
        submit_job.assert_not_called()

    async def test_bridge_rejects_other_destinations_before_fetch(self):
        urls = [
            'https://127.0.0.1:43203/feed/synthetic.rss',
            'http://127.0.0.1:43204/feed/synthetic.rss',
            'http://example.test:43203/feed/synthetic.rss',
            'http://synthetic:synthetic@localhost:43203/feed/synthetic.rss',
            'http://127.0.0.1:43203/admin',
        ]
        with patch('urllib.request.build_opener') as build:
            for url in urls:
                with self.subTest(url=url):
                    response = await self.client.post('/v1/wechat/feed', headers=self.headers, json={'url': url})
                    self.assertEqual(response.status_code, 400)
            build.assert_not_called()

    async def test_bridge_reads_cache_with_proxy_bypass_and_no_redirect(self):
        opener = MagicMock()
        response_body = opener.open.return_value.__enter__.return_value
        response_body.read.return_value = b'<rss><channel/></rss>'
        with patch('urllib.request.build_opener', return_value=opener) as build:
            response = await self.client.post('/v1/wechat/feed', headers=self.headers,
                json={'url': 'http://localhost:43203/api/v1/wx/feed/synthetic.rss?is_update=true&limit=1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'feed': '<rss><channel/></rss>'})
        url = opener.open.call_args.args[0]
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query), {'is_update': ['false'], 'limit': ['1']})
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 30})
        response_body.read.assert_called_once_with(32_000_001)
        proxy, redirect = build.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(None, None, 302, 'redirect', {}, 'https://example.test/'))

    async def test_bridge_redirect_failure_does_not_follow(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError(
            'http://localhost:43203/feed/synthetic.rss', 302, 'redirect', {}, None)
        with patch('urllib.request.build_opener', return_value=opener):
            response = await self.client.post('/v1/wechat/feed', headers=self.headers,
                json={'url': 'http://localhost:43203/feed/synthetic.rss'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'detail': '公众号桥接未连接或订阅不可用，请检查扫码授权与订阅地址'})
        opener.open.assert_called_once()


if __name__ == '__main__':
    unittest.main()
