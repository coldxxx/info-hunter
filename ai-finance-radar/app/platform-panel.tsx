'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUrlState, updateUrlState } from '@/lib/url-state';

type Connection = {
  id: string;
  platform: string;
  status: string;
  message: string;
  used_today: number;
  daily_limit: number;
  last_success: number;
  retry_at: number;
};
type Connections = {
  available: boolean;
  error?: string;
  items: Connection[];
  storage?: { bytes: number; free_bytes: number };
  reddit?: { approval_confirmed: boolean };
};
type Podcast = {
  name: string;
  author: string;
  feed_url: string;
  url: string;
  updated_at: string;
  reason: string;
};
export async function request<T = Record<string, unknown>>(
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(
    '/api/' + path,
    body === undefined
      ? {}
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
  );
  const result = (await response.json()) as Record<string, unknown>;
  if (!response.ok)
    throw new Error(
      typeof result.error === 'string' ? result.error : '请求失败',
    );
  return result as T;
}
const labels: Record<string, string> = {
  ready: '已连接',
  needs_login: '待登录',
  login_open: '等待确认登录',
  paused: '已暂停',
  challenge: '待人工验证',
  cooldown: '限流冷却',
  adapter_error: '页面结构待检查',
  network_error: '网络故障',
};
export default function PlatformPanel({
  watchId,
  onChanged,
}: {
  watchId: string;
  onChanged: () => void;
}) {
  const [tab, setTab] = useUrlState('platform_panel', '', { values: ['', 'connections', 'podcasts', 'wechat', 'opml'], history: 'push' });
  const [state, setState] = useState<Connections | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [podcastQuery] = useUrlState('podcast_q', '');
  const [podcastFeed, setPodcastFeed] = useUrlState('podcast_feed', '', { history: 'push' });
  const [podcastRetry, setPodcastRetry] = useState(0);
  const [preview, setPreview] = useState<{
    feed_url: string;
    language: string;
    episodes: {
      title: string;
      url: string;
      published_at: string;
      matched_keywords: string[];
    }[];
  } | null>(null);
  const refresh = useCallback(
    () =>
      request<Connections>('platform-connections')
        .then(setState)
        .catch((e) => setError(String(e))),
    [],
  );
  useEffect(() => {
    if (tab !== 'connections') return;
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [tab, refresh]);
  useEffect(() => {
    if (tab !== 'podcasts' || !podcastQuery) return;
    let live = true;
    async function load() {
      setBusy(true); setError('');
      try {
        const result = await request<{ items: Podcast[] }>('podcasts?q=' + encodeURIComponent(podcastQuery));
        if (!live) return;
        setPodcasts(result.items);
        if (podcastFeed) {
          const result = await request('podcast-preview?' + new URLSearchParams({ url: podcastFeed, q: podcastQuery }));
          if (live) setPreview(result as unknown as NonNullable<typeof preview>);
        } else setPreview(null);
      } catch (error) { if (live) setError(String(error)); }
      finally { if (live) setBusy(false); }
    }
    void load();
    return () => { live = false; };
  }, [tab, podcastQuery, podcastFeed, podcastRetry]);
  async function act(path: string, body: unknown, text: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await request(path, body);
      setMessage(text);
      await refresh();
      onChanged();
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="platform-tools" aria-label="平台接入与发现">
      <div className="platform-tabs">
        {[
          ['connections', '平台连接'],
          ['podcasts', '发现播客'],
          ['wechat', '公众号与文章'],
          ['opml', '导入 OPML'],
        ].map(([id, name]) => (
          <Button
            key={id}
            variant={tab === id ? 'default' : 'outline'}
            onClick={() => {
              setTab(tab === id ? '' : id);
              setError('');
              setMessage('');
            }}
            aria-expanded={tab === id}
          >
            {name}
          </Button>
        ))}
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {message && <output className="notice">{message}</output>}
      {tab === 'connections' && (
        <div className="platform-surface">
          <div className="platform-heading">
            <div>
              <span className="eyebrow">PRIVATE CONNECTIONS</span>
              <h3>独立账号 · 共用采集</h3>
              <p>
                在普通专用窗口手动登录，完成后关闭该平台的所有登录窗口，再回到这里确认。
                登录状态只保存在项目专用配置中。
              </p>
            </div>
            <span className="source-state">
              {state?.available ? '本机执行器在线' : '执行器未连接'}
            </span>
          </div>
          {state?.error && <p className="notice warning">{state.error}</p>}
          <div className="platform-actions">
            {['x', 'reddit'].map((platform) => (
              <Button
                key={platform}
                variant="outline"
                disabled={busy || !state?.available}
                onClick={() =>
                  void act(
                    'platform-connection',
                    { platform, action: 'login' },
                    '已打开普通专用窗口。请登录小号，关闭该平台的登录窗口后确认登录',
                  )
                }
              >
                打开 {platform === 'x' ? 'X' : 'Reddit'} 登录
              </Button>
            ))}
          </div>
          <div className="connection-list">
            {state?.items.map((item) => (
              <div className="connection-row" key={item.id}>
                <div>
                  <strong>{item.id}</strong>
                  <span className="source-state">
                    {labels[item.status] || item.status}
                  </span>
                  <p>{item.message || '会话就绪，后台按预算巡检'}</p>
                  <small>
                    今日巡检 {item.used_today}/{item.daily_limit} · 每源至少 6
                    小时
                    {item.retry_at > 0 &&
                      ` · 恢复时间 ${new Date(item.retry_at * 1000).toLocaleString('zh-CN')}`}
                  </small>
                </div>
                <div className="platform-actions">
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        'platform-connection',
                        { id: item.id, action: 'login' },
                        '请在普通专用窗口完成登录，关闭该平台的登录窗口后确认',
                      )
                    }
                  >
                    打开窗口
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        'platform-connection',
                        {
                          id: item.id,
                          action: item.status === 'ready' ? 'pause' : 'confirm',
                        },
                        item.status === 'ready'
                          ? '已暂停'
                          : '已确认登录，可以采集',
                      )
                    }
                  >
                    {item.status === 'ready' ? '暂停' : '确认登录 / 恢复'}
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <p className="platform-note">
            Reddit 官方 API：
            {state?.reddit?.approval_confirmed ? '已确认审批' : '尚未确认审批'}
            。
            <a
              href="https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki"
              target="_blank"
              rel="noreferrer"
            >
              申请免费访问
            </a>
            ；获批后使用本机配置命令接入，同一来源继续复用。
          </p>
          {state?.storage && (
            <div className="platform-actions">
              <small>
                媒体缓存 {(state.storage.bytes / 1024 ** 3).toFixed(2)} GB · 7
                天保留
              </small>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  void act(
                    'media-cleanup',
                    {},
                    '已清理超过7天的媒体缓存，文字结果保留',
                  )
                }
              >
                清理过期媒体
              </Button>
            </div>
          )}
        </div>
      )}
      {tab === 'podcasts' && (
        <div className="platform-surface">
          <h3>从主题、人物或节目发现播客</h3>
          <p>
            先检查近期单集和 RSS，再加入全局来源库。目录匹配不等于质量评分。
          </p>
          <form
            className="platform-search"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              const query = data.get('q');
              updateUrlState({ podcast_q: typeof query === 'string' ? query.trim() : '', podcast_feed: null });
              setPodcastRetry((value) => value + 1);
            }}
          >
            <Input
              key={podcastQuery}
              name="q"
              defaultValue={podcastQuery}
              aria-label="播客搜索关键词"
              placeholder="例如 AI agents、模型研究、创业访谈"
              required
            />
            <Button type="submit" disabled={busy}>
              {busy ? '搜索中…' : '搜索节目'}
            </Button>
          </form>
          <div className="podcast-results">
            {podcasts.map((p) => (
              <div className="podcast-row" key={p.feed_url}>
                <div>
                  <h4>{p.name}</h4>
                  <p>
                    {p.author} · {p.updated_at?.slice(0, 10)}
                  </p>
                  <small>{p.reason}</small>
                </div>
                <div className="platform-actions">
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => setPodcastFeed(p.feed_url)}
                  >
                    验证并查看单集
                  </Button>
                  <Button
                    disabled={busy || preview?.feed_url !== p.feed_url}
                    onClick={() =>
                      void act(
                        'source',
                        {
                          url: p.feed_url,
                          feed_url: p.feed_url,
                          name: p.name,
                          watch_id: watchId || null,
                          include_all: true,
                        },
                        '节目已加入全局来源库，并关注到当前主题',
                      )
                    }
                  >
                    订阅
                  </Button>
                </div>
                {preview?.feed_url === p.feed_url && (
                  <div className="podcast-preview">
                    <small>RSS 已验证 · 语言 {preview.language}</small>
                    <ol>
                      {preview.episodes.map((ep) => (
                        <li key={ep.url}>
                          <a href={ep.url} target="_blank" rel="noreferrer">
                            {ep.title}
                          </a>
                          {ep.matched_keywords?.length > 0 && (
                            <small>
                              匹配词：{ep.matched_keywords.join('、')}
                            </small>
                          )}
                          <small>{ep.published_at?.slice(0, 10)}</small>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {tab === 'wechat' && (
        <div className="platform-surface">
          <h3>微信公众号</h3>
          <p>
            在本机公众号桥接中扫码登录，添加公众号，并设置每 12
            小时更新、首次一页。然后把生成的 RSS 地址接入这里。
          </p>
          <a
            className="original-link"
            href="http://127.0.0.1:43203"
            target="_blank"
            rel="noreferrer"
          >
            打开本机公众号桥接 ↗
          </a>
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                'wechat-source',
                {
                  ...Object.fromEntries(new FormData(e.currentTarget)),
                  watch_id: watchId || null,
                  include_all:
                    new FormData(e.currentTarget).get('include_all') === 'on',
                },
                '公众号已接入全局来源库',
              );
            }}
          >
            <Input
              name="name"
              placeholder="公众号名称"
              aria-label="公众号名称"
              required
            />
            <Input
              name="url"
              type="url"
              placeholder="分享文章链接（可选）"
              aria-label="公众号分享链接"
            />
            <Input
              name="feed_url"
              type="url"
              placeholder="http://127.0.0.1:43203/… RSS 地址"
              aria-label="公众号RSS地址"
              required
            />
            {watchId && (
              <label className="check-label">
                <input type="checkbox" name="include_all" />
                全部收录到当前主题（默认按关键词筛选）
              </label>
            )}
            <Button type="submit" disabled={busy}>
              连接公众号订阅
            </Button>
          </form>
          <h3>收录一篇文章</h3>
          <p>也可以直接导入公开公众号或博客文章；需要登录时会提示。</p>
          <form
            className="platform-search"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                'import-link',
                {
                  url: new FormData(e.currentTarget).get('url'),
                  watch_id: watchId,
                },
                '文章全文已收录',
              );
            }}
          >
            <Input
              name="url"
              type="url"
              required
              aria-label="文章链接"
              placeholder="粘贴文章分享链接"
            />
            <Button type="submit" disabled={busy}>
              获取正文
            </Button>
          </form>
        </div>
      )}
      {tab === 'opml' && (
        <div className="platform-surface">
          <h3>导入现有订阅</h3>
          <p>支持 OPML 文件，一次最多 100 个来源；已有来源会复用。</p>
          <input
            type="file"
            accept=".opml,.xml"
            aria-label="选择OPML文件"
            disabled={busy}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 90000) {
                setError('OPML 文件不能超过90 KB');
                return;
              }
              await act(
                'opml',
                { text: await file.text(), watch_id: watchId || null },
                '订阅已处理；请检查来源状态，无法识别的入口会保留为待接入',
              );
            }}
          />
        </div>
      )}
    </section>
  );
}
