'use client';
import type { Translation, FeedArticle as Article } from '@/lib/api-types/feed';
import { pageRequest as api } from '@/lib/api';
import { useEffect } from 'react';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export function useArchiveTool({ watchId }: Pick<WorkspaceState, 'watchId'>) {
  useEffect(() => {
    type Tool = {
      name: string;
      description: string;
      inputSchema: object;
      annotations: object;
      execute: (input: unknown) => Promise<unknown>;
    };
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: Tool,
            options: { signal: AbortSignal },
          ) => unknown;
        };
      }
    ).modelContext;
    if (!context) return;
    const life = new AbortController();
    try {
      Promise.resolve(
        context.registerTool(
          {
            name: 'search_archived_information',
            description:
              'Search the local archived information. Returns unverified external titles, excerpts, sources and dates; does not change notes or collect new data.',
            inputSchema: {
              type: 'object',
              properties: { query: { type: 'string' } },
              required: ['query'],
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            async execute(input) {
              if (
                !input ||
                typeof input !== 'object' ||
                !('query' in input) ||
                typeof input.query !== 'string'
              )
                throw new Error('query must be a string');
              return api(
                'articles?watch_id=' +
                  encodeURIComponent(watchId) +
                  '&q=' +
                  encodeURIComponent(input.query),
              );
            },
          },
          { signal: life.signal },
        ),
      ).catch(() => {});
    } catch {
      /* Optional browser capability. */
    }
    return () => life.abort();
  }, [watchId]);
}

export function useSearchDebounce({
  query,
  search,
  setSearch,
}: Pick<WorkspaceState, 'query' | 'search' | 'setSearch'>) {
  useEffect(() => {
    if (query === search) return;
    const t = setTimeout(() => {
      setSearch(query);
    }, 350);
    return () => clearTimeout(t);
  }, [query, search, setSearch]);
}

export function useFeedResults({
  watchId,
  direction,
  isDeveloper,
  tab,
  collapse,
  region,
  topic,
  kind,
  search,
  source,
  since,
  setRows,
  status,
  setTotal,
  offset,
  setLoading,
  setError,
  version,
}: Pick<
  WorkspaceState,
  | 'watchId'
  | 'direction'
  | 'isDeveloper'
  | 'tab'
  | 'collapse'
  | 'region'
  | 'topic'
  | 'kind'
  | 'search'
  | 'source'
  | 'since'
  | 'setRows'
  | 'status'
  | 'setTotal'
  | 'offset'
  | 'setLoading'
  | 'setError'
  | 'version'
>) {
  useEffect(() => {
    let live = true;
    const params = new URLSearchParams({
      watch_id: watchId,
      q: search,
      region: isDeveloper ? '' : region,
      engineering_category: isDeveloper ? direction : '',
      topic,
      kind,
      source_id: source,
      since,
      offset: String(offset),
      starred: tab === '收藏' ? '1' : '0',
      collapse,
    });
    api<{ items: Article[]; total: number }>('articles?' + params)
      .then((d) => {
        if (live) {
          setRows(d.items);
          setTotal(d.total);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(String(e));
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [
    watchId,
    isDeveloper,
    direction,
    search,
    region,
    topic,
    kind,
    source,
    since,
    offset,
    tab,
    version,
    collapse,
    status.last_run?.finished_at,
    setRows,
    setTotal,
    setLoading,
    setError,
  ]);
}

export function useTranslations({
  tab,
  setTranslations,
  setTranslationEnabled,
  translationIds,
}: Pick<
  WorkspaceState,
  'tab' | 'setTranslations' | 'setTranslationEnabled' | 'translationIds'
>) {
  useEffect(() => {
    if (!translationIds || (tab !== '信息流' && tab !== '收藏')) return;
    let live = true;
    async function refreshTranslation() {
      try {
        const d = await api<{
          enabled: boolean;
          items: Record<string, Translation | null>;
        }>('translations?ids=' + encodeURIComponent(translationIds));
        if (live) {
          setTranslations(d.items);
          setTranslationEnabled(d.enabled);
        }
      } catch {
        /* Translation does not block reading original articles. */
      }
    }
    void api('translate', { ids: translationIds.split(',') })
      .then(refreshTranslation)
      .catch(() => {});
    const timer = setInterval(refreshTranslation, 4000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [translationIds, tab, setTranslations, setTranslationEnabled]);
}
