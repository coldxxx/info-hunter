'use client';
import { useCallback, useEffect, useState, type SubmitEvent } from 'react';
import type {
  PlatformConnections as Connections,
  Podcast,
} from '@/lib/api-types/platform';
import { platformRequest as request } from '@/lib/api';
import { useUrlState, updateUrlState } from '@/lib/url-state';

export type PlatformPanelProps = { watchId: string; onChanged: () => void };

export function usePlatformPanel({ onChanged }: PlatformPanelProps) {
  const [tab, setTab] = useUrlState('platform_panel', '', {
    values: ['', 'connections', 'podcasts', 'wechat', 'opml'],
    history: 'push',
  });
  const [state, setState] = useState<Connections | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [podcastQuery] = useUrlState('podcast_q', '');
  const [podcastFeed, setPodcastFeed] = useUrlState('podcast_feed', '', {
    history: 'push',
  });
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
      setBusy(true);
      setError('');
      try {
        const result = await request<{ items: Podcast[] }>(
          'podcasts?q=' + encodeURIComponent(podcastQuery),
        );
        if (!live) return;
        setPodcasts(result.items);
        if (podcastFeed) {
          const result = await request(
            'podcast-preview?' +
              new URLSearchParams({ url: podcastFeed, q: podcastQuery }),
          );
          if (live)
            setPreview(result as unknown as NonNullable<typeof preview>);
        } else setPreview(null);
      } catch (error) {
        if (live) setError(String(error));
      } finally {
        if (live) setBusy(false);
      }
    }
    void load();
    return () => {
      live = false;
    };
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
  function searchPodcasts(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const query = data.get('q');
    updateUrlState({
      podcast_q: typeof query === 'string' ? query.trim() : '',
      podcast_feed: null,
    });
    setPodcastRetry((value) => value + 1);
  }
  return {
    tab,
    setTab,
    state,
    error,
    setError,
    message,
    setMessage,
    busy,
    podcasts,
    podcastQuery,
    setPodcastFeed,
    preview,
    act,
    searchPodcasts,
  };
}

export type PlatformPanelController = ReturnType<typeof usePlatformPanel>;
