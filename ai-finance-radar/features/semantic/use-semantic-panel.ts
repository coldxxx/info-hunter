'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  SemanticConfig as Config,
  SemanticPair as Pair,
  SemanticStatus as Status,
} from '@/lib/api-types/semantic';
import { semanticRequest as request } from '@/lib/api';
import { useUrlState } from '@/lib/url-state';
import { relations } from './semantic-display';

export type SemanticPanelProps = { watchId: string; onChange: () => void };
export function useSemanticPanel({ watchId, onChange }: SemanticPanelProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [list, setList] = useState<{ total: number; items: Pair[] }>({
    total: 0,
    items: [],
  });
  const [filter, setFilter] = useUrlState('semantic_status', 'review', {
    values: ['review', 'reviewed', 'all'],
  });
  const [relationFilter, setRelationFilter] = useUrlState(
    'semantic_relation',
    '',
    { values: ['', ...Object.keys(relations)] },
  );
  const [offset, setOffset] = useUrlState('semantic_offset', 0);
  const previousWatch = useRef(watchId);
  useEffect(() => {
    if (previousWatch.current !== watchId) {
      previousWatch.current = watchId;
      setOffset(0);
    }
  }, [watchId, setOffset]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const refresh = useCallback(async () => {
    const q = new URLSearchParams({
      status: filter,
      watch_id: watchId,
      offset: String(offset),
      relation: relationFilter,
    });
    const [s, p] = await Promise.all([
      request<Status>('status'),
      request<{ total: number; items: Pair[] }>('pairs?' + q),
    ]);
    setStatus(s);
    setDraft((current) => current || s.config);
    setList(p);
  }, [filter, watchId, offset, relationFilter]);
  useEffect(() => {
    let live = true;
    const run = () =>
      refresh().catch((e) => {
        if (live) setError(String(e.message));
      });
    void run();
    const timer = setInterval(run, 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [refresh]);
  async function act(path: string, body: unknown, success: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await request<Record<string, unknown>>(path, body);
      await refresh();
      onChange();
      setMessage(success);
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function exportLabels() {
    try {
      const labels = await request<{ cases: unknown[] }>('labels');
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(labels.cases, null, 2)], {
          type: 'application/json',
        }),
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'semantic-reviewed-pairs.json';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  }
  return {
    status,
    draft,
    setDraft,
    list,
    filter,
    setFilter,
    relationFilter,
    setRelationFilter,
    offset,
    setOffset,
    busy,
    error,
    message,
    setMessage,
    act,
    exportLabels,
  };
}
