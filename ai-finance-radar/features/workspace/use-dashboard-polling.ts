'use client';
import type {
  WatchTopic,
  CollectorStatus as Status,
} from '@/lib/api-types/feed';
import { pageRequest as api } from '@/lib/api';
import { useEffect } from 'react';
import { type Source } from '@/app/source-manager';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export function useDashboardPolling({
  watchId,
  setWatchTopics,
  setAllSources,
  setSourceWatchId,
  setSources,
  setStatus,
  setError,
  version,
}: Pick<
  WorkspaceState,
  | 'watchId'
  | 'setWatchTopics'
  | 'setAllSources'
  | 'setSourceWatchId'
  | 'setSources'
  | 'setStatus'
  | 'setError'
  | 'version'
>) {
  useEffect(() => {
    let live = true;
    async function refresh() {
      try {
        const [s, x, w, all] = await Promise.all([
          api<Status>('status?watch_id=' + encodeURIComponent(watchId)),
          api<Source[]>('sources?watch_id=' + encodeURIComponent(watchId)),
          api<WatchTopic[]>('watch-topics'),
          api<Source[]>(
            'sources?all=1&watch_id=' + encodeURIComponent(watchId),
          ),
        ]);
        if (live) {
          setStatus(s);
          setSources(x);
          setWatchTopics(w);
          setAllSources(all);
          setSourceWatchId(watchId);
          setError('');
        }
      } catch (e) {
        if (live) setError(String(e));
      }
    }
    void refresh();
    const t = setInterval(refresh, 5000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [
    version,
    watchId,
    setWatchTopics,
    setAllSources,
    setSourceWatchId,
    setSources,
    setStatus,
    setError,
  ]);
}
