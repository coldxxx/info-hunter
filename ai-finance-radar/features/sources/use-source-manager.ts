'use client';
import { useState } from 'react';
import type { Source } from '@/lib/api-types/sources';
import { useUrlState } from '@/lib/url-state';
import { adapterOf, host, needsAttention } from './source-utils';
import { useSourceDetail } from './use-source-detail';

export type SourceManagerProps = {
  sources: Source[];
  allSources: Source[];
  watchId: string;
  watchName: string;
  isDeveloper: boolean;
  version: number;
  loading: boolean;
  onAction: (
    path: string,
    body?: unknown,
  ) => Promise<Record<string, unknown> | null>;
  onMessage: (message: string) => void;
};
export function useSourceManager({
  sources,
  allSources,
  watchId,
  watchName,
  version,
  loading,
  onAction,
  onMessage,
}: SourceManagerProps) {
  const [query, setQuery] = useUrlState('src_q', '');
  const [state, setState] = useUrlState('src_state', '');
  const [adapter, setAdapter] = useUrlState('src_adapter', '');
  const [kind, setKind] = useUrlState('src_kind', '');
  const [region, setRegion] = useUrlState('src_region', '');
  const [platform, setPlatform] = useUrlState('src_platform', '');
  const [connection, setConnection] = useUrlState('src_connection', '');
  const [completion, setCompletion] = useUrlState('src_completion', '');
  const [sort, setSort] = useUrlState('src_sort', 'name', {
    values: ['name', 'count', 'recent', 'score'],
  });
  const [scope, setScope] = useUrlState('src_scope', 'global', {
    values: ['global', 'topic'],
  });
  const [membership, setMembership] = useUrlState('src_membership', '');
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const [includeAll, setIncludeAll] = useState(false);
  const [page, setPage] = useUrlState('src_page', 0);
  const [selectedId, setSelectedUrl] = useUrlState('source_detail', '', {
    history: 'push',
  });
  const setSelectedId = (
    value: string | null | ((previous: string) => string | null),
  ) =>
    setSelectedUrl(
      (previous) =>
        (typeof value === 'function' ? value(previous) : value) || '',
    );
  const [addOpen, setAddOpen] = useUrlState('add_source', false);
  const [adding, setAdding] = useState(false);
  const [pendingAction, setPendingAction] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const selected = allSources.find((s) => s.id === selectedId);
  const directory = scope === 'topic' && watchId ? sources : allSources;
  const availableSelection = allSources.filter(
    (s) => checkedIds.includes(s.id) && !s.followed,
  );

  const { detail, detailError, detailLoading, detailHeading, setRetry } =
    useSourceDetail({
      selectedId,
      watchId,
      version,
      checkedAt: selected?.checked_at,
      deleteTarget,
    });
  function changeFilter(set: (value: string) => void, value: string) {
    set(value);
    setPage(0);
  }

  const filtered = (loading ? [] : directory)
    .filter((s) => {
      const match =
        `${s.config.name} ${s.config.url} ${s.config.note} ${s.id} ${(s.topics || []).map((t) => t.name).join(' ')}`
          .toLowerCase()
          .includes(query.trim().toLowerCase());
      const matchesState =
        !state ||
        (state === 'attention'
          ? needsAttention(s)
          : state === 'paused'
            ? !s.config.enabled
            : state === 'enabled'
              ? s.config.enabled
              : s.config.enabled && s.status === state);
      return (
        match &&
        matchesState &&
        (!watchId ||
          !membership ||
          (membership === 'followed' ? s.followed : !s.followed)) &&
        (!adapter || adapterOf(s) === adapter) &&
        (!kind || s.config.kind === kind) &&
        (!region || s.config.region === region) &&
        (!platform || (s.config.platform || host(s.config.url)) === platform) &&
        (!connection || s.connection_status === connection) &&
        (!completion ||
          (completion === 'body' ? !!s.body_count : !s.body_count))
      );
    })
    .sort((a, b) =>
      sort === 'name'
        ? a.config.name.localeCompare(b.config.name, 'zh-CN')
        : sort === 'count'
          ? b.last_count - a.last_count
          : sort === 'recent'
            ? (b.success_at || '').localeCompare(a.success_at || '')
            : (b.preference?.score ?? 10) - (a.preference?.score ?? 10),
    );
  const pages = Math.max(1, Math.ceil(filtered.length / 25));
  const currentPage = Math.min(page, pages - 1);
  const filteredCount = [
    query.trim(),
    state,
    adapter,
    kind,
    region,
    membership,
    platform,
    connection,
    completion,
  ].filter(Boolean).length;
  const reset = () => {
    setPage(0);
    setQuery('');
    setState('');
    setAdapter('');
    setKind('');
    setRegion('');
    setMembership('');
    setPlatform('');
    setConnection('');
    setCompletion('');
  };
  async function addToTopic(ids: string[], include = false) {
    if (!watchId || pendingAction || loading || ids.length === 0) return;
    setPendingAction(true);
    try {
      const result = await onAction('watch-sources', {
        watch_id: watchId,
        source_ids: ids,
        include_all: include,
      });
      if (result) {
        setCheckedIds([]);
        onMessage(
          `已将 ${String(result.added)} 个全局来源加入「${watchName}」，共用原有采集配置`,
        );
      }
    } finally {
      setPendingAction(false);
    }
  }
  async function feedback(action: string) {
    if (!selected || pendingAction) return;
    setPendingAction(true);
    try {
      if (
        await onAction('source-feedback', {
          watch_id: watchId,
          source_id: selected.id,
          action,
        })
      ) {
        onMessage(
          {
            prefer: '已提高此主题下的来源偏好',
            less: '已降低此主题下的来源偏好',
            pause: '来源已暂停，作用于所有主题',
            resume: '来源已恢复采集',
            reset: '此主题下的偏好已重置',
          }[action] || '已保存',
        );
      }
    } finally {
      setPendingAction(false);
    }
  }

  function askDelete(source: Source) {
    setDeleteError('');
    setDeleteTarget(source);
  }
  async function deleteSource() {
    if (!deleteTarget || pendingAction) return;
    const id = deleteTarget.id;
    setPendingAction(true);
    setDeleteError('');
    try {
      if (await onAction('source-delete', { source_id: id })) {
        setCheckedIds((ids) => ids.filter((sid) => sid !== id));
        setSelectedId((sid) => (sid === id ? null : sid));
        setDeleteTarget(null);
        onMessage('来源已删除，历史归档、收藏和笔记已保留');
      } else {
        setDeleteError('删除未完成，请重试。');
      }
    } finally {
      setPendingAction(false);
    }
  }
  return {
    query,
    setQuery,
    state,
    setState,
    adapter,
    setAdapter,
    kind,
    setKind,
    region,
    setRegion,
    platform,
    setPlatform,
    connection,
    setConnection,
    completion,
    setCompletion,
    sort,
    setSort,
    scope,
    setScope,
    membership,
    setMembership,
    checkedIds,
    setCheckedIds,
    includeAll,
    setIncludeAll,
    setPage,
    selectedId,
    setSelectedId,
    detail,
    detailError,
    detailLoading,
    detailHeading,
    setRetry,
    addOpen,
    setAddOpen,
    adding,
    setAdding,
    pendingAction,
    setPendingAction,
    deleteTarget,
    setDeleteTarget,
    deleteError,
    selected,
    directory,
    availableSelection,
    filtered,
    pages,
    currentPage,
    filteredCount,
    reset,
    changeFilter,
    addToTopic,
    feedback,
    askDelete,
    deleteSource,
  };
}

export type SourceManagerController = ReturnType<typeof useSourceManager>;
export type SourceViewProps = SourceManagerProps & SourceManagerController;
