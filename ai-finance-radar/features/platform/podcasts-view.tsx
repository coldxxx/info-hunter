'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type {
  PlatformPanelController,
  PlatformPanelProps,
} from './use-platform-panel';

type PodcastsViewProps = Pick<PlatformPanelProps, 'watchId'> &
  Pick<
    PlatformPanelController,
    | 'podcastQuery'
    | 'setPodcastFeed'
    | 'podcasts'
    | 'preview'
    | 'busy'
    | 'act'
    | 'searchPodcasts'
  >;

export default function PodcastsView({
  watchId,
  podcastQuery,
  setPodcastFeed,
  podcasts,
  preview,
  busy,
  act,
  searchPodcasts,
}: PodcastsViewProps) {
  return (
    <div className="platform-surface">
      <h3>从主题、人物或节目发现播客</h3>
      <p>先检查近期单集和 RSS，再加入全局来源库。目录匹配不等于质量评分。</p>
      <form className="platform-search" onSubmit={searchPodcasts}>
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
                        <small>匹配词：{ep.matched_keywords.join('、')}</small>
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
  );
}
