import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { pageRequest, platformRequest, semanticRequest, uploadRequest } from '../lib/api.ts';
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
function response(status, value, parseError) {
  return { ok: status < 400, status, json: async () => { if (parseError) throw parseError; return value; } };
}
test('GET/POST use the original URL, body distinction and signal', async () => {
  const calls = []; const signal = new AbortController().signal;
  globalThis.fetch = async (...args) => { calls.push(args); return response(200, { ok: true }); };
  assert.deepEqual(await pageRequest('sources?watch_id=ai'), { ok: true });
  await pageRequest('source', null, { signal });
  await semanticRequest('settings', { enabled: false });
  assert.deepEqual(calls[0], ['/api/sources?watch_id=ai', {}]);
  assert.deepEqual(calls[1], ['/api/source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: 'null', signal }]);
  assert.equal(calls[2][0], '/api/semantic/settings');
  assert.equal(calls[2][1].body, '{"enabled":false}');
});
test('page rejects HTTP before parsing and retains ordinary Error display', async () => {
  globalThis.fetch = async () => response(503, null, new SyntaxError('invalid JSON'));
  await assert.rejects(pageRequest('status'), error => String(error) === 'Error: 请求失败 (503)，请检查本地服务。');
  await assert.rejects(pageRequest('source-detail', undefined, { httpError: status => `采集详情加载失败 (${status})` }), /采集详情加载失败 \(503\)/);
  await assert.rejects(pageRequest('articles', undefined, { httpError: () => '资料详情读取失败' }), /资料详情读取失败/);
});
test('platform parses before HTTP checks and only accepts string error messages', async () => {
  globalThis.fetch = async () => response(400, { error: '原有接口错误' });
  await assert.rejects(platformRequest('content'), /原有接口错误/);
  globalThis.fetch = async () => response(400, { error: 42 });
  await assert.rejects(platformRequest('content'), error => error.message === '请求失败');
  globalThis.fetch = async () => response(500, {}, new SyntaxError('invalid JSON'));
  await assert.rejects(platformRequest('content'), SyntaxError);
});
test('platform retains the existing null response failure', async () => {
  globalThis.fetch = async () => response(400, null);
  await assert.rejects(platformRequest('content'), TypeError);
});
test('semantic stringifies the error field and retains its fallback', async () => {
  globalThis.fetch = async () => response(400, { error: 42 });
  await assert.rejects(semanticRequest('status'), error => error.message === '42');
  globalThis.fetch = async () => response(400, null);
  await assert.rejects(semanticRequest('status'), error => error.message === '请求失败，请检查本地服务');
});
test('upload sends FormData without a JSON header and preserves missing error text', async () => {
  const form = new FormData(); form.append('file', new Blob(['content']), 'sample.txt');
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/media-upload?id=sample');
    assert.deepEqual(options, { method: 'POST', body: form });
    return response(400, {});
  };
  await assert.rejects(uploadRequest('media-upload?id=sample', form), error => error.message === '');
});
