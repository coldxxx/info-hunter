import type { Source } from '@/lib/api-types/sources';

export const time = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    : '—';
export const adapterOf = (s: Source) => s.effective_adapter || s.config.adapter;
export const adapterLabel = (adapter: string) =>
  ({
    'rss-browser': 'RSS + 会员正文',
    'browser-auto': '隔离浏览器',
    'wechat-rss': '公众号桥接',
    rss: 'RSS / Atom',
    x: 'X API',
    reddit: 'Reddit API',
    browser: '浏览器辅助',
    manual: '手动 / 待接入',
  })[adapter] || '待接入';
export const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};
export const needsAttention = (s: Source) =>
  s.config.enabled && !['成功', '未采集', '样本已入库'].includes(s.status);
export const stateClass = (s: Source) =>
  !s.config.enabled
    ? 'paused'
    : ['成功', '样本已入库'].includes(s.status)
      ? 'ok'
      : s.status === '失败'
        ? 'bad'
        : s.status === '未采集'
          ? 'neutral'
          : 'pending';

export function connectionPlatform(source: Source): string | null {
  if (source.config.adapter === 'wechat-rss') return null;
  try {
    const url = new URL(source.config.url);
    if (
      ['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(
        url.hostname,
      )
    ) {
      return /^\/[A-Za-z0-9_]{1,15}\/?$/.test(url.pathname) &&
        !['home', 'search', 'explore', 'i'].includes(
          url.pathname.replaceAll('/', '').toLowerCase(),
        )
        ? 'x'
        : null;
    }
    if (
      ['reddit.com', 'www.reddit.com', 'old.reddit.com'].includes(url.hostname)
    )
      return /^\/r\/[A-Za-z0-9_]+\/?$/i.test(url.pathname) ? 'reddit' : null;
    if (source.config.connection_id || source.config.kind.includes('博客'))
      return 'blog';
  } catch {
    /* Invalid or unsupported entries have no account controls. */
  }
  return null;
}
