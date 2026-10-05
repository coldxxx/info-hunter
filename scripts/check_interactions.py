"""Headless UI acceptance against synthetic API state and a temporary static build.

Requires Playwright (already in native/requirements.lock) and its browser cache.
No real database, connection configuration, profiles, platform or model is used.
"""
import functools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from check_frontend import copy_frontend
from playwright.sync_api import sync_playwright, expect


def fixture():
    topic = dict(id='coding-agent', name='隔离主题', description='fixture', keywords=['AI'], exclude=[], regions=[], enabled=True, news_search=False, content_profile='developer', article_count=2, source_count=1)
    sources = []
    for number in range(30):
        ident = 'fixture-%02d' % number
        sources.append(dict(id=ident, status='成功', checked_at='2026-10-04T00:00:00Z', success_at='2026-10-04T00:00:00Z', error='', last_count=number, followed=number == 0, topics=[dict(id=topic['id'], name=topic['name'], enabled=True, include_all=False)] if number == 0 else [], include_all=False, connection_status='无需登录', body_count=number % 2, next_at=0, preference=dict(score=10, interval_hours=6, reason='fixture', signals={}), config=dict(adapter='rss', enabled=True, name='Fixture %02d' % number, region='全球', language='en', kind='博客', url='https://example.org/%s' % ident, note='synthetic public fixture')))
    article = dict(id='article-fixture', title='隔离资料 AI', url='https://example.org/article', excerpt='Synthetic archived text', publisher='Fixture Publisher', region='全球', language='en', kind='博客', topics=[], published_at='2026-10-04T00:00:00Z', collected_at='2026-10-04T01:00:00Z', source_id='fixture-00', source_name='Fixture 00', starred=0, note='fixture note', review='未核验', duplicate_count=1, duplicates=[], engineering_category='工程实践')
    config = dict(enabled=False, mode='review', embedding_model='fixture-embed', judge_model='fixture-judge', embedding_url='', judge_url='', candidate_threshold=.5, auto_threshold=.95, top_k=5, window_days=7, daily_pair_limit=10)
    semantic_article = {key: article[key] for key in ('id', 'title', 'url', 'excerpt', 'publisher', 'language', 'published_at', 'kind')}
    semantic_article.update(review_text='fixture original', has_full_text=True, truncated=False)
    pair = dict(id='pair-fixture', left=semantic_article, right=dict(semantic_article, id='article-fixture-2', title='另一条隔离资料'), similarity=.8, relation='related', model='fixture', status='review', reviewed_relation=None, review_note=None, updated_at=42, decision=dict(confidence=.8, reason='fixture reasoning', evidence_a='a', evidence_b='b', guards=[], text_scope='full', same_event=False, new_information=True, contradiction=False))
    return dict(topic=topic, sources=sources, article=article, config=config, pair=pair, writes=[], delete_fail=True, requests=[], outside=[])


def router(state, origin):
    def handle(route):
        request = route.request
        parsed = urlsplit(request.url)
        if not request.url.startswith(origin + '/'):
            state['outside'].append(request.url)
            return route.abort()
        if not parsed.path.startswith('/api/'):
            return route.continue_()
        q = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        path = parsed.path.removeprefix('/api/')
        state['requests'].append((request.method, path))
        status = 200
        if request.method == 'POST':
            body = ({'multipart': request.headers.get('content-type', '')} if path == 'media-upload' else request.post_data_json or {})
            state['writes'].append((path, body))
            value = {'ok': True}
            if path == 'source-delete':
                if state['delete_fail']:
                    state['delete_fail'] = False
                    status = 400; value = {'error': 'synthetic deletion failure'}
                else:
                    state['sources'] = [s for s in state['sources'] if s['id'] != body['source_id']]
            elif path == 'watch-sources':
                for s in state['sources']:
                    if s['id'] in body['source_ids']: s['followed'] = True
                value = {'added': len(body['source_ids'])}
            elif path == 'source':
                value = {'config': {'note': 'synthetic saved'}}
            elif path == 'article':
                state['article'].update({k: body[k] for k in ('starred', 'note', 'review')})
            elif path == 'translate':
                value = {'enabled': False, 'queued': 0}
            elif path == 'semantic/review':
                state['pair']['reviewed_relation'] = body['relation']
            elif path == 'semantic/settings':
                state['config'].update(body)
        elif path == 'status': value = {'count': 1, 'busy': False, 'last_run': None}
        elif path == 'watch-topics': value = [state['topic']]
        elif path == 'sources': value = state['sources'] if q.get('all') == '1' or not q.get('watch_id') else [s for s in state['sources'] if s['followed']]
        elif path == 'source-detail':
            source = next(s for s in state['sources'] if s['id'] == q['id'])
            value = dict(source_id=source['id'], entry_url=source['config']['url'], query='', configured_adapter='rss', effective_adapter='rss', access=dict(mode='public', ready=True, message='fixture'), capture_strategy=dict(id='rss', name='RSS', adapter_name='RSS', description='fixture', parameters=[]), steps=[], topics=[], schedule=dict(interval_hours=6, enabled=True, baseline=True, policy=source['preference']), stats=dict(archived=1, in_topic=1), recent=[], last_run=None, next_at=0)
        elif path == 'articles': value = {'total': 1, 'items': [state['article']]}
        elif path == 'translations': value = {'enabled': False, 'items': {}}
        elif path == 'platform-connections': value = {'available': False, 'items': [], 'reddit': {'approval_confirmed': False}}
        elif path == 'content': value = {'body': 'isolated full text', 'origin': 'page', 'status': 'completed', 'segments': [{'start': 1, 'end': 3, 'text': 'caption'}], 'media': {'type': 'podcast', 'url': origin + '/fixture.wav'}}
        elif path == 'semantic/status': value = dict(config=state['config'], jobs={}, relations={}, awaiting=1, reviewed=0, collapsed=0, last_error='', auto_gate=dict(ready=False, requirement='fixture', report={}), budget=dict(used=0, limit=10, resumes_at=None), index=dict(total=1, indexed=1), events=[])
        elif path == 'semantic/pairs': value = {'total': 1, 'items': [state['pair']]}
        elif path == 'podcasts': value = {'items': [dict(name='Fixture Podcast', author='Fixture', feed_url='https://example.org/feed', url='https://example.org/podcast', updated_at='', reason='fixture')]}
        elif path == 'podcast-preview': value = {'feed_url': q['url'], 'language': 'en', 'episodes': [dict(title='Fixture Episode', url='https://example.org/episode', published_at='', matched_keywords=[])]}
        else: value = {}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value, ensure_ascii=False))
    return handle


def check(page, origin, state):
    passed = []
    def record(name):
        passed.append(name); print('PASS:', name, flush=True)
    page.goto(origin + '/?view=sources&keep=fixture#anchor')
    expect(page.get_by_role('heading', name=re.compile('全局来源库'))).to_be_visible()
    expect(page.get_by_label('搜索信息源')).to_be_visible()
    page.get_by_label('搜索信息源').fill('Fixture 02')
    expect(page.get_by_role('button', name='查看 Fixture 02 的采集流程', exact=True)).to_be_visible()
    assert 'src_q=Fixture' in page.url and 'keep=fixture' in page.url and page.url.endswith('#anchor')
    page.reload(); expect(page.get_by_label('搜索信息源')).to_have_value('Fixture 02')
    record('source filters and reload retain URL/path/hash/unknown params')
    page.get_by_role('button', name='清除筛选', exact=True).click()
    page.get_by_label('选择 Fixture 01', exact=True).check()
    page.get_by_role('button', name='下一页', exact=True).click()
    assert 'src_page=1' in page.url
    page.get_by_label('选择 Fixture 26', exact=True).check()
    page.get_by_role('button', name='查看 Fixture 26 的采集流程', exact=True).click()
    expect(page.get_by_role('heading', name='Fixture 26', exact=True)).to_be_visible()
    assert 'source_detail=fixture-26' in page.url
    page.go_back(); expect(page.get_by_label('选择 Fixture 26', exact=True)).to_be_checked()
    page.go_forward(); expect(page.get_by_role('heading', name='Fixture 26', exact=True)).to_be_visible()
    page.reload(); expect(page.get_by_role('heading', name='Fixture 26', exact=True)).to_be_visible()
    record('source detail direct URL/reload/back/forward and selection state before reload')
    page.keyboard.press('Escape'); expect(page.get_by_label('搜索信息源')).to_be_visible()
    page.get_by_role('button', name='上一页', exact=True).click()
    page.get_by_label('选择 Fixture 01', exact=True).check()
    page.get_by_role('button', name='下一页', exact=True).click()
    page.get_by_label('选择 Fixture 26', exact=True).check()
    page.get_by_role('button', name='加入「隔离主题」', exact=True).click()
    expect(page.get_by_role('button', name='清空选择', exact=True)).to_have_count(0)
    payload = next(body for path, body in state['writes'] if path == 'watch-sources')
    assert sorted(payload['source_ids']) == ['fixture-01', 'fixture-26'] and payload['include_all'] is False
    record('batch following keeps cross-page selection and original include_all default')
    page.get_by_role('button', name='新增信息源', exact=True).click()
    expect(page.locator('input[name=bind_topic]')).to_be_checked()
    expect(page.locator('input[name=include_all]')).to_be_checked()
    page.get_by_label('来源链接', exact=True).fill('https://example.org/new-feed')
    page.get_by_role('button', name='保存信息源', exact=True).click()
    expect(page.locator('#source-add-panel')).to_have_count(0)
    payload = next(body for path, body in state['writes'] if path == 'source')
    assert payload['include_all'] is True and payload['watch_id'] == 'coding-agent'
    record('add form payload/defaults and collapse on success')
    page.get_by_role('button', name='删除 Fixture 27', exact=True).click()
    page.get_by_role('button', name='确认删除', exact=True).click()
    expect(page.get_by_role('alertdialog')).to_be_visible()
    expect(page.get_by_role('alertdialog').get_by_role('alert')).to_contain_text('删除未完成，请重试。')
    page.get_by_role('button', name='确认删除', exact=True).click()
    expect(page.get_by_role('alertdialog')).to_have_count(0)
    expect(page.get_by_role('button', name='删除 Fixture 27', exact=True)).to_have_count(0)
    assert state['article']['note'] == 'fixture note'
    record('failed delete keeps dialog/target; success preserves archive annotation fixture')
    if '--source-batch' in sys.argv:
        assert not state['outside'], state['outside']
        return passed
    page.goto(origin + '/?article=article-fixture&keep=fixture')
    expect(page.locator('.detail h2')).to_have_text('隔离资料 AI')
    expect(page.get_by_role('textbox', name='研究笔记', exact=True)).to_have_value('fixture note')
    page.get_by_role('textbox', name='研究笔记', exact=True).fill('isolated edited note')
    page.get_by_role('combobox', name='核验状态', exact=True).select_option('已核验')
    page.get_by_role('button', name='保存笔记', exact=True).click()
    expect(page.locator('output.notice')).to_contain_text('笔记与核验状态已保存')
    page.reload(); expect(page.get_by_role('textbox', name='研究笔记', exact=True)).to_have_value('isolated edited note')
    expect(page.get_by_role('combobox', name='核验状态', exact=True)).to_have_value('已核验')
    # The player intentionally uses preload=none; load the synthetic audio before seeking.
    page.locator('audio').evaluate('(audio) => audio.load()')
    page.wait_for_function("document.querySelector('audio')?.readyState >= 1")
    page.get_by_role('button', name='00:00:01', exact=True).click()
    page.wait_for_function("document.querySelector('audio')?.currentTime >= 1")
    with page.expect_download() as event:
        page.get_by_role('button', name='导出 SRT', exact=True).click()
    download = event.value
    assert download.suggested_filename == 'article-fixture.srt'
    assert '00:00:01,000 --> 00:00:03,000' in Path(download.path()).read_text()
    page.locator('.media-upload input[type=file]').set_input_files({'name': 'fixture.wav', 'mimeType': 'audio/wav', 'buffer': b'synthetic-media'})
    page.wait_for_function("document.querySelector('.media-panel input[type=file]')?.disabled === false")
    assert next(body for path, body in state['writes'] if path == 'media-upload')['multipart'].startswith('multipart/form-data;')
    page.get_by_role('button', name='关闭', exact=True).click()
    page.wait_for_function("window.__blobs.created.every(url => window.__blobs.revoked.includes(url))")
    record('media playback timestamp, subtitle export/upload and Blob cleanup')
    assert 'article=' not in page.url
    page.get_by_role('button', name='隔离资料 AI', exact=True).click()
    assert 'article=article-fixture' in page.url
    page.go_back(); expect(page.locator('.detail')).to_have_count(0)
    page.go_forward(); expect(page.locator('.detail h2')).to_have_text('隔离资料 AI')
    record('article detail URL, annotations, reload and back/forward')
    page.get_by_label('搜索标题、摘要与笔记').fill('synthetic query')
    expect(page.get_by_label('搜索标题、摘要与笔记')).to_have_value('synthetic query')
    page.wait_for_function("new URLSearchParams(location.search).get('q') === 'synthetic query'")
    record('feed search retains URL state and debounce path')
    page.goto(origin + '/?view=topics&edit_topic=coding-agent')
    expect(page.get_by_role('textbox', name='主题名称', exact=True)).to_have_value('隔离主题')
    expect(page.get_by_role('combobox', name='内容侧重', exact=True)).to_have_value('developer')
    record('topic editor URL and developer profile')
    page.goto(origin + '/?view=sources&platform_panel=podcasts&podcast_q=AI')
    expect(page.get_by_role('heading', name='Fixture Podcast', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='订阅', exact=True)).to_be_disabled()
    page.get_by_role('button', name='验证并查看单集', exact=True).click()
    expect(page.get_by_role('button', name='订阅', exact=True)).to_be_enabled()
    assert 'podcast_feed=' in page.url
    page.reload(); expect(page.get_by_text('RSS 已验证 · 语言 en', exact=True)).to_be_visible()
    page.get_by_role('button', name='订阅', exact=True).click()
    payload = [body for path, body in state['writes'] if path == 'source'][-1]
    assert payload['feed_url'] == 'https://example.org/feed' and payload['include_all'] is True
    page.get_by_label('播客搜索关键词', exact=True).fill('new query')
    page.get_by_role('button', name='搜索节目', exact=True).click()
    expect(page.get_by_role('button', name='订阅', exact=True)).to_be_disabled()
    assert 'podcast_feed=' not in page.url and 'podcast_q=new+query' in page.url
    record('podcast deep URL/reload, verified preview gate and search reset')
    page.goto(origin + '/?view=sources&watch=&src_page=999999&keep=fixture')
    expect(page.get_by_role('combobox', name='关注主题', exact=True)).to_have_value('')
    expect(page.get_by_role('button', name='查看 Fixture 29 的采集流程', exact=True)).to_be_visible()
    assert 'src_page=999999' in page.url and 'watch=' in page.url
    record('explicit empty watch and out-of-range source page retain URL while display clamps')
    page.goto(origin + '/?view=semantic')
    expect(page.get_by_role('heading', name='资料关系复核', exact=True)).to_be_visible()
    note = page.get_by_label('复核备注', exact=True)
    note.fill('draft survives refresh')
    page.wait_for_function("document.querySelector('.semantic-panel') !== null")
    page.wait_for_timeout(5200)
    expect(note).to_have_value('draft survives refresh')
    page.get_by_role('button', name='保存复核', exact=True).click()
    payload = next(body for path, body in state['writes'] if path == 'semantic/review')
    assert payload['expected'] == 42 and payload['note'] == 'draft survives refresh'
    record('semantic polling retains draft and review version contract')
    assert not state['outside'], state['outside']
    return passed


def main():
    state = fixture()
    with tempfile.TemporaryDirectory(prefix='info-hunter-ui-') as temporary:
        target = Path(temporary)
        copy_frontend(target)
        if '--source-batch' in sys.argv:
            repo = Path(__file__).resolve().parent.parent
            for file in ('page.tsx', 'platform-panel.tsx', 'media-panel.tsx', 'semantic-panel.tsx'):
                (target / 'app' / file).write_bytes(subprocess.check_output(['git', 'show', '3e21457:ai-finance-radar/app/' + file], cwd=repo))
        subprocess.run(['npm', 'run', 'build:container'], cwd=target, check=True, stdout=subprocess.DEVNULL)
        if '--source-batch' in sys.argv:
            subprocess.run(['npm', 'run', 'build'], cwd=target, check=True, stdout=subprocess.DEVNULL)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_): pass
        with wave.open(str(target / 'container-dist' / 'fixture.wav'), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b'\0\0' * 32000)
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(target / 'container-dist')))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = 'http://127.0.0.1:%s' % server.server_port
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                page.set_default_timeout(8000)
                page.add_init_script('''window.__blobs={created:[],revoked:[]};
                    const create=URL.createObjectURL.bind(URL), revoke=URL.revokeObjectURL.bind(URL);
                    URL.createObjectURL=blob=>{const url=create(blob);window.__blobs.created.push(url);return url;};
                    URL.revokeObjectURL=url=>{window.__blobs.revoked.push(url);return revoke(url);};''')
                errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                page.route('**/*', router(state, origin))
                passed = check(page, origin, state)
                assert not errors, errors
                browser.close()
                print(json.dumps({'passed': passed, 'page_errors': errors, 'external_requests': len(state['outside'])}, ensure_ascii=False))
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__': main()
