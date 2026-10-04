import json
import os
import asyncio
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch,Mock,AsyncMock
import radar
import content_store as content
import readable
import feed_reader
sys.path.insert(0,str(Path(__file__).parent/'native'))
from browser_worker import Browsers,Paused,detect_block,identity
from jobs import Jobs
from transcribe import transcript,youtube_id,prepare,decode_audio
from manual_login import ManualLogin

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patch=patch.object(radar,'DB',self.root/'radar.sqlite3');self.patch.start();radar.init()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_decoder_limit_stops_child_that_ignores_termination(self):
        chunks=self.root/'chunks';chunks.mkdir()
        script="import os,signal,time,sys; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); p=Path(sys.argv[1]); (p/'pid').write_text(str(os.getpid())); (p/'00000.wav').write_bytes(b'x'*64); time.sleep(60)"
        started=time.monotonic()
        with self.assertRaisesRegex(ValueError,'解码音频超过'):
            decode_audio([sys.executable,'-c',script,str(chunks)],chunks,maximum=16)
        self.assertLess(time.monotonic()-started,8)
        with self.assertRaises(ProcessLookupError):os.kill(int((chunks/'pid').read_text()),0)
    def test_rss_enclosure_transcript_and_full_body(self):
        xml=b'''<rss xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>AI podcast</title><link>https://example.org/ep</link><enclosure url="https://cdn.example.org/a.mp3" type="audio/mpeg"/><podcast:transcript url="https://cdn.example.org/a.vtt" type="text/vtt"/><content:encoded>&lt;p&gt;Full article&lt;/p&gt;</content:encoded></item></channel></rss>'''
        row=radar.parse_feed(xml)[0];self.assertEqual(row['media']['type'],'podcast');self.assertEqual(row['body'],'Full article');self.assertTrue(row['media']['transcript_url'].endswith('.vtt'))
    def test_full_text_shared_and_preserves_annotations(self):
        source={'id':'manual-import','name':'Test','region':'全球','language':'en','kind':'播客'}
        row={'url':'https://example.org/ep','title':'GPU model','body':'long content '*300,'media':{'url':'https://example.org/audio.mp3'}}
        with radar.connect() as c:
            self.assertEqual(radar.put(c,source,row),1);self.assertEqual(radar.put(c,source,row),0)
            a=c.execute('SELECT id FROM articles').fetchone()[0]
            self.assertGreater(len(content.info(c,a)['body']),1200)
            c.execute("UPDATE articles SET note='my research' WHERE id=?",(a,));content.remove(c,a);radar.put(c,source,row)
            self.assertEqual(c.execute('SELECT note FROM articles WHERE id=?',(a,)).fetchone()[0],'my research')
    def test_existing_completed_job_reused(self):
        with radar.connect() as c:
            source={'id':'manual-import','name':'Test','region':'全球','language':'en','kind':'视频'}
            radar.put(c,source,dict(url='https://www.youtube.com/watch?v=abcdefghijk',title='AI',media={'type':'youtube'}))
            aid=c.execute('SELECT id FROM articles').fetchone()[0];content.attach_job(c,aid,{'id':'cached'})
            with patch.object(content.native_client,'call',return_value={'id':'cached','status':'completed'}) as call:
                self.assertEqual(content.extract(c,aid)['id'],'cached');self.assertEqual(call.call_count,1)
    def test_background_job_archives_without_open_detail(self):
        with radar.connect() as c:
            radar.put(c,{'id':'manual-import','name':'Podcast','region':'全球','language':'en','kind':'播客'},dict(url='https://example.org/episode',title='AI',media={'type':'podcast','url':'https://example.org/audio.mp3'},body='Show notes'))
            aid=c.execute('SELECT id FROM articles').fetchone()[0];content.attach_job(c,aid,{'id':'job'})
            with patch.object(content.native_client,'call',return_value={'status':'completed','result':{'text':'full audio transcript','segments':[],'origin':'local-asr'}}):content.sync_jobs(c)
            self.assertEqual(content.info(c,aid)['body'],'full audio transcript')
    def test_member_connection_opens_site_home(self):
        self.assertEqual(content.connection_for({'url':'https://example.org/feed'})['url'],'https://example.org/')
    def test_legacy_x_root_cannot_claim_author_capture(self):
        with self.assertRaisesRegex(ValueError,'作者主页'):content.connection_for({'url':'https://x.com/'})
    def test_feed_conditional_304_preserves_media(self):
        raw=b'<rss><channel><item><title>GPU</title><link>https://example.org/a</link></item></channel></rss>'
        with radar.connect() as c:c.execute('INSERT INTO feed_cache VALUES(?,?,?,?)',('https://example.org/feed','version1','yesterday',raw))
        fetch=Mock(side_effect=urllib.error.HTTPError('https://example.org/feed',304,'Not modified',{},None))
        rows,_,_=feed_reader.read({'id':'feed','url':'https://example.org/feed'},{'db':radar.DB,'fetch':fetch,'parse_feed':radar.parse_feed})
        self.assertEqual(rows[0]['title'],'GPU');self.assertEqual(fetch.call_args.kwargs['headers']['If-None-Match'],'version1')
    def test_blog_rejects_gate(self):
        with self.assertRaises(ValueError):readable.extract('<article>Subscribe to continue '+('preview '*100)+'</article>')
        self.assertIn('正文',readable.extract('<article><script>secret()</script><p>'+('正文内容 '*100)+'</p></article>'))
        self.assertNotIn('secret',readable.extract('<article><script>secret()</script><p>'+('正文内容 '*100)+'</p></article>'))
    def test_reddit_backup_is_scrubbed(self):
        source={'id':'manual-import','name':'Reddit','region':'全球','language':'en','kind':'论坛'}
        with radar.connect() as c:radar.put(c,source,dict(url='https://www.reddit.com/r/test/comments/abc/',title='AI model',body='private cached text'))
        with patch.dict('os.environ',{'RADAR_BACKUP_DIR':str(self.root/'backups')}):file=radar.backup()
        with sqlite3.connect(file) as c:self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],0)
        with radar.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],1)
    def test_old_backup_scrub_preserves_own_notes(self):
        folder=self.root/'legacy';folder.mkdir();file=folder/'old.sqlite3'
        with radar.connect() as c:
            radar.put(c,{'id':'manual-import','name':'Reddit','region':'全球','language':'en','kind':'论坛'},dict(url='https://www.reddit.com/r/test/comments/abc/',title='AI model',body='provider content'))
            c.execute("UPDATE articles SET note='my own research'");c.commit()
            with sqlite3.connect(file) as out:c.backup(out)
        content.scrub_backups(folder)
        with sqlite3.connect(file) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT note FROM saved_annotations').fetchone()[0],'my own research')
    def test_bind_rss_member_keeps_feed_adapter(self):
        with radar.connect() as c:
            c.execute('INSERT INTO source_connections VALUES(?,?,?)',('nvidia','blog-test','rss-browser'))
            config=json.loads(c.execute("SELECT config FROM sources WHERE id='nvidia'").fetchone()[0])
            decorated=content.decorate(c,config);self.assertEqual(decorated['adapter'],'rss-browser')
            self.assertEqual(decorated['url'],config['url'])
    def test_opml_rejects_private_source(self):
        with self.assertRaises(ValueError):content.opml('<opml><body><outline xmlUrl="http://127.0.0.1/rss"/></body></opml>')
    def test_transcript_formats(self):
        data=transcript('WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello AI\n\n')
        self.assertEqual(data['segments'][0]['start'],1);self.assertEqual(data['text'],'Hello AI')
        self.assertEqual(transcript('{"events":[{"tStartMs":1000,"dDurationMs":2000,"segs":[{"utf8":"你好"}]}]}','json')['segments'][0]['end'],3)
    def test_youtube_identity(self):
        self.assertEqual(youtube_id('https://youtu.be/abcdefghijk'),'abcdefghijk')
        self.assertEqual(youtube_id('https://youtube.com/watch?v=abcdefghijk&t=2'),'abcdefghijk')
        self.assertIsNone(youtube_id('https://evil.test/watch?v=abcdefghijk'))
    def test_cover_image_is_not_audio(self):
        rows=radar.parse_feed(b'<rss><channel><item><title>AI news</title><link>https://example.org/a</link><enclosure type="image/jpeg" url="https://example.org/cover.jpg"/></item></channel></rss>')
        self.assertNotIn('media',rows[0])
    def test_member_preview_is_not_full_body(self):
        rows=radar.parse_feed(b'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>AI</title><link>https://example.org/a</link><content:encoded>Preview. This post is for paid subscribers</content:encoded></item></channel></rss>')
        self.assertNotIn('body',rows[0]);self.assertIn('body_error',rows[0])
    def test_wechat_sharing_links_reuse_publisher(self):
        import interests
        with radar.connect() as c:
            s={'url':'https://mp.weixin.qq.com/s/one','adapter':'wechat-rss','platform':'wechat','kind':'公众号','name':'测试公众号','bridge_feed':'http://127.0.0.1:43203/feed/MP_abc.rss'}
            one=interests.register(c,s,s['url'],radar.canonical,'ai')
            s=dict(s,url='https://mp.weixin.qq.com/s/two',bridge_feed='http://127.0.0.1:43203/api/v1/wx/feed/MP_abc.xml?is_update=false')
            two=interests.register(c,s,s['url'],radar.canonical,'coding-agent')
            self.assertEqual(one['source_id'],two['source_id'])
    def test_wechat_feed_without_share_link_preserves_identity_and_topic_filter(self):
        import collection_api
        xml='<rss><channel><title>Publisher</title></channel></rss>'
        with radar.connect() as c,patch.object(collection_api.native_client,'call',return_value={'feed':xml}):
            body=dict(feed_url='http://127.0.0.1:43203/feed/MP_WXS_3076555400.rss',name='Kevin策略研究',watch_id='ai',include_all=False)
            one=collection_api.post('/api/wechat-source',body,c,radar)
            self.assertIn('__biz=MzA3NjU1NTQwMA%3D%3D',one['config']['url'])
            self.assertEqual(c.execute('SELECT include_all FROM watch_sources WHERE source_id=? AND topic_id=?',(one['source_id'],'ai')).fetchone()[0],0)
            again=collection_api.post('/api/wechat-source',dict(body,watch_id='coding-agent'),c,radar)
            other=collection_api.post('/api/wechat-source',dict(body,feed_url='http://127.0.0.1:43203/feed/MP_WXS_1234567890.rss'),c,radar)
            self.assertEqual(one['source_id'],again['source_id'])
            self.assertNotEqual(one['source_id'],other['source_id'])
    def test_wechat_unknown_feed_requires_share_link_and_rejects_invalid_rules(self):
        import collection_api
        body=dict(feed_url='http://127.0.0.1:43203/feed/MP_other.rss',watch_id='ai')
        with radar.connect() as c,patch.object(collection_api.native_client,'call',return_value={'feed':'<rss><channel/></rss>'}):
            with self.assertRaisesRegex(ValueError,'补充'):collection_api.post('/api/wechat-source',body,c,radar)
            with self.assertRaisesRegex(ValueError,'分享'):collection_api.post('/api/wechat-source',dict(body,url='https://example.org/article'),c,radar)
            with self.assertRaisesRegex(ValueError,'布尔'):collection_api.post('/api/wechat-source',dict(body,include_all='false'),c,radar)
    def youtube_mock(self,info,failed=False):
        import types
        media=self.root/'audio.webm';media.write_bytes(b'media')
        ydl=Mock();ydl.extract_info=Mock(side_effect=ValueError('restricted')) if failed else Mock(return_value=info)
        ydl.prepare_filename.return_value=str(media);ydl.__enter__=Mock(return_value=ydl);ydl.__exit__=Mock(return_value=False)
        return patch.dict(sys.modules,{'yt_dlp':types.SimpleNamespace(YoutubeDL=Mock(return_value=ydl))}),ydl
    def test_youtube_prefers_manual_then_automatic_caption(self):
        captions=self.root/'captions.vtt';captions.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello AI\n\n')
        for field,origin in [('subtitles','manual-caption'),('automatic_captions','automatic-caption')]:
            module,ydl=self.youtube_mock({field:{'en':[{'ext':'vtt','url':'https://example.org/captions'}]}})
            with module,patch('transcribe.download',return_value=captions):
                audio,result=prepare({'url':'https://youtu.be/abcdefghijk'},self.root,Mock())
                self.assertIsNone(audio);self.assertEqual(result['origin'],origin);self.assertEqual(ydl.extract_info.call_count,1)
    def test_youtube_without_caption_uses_audio(self):
        module,ydl=self.youtube_mock({})
        with module:
            audio,result=prepare({'url':'https://youtu.be/abcdefghijk'},self.root,Mock())
            self.assertTrue(audio.exists());self.assertIsNone(result);self.assertTrue(ydl.extract_info.call_args.kwargs['download'])
    def test_youtube_restriction_stops_with_explicit_reason(self):
        module,_=self.youtube_mock({},True)
        with module,self.assertRaisesRegex(ValueError,'不可获取'):prepare({'url':'https://youtu.be/abcdefghijk'},self.root,Mock())
    def test_publisher_transcript_and_invalid_audio(self):
        captions=self.root/'captions.txt';captions.write_text('Provided by the publisher')
        with patch('transcribe.download',return_value=captions):
            audio,result=prepare({'media':{'transcript_url':'https://example.org/transcript.txt'}},self.root,Mock())
            self.assertIsNone(audio);self.assertEqual(result['origin'],'publisher-transcript')
        with patch('transcribe.download',side_effect=ValueError('404 音频链接已失效')),self.assertRaisesRegex(ValueError,'404'):
            prepare({'media':{'url':'https://example.org/expired.mp3'}},self.root,Mock())

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        def db():
            c=sqlite3.connect(self.root/'native.sqlite');c.row_factory=sqlite3.Row;return c
        self.db=db;self.browser=Browsers(self.root,db)
        with db() as c:c.execute("INSERT INTO connections(id,platform,url,status) VALUES('x','x','https://x.com/test','ready')")
    def tearDown(self):self.tmp.cleanup()
    def test_manual_login_does_not_attach_automation_to_sign_in(self):
        profile=self.root/'profiles'/'x'
        child=Mock(pid=4242);child.poll.return_value=None
        with patch('manual_login.subprocess.Popen',return_value=child) as launch:
            self.browser.manual.open('x','/project/Chromium',profile,'https://x.com/home')
        command=launch.call_args.args[0]
        self.assertIn('--user-data-dir='+str(profile),command)
        self.assertFalse(any('automation' in a or 'remote-debugging' in a or 'disable-blink' in a for a in command))
        with self.assertRaisesRegex(ValueError,'关闭'):
            asyncio.run(self.browser.action('x','confirm'))
        self.assertIsNone(self.browser.playwright)
    def test_manual_login_lock_survives_service_restart(self):
        profile=self.root/'profiles'/'x'
        child=Mock(pid=4242);child.poll.return_value=None
        with patch('manual_login.subprocess.Popen',return_value=child):
            self.browser.manual.open('x','/project/Chromium',profile,'https://x.com/home')
        self.browser.state('x','login_open','Login')
        command='/project/Chromium --user-data-dir='+str(profile)+' --new-window https://x.com/home'
        with patch('manual_login.subprocess.run',return_value=Mock(stdout=command)):
            restored=Browsers(self.root,self.db)
            self.assertEqual(restored.get('x')['status'],'login_open')
            with self.assertRaisesRegex(ValueError,'关闭'):asyncio.run(restored.context('x'))
        with patch('manual_login.subprocess.run',return_value=Mock(stdout='')):
            self.assertFalse(restored.manual.in_use('x'))
        self.assertNotIn('x',ManualLogin(self.root).records)
    def test_macos_collector_uses_human_login_keychain(self):
        launch=AsyncMock(return_value=Mock())
        self.browser.playwright=Mock(chromium=Mock(launch_persistent_context=launch))
        with patch('browser_worker.sys.platform','darwin'):
            asyncio.run(self.browser.context('x'))
        self.assertEqual(launch.call_args.args[0],str(self.root/'profiles'/'x'))
        self.assertEqual(set(launch.call_args.kwargs['ignore_default_args']),{'--use-mock-keychain','--password-store=basic'})
    def test_login_confirmation_navigation_failure_preserves_session(self):
        page=Mock(url='about:blank',goto=AsyncMock(side_effect=TimeoutError('page timeout')))
        ctx=Mock(pages=[page]);self.browser.contexts['x']=ctx
        with self.assertRaisesRegex(ValueError,'网络'):
            asyncio.run(self.browser.action('x','confirm'))
        self.assertEqual(self.browser.get('x')['status'],'network_error')
        ctx.close.assert_not_called()
    def test_reddit_confirmation_exposes_existing_account_menu(self):
        with self.db() as c:c.execute("INSERT INTO connections(id,platform,url,status) VALUES('reddit','reddit','https://www.reddit.com/','login_open')")
        page=Mock(url='https://www.reddit.com/',bring_to_front=AsyncMock(),goto=AsyncMock())
        page.locator.return_value=Mock(inner_text=AsyncMock(return_value='Reddit'),count=AsyncMock(return_value=0))
        self.browser.contexts['reddit']=Mock(pages=[page])
        with self.assertRaisesRegex(ValueError,'账号菜单'):
            asyncio.run(self.browser.action('reddit','confirm'))
        self.assertEqual(self.browser.get('reddit')['status'],'login_open')
        page.bring_to_front.assert_awaited_once();page.goto.assert_not_called()
    def test_six_hour_source_and_account_spacing(self):
        self.browser.reserve('x','one')
        with self.assertRaises(Paused) as err:self.browser.reserve('x','one')
        self.assertEqual(err.exception.status,'scheduled')
        with self.assertRaises(Paused):self.browser.reserve('x','two')
    def test_daily_budget_is_persistent(self):
        with self.db() as c:
            for i in range(20):c.execute('INSERT INTO visits VALUES(?,?,?)',('x',str(i),time.time()-400))
        another=Browsers(self.root,self.db)
        with self.assertRaises(Paused) as err:another.reserve('x','new')
        self.assertEqual(err.exception.status,'budget')
    def test_manual_login_stops_background_reservations(self):
        self.browser.state('x','login_open','Login')
        with self.assertRaises(Paused) as err:self.browser.reserve('x','one')
        self.assertEqual(err.exception.status,'login_open')
    def test_detection_and_retry_header(self):
        for code,status in [(401,'needs_login'),(403,'needs_login'),(429,'cooldown')]:
            with self.assertRaises(Paused) as err:detect_block('','https://x.com/test',code,'120')
            self.assertEqual(err.exception.status,status)
        with self.assertRaises(Paused) as err:detect_block('Verify you are human','https://x.com/test')
        self.assertEqual(err.exception.status,'challenge')
    def test_profiles_are_site_specific(self):
        self.assertNotEqual(identity('blog','https://one.example.org'),identity('blog','https://two.example.org'))
        with self.assertRaises(ValueError):identity('x','https://x.com.evil.org')
    def test_job_dedup_cancel_recovery(self):
        jobs=Jobs(self.root,self.db)
        spec={'url':'https://youtube.com/watch?v=abcdefghijk'}
        one=jobs.submit(spec);two=jobs.submit({'url':'https://youtu.be/abcdefghijk'})
        self.assertEqual(one['id'],two['id']);self.assertEqual(jobs.cancel(one['id'])['status'],'cancelled')
        retry=jobs.submit(spec);self.assertEqual(retry['status'],'queued')
        with self.db() as c:c.execute("UPDATE jobs SET status='running'")
        restarted=Jobs(self.root,self.db);self.assertEqual(restarted.get(one['id'])['status'],'queued')
    def test_audio_cache_cleanup_preserves_transcript(self):
        jobs=Jobs(self.root,self.db);j=jobs.submit({'url':'https://youtu.be/abcdefghijk'});folder=jobs.root/j['id']
        (folder/'audio.mp3').write_bytes(b'123');(folder/'result.json').write_text('{"text":"keep"}')
        with self.db() as c:c.execute("UPDATE jobs SET status='completed',updated_at=?",(time.time()-8*86400,))
        jobs.cleanup();self.assertFalse((folder/'audio.mp3').exists());self.assertTrue((folder/'result.json').exists())
    def test_cancelled_worker_cannot_be_overwritten_by_retry(self):
        jobs=Jobs(self.root,self.db);spec={'url':'https://youtu.be/abcdefghijk'}
        j=jobs.submit(spec);jobs.active=j['id'];jobs.cancel(j['id'])
        with self.assertRaises(ValueError):jobs.submit(spec)
        jobs.active=None;self.assertEqual(jobs.submit(spec)['status'],'queued')

if __name__=='__main__':unittest.main()
