'use client';
import type {
  WatchTopic,
  Translation,
  FeedArticle as Article,
  CollectorStatus as Status,
} from '@/lib/api-types/feed';
import { pageRequest as api } from '@/lib/api';
import { useEffect, useState } from 'react';
import type { Source } from '@/lib/api-types/sources';
import {
  useUrlState,
  updateUrlState,
  viewNames,
  viewKey,
} from '@/lib/url-state';
import { useArticleDetailLoading } from '@/features/articles/use-article-detail';
import {
  useArchiveTool,
  useSearchDebounce,
  useFeedResults,
  useTranslations,
} from '@/features/feed/use-feed';
import { useDashboardPolling } from '@/features/workspace/use-dashboard-polling';
export function useWorkspace() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [watchId] = useUrlState('watch', 'coding-agent', { history: 'push' });
  const [watchTopics, setWatchTopics] = useState<WatchTopic[]>([]);
  const [allSources, setAllSources] = useState<Source[]>([]);
  const [sourceWatchId, setSourceWatchId] = useState<string | null>(null);
  const [direction, setDirection] = useUrlState('direction', '');
  const [editingId] = useUrlState('edit_topic', '', { history: 'push' });
  const editing = watchTopics.find((topic) => topic.id === editingId) || null;
  const setEditing = (topic: WatchTopic | null) =>
    updateUrlState(
      { edit_topic: topic?.id || null, draft_profile: null },
      'push',
    );
  const [profileDraft, setProfileDraft] = useUrlState(
    'draft_profile',
    editing?.content_profile || 'standard',
    { values: ['standard', 'developer'] },
  );
  const activeWatch = watchTopics.find((t) => t.id === watchId);
  const isDeveloper =
    activeWatch?.content_profile === 'developer' ||
    (!activeWatch && watchId === 'coding-agent');
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [menuOpen]);
  function changeWatch(id: string) {
    setMenuOpen(false);
    setSearch('');
    setSelectedRecord(null);
    updateUrlState(
      {
        watch: id === 'coding-agent' ? null : id,
        topic: null,
        source: null,
        region: null,
        direction: null,
        q: null,
        article: null,
        offset: null,
        view: tab === '来源管理' ? 'sources' : null,
      },
      'push',
    );
  }
  const [view, setView] = useUrlState('view', 'feed', {
    values: Object.keys(viewNames),
    history: 'push',
  });
  const tab = viewNames[view];
  const setTab = (name: string) => setView(viewKey(name));
  const [collapse, setCollapse] = useUrlState('collapse', '1');
  const [region, setRegion] = useUrlState('region', ''),
    [topic, setTopic] = useUrlState('topic', ''),
    [kind, setKind] = useUrlState('kind', ''),
    [query, setQuery] = useUrlState('q', ''),
    [search, setSearch] = useState(query),
    [source, setSource] = useUrlState('source', ''),
    [since, setSince] = useUrlState('since', '');
  const [showOriginal, setShowOriginal] = useUrlState('original', false);
  const [translations, setTranslations] = useState<
    Record<string, Translation | null>
  >({});
  const [translationEnabled, setTranslationEnabled] = useState(false);
  const [rows, setRows] = useState<Article[]>([]),
    [sources, setSources] = useState<Source[]>([]),
    [status, setStatus] = useState<Status>({
      count: 0,
      busy: false,
      last_run: null,
    });
  const [total, setTotal] = useState(0),
    [offset, setOffset] = useUrlState('offset', 0),
    [selectedRecord, setSelectedRecord] = useState<Article | null>(null),
    [loading, setLoading] = useState(true),
    [message, setMessage] = useState(''),
    [error, setError] = useState(''),
    [version, setVersion] = useState(0);
  const [articleId, setArticleId] = useUrlState('article', '', {
    history: 'push',
  });
  const selected = selectedRecord?.id === articleId ? selectedRecord : null;
  function setSelected(article: Article | null) {
    setSelectedRecord(article);
    setArticleId(article?.id || '');
  }
  useArticleDetailLoading({
    selectedRecord,
    setSelectedRecord,
    setError,
    articleId,
  });
  useArchiveTool({ watchId });
  useSearchDebounce({ query, search, setSearch });
  useDashboardPolling({
    watchId,
    setWatchTopics,
    setAllSources,
    setSourceWatchId,
    setSources,
    setStatus,
    setError,
    version,
  });
  useFeedResults({
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
  });
  const translationIds = Array.from(
    new Set([...(selected ? [selected.id] : []), ...rows.map((a) => a.id)]),
  )
    .slice(0, 50)
    .join(',');
  useTranslations({
    tab,
    setTranslations,
    setTranslationEnabled,
    translationIds,
  });
  function displayText(a: Article, field: 'title' | 'excerpt') {
    const t = translations[a.id];
    return !showOriginal && t?.status === '完成' ? t[field] : a[field];
  }
  function filter(set: (v: string) => void, v: string) {
    set(v);
    setOffset(0);
  }
  async function action(path: string, body: unknown = {}) {
    setError('');
    try {
      const r = await api(path, body);
      setVersion((v) => v + 1);
      return r;
    } catch (e) {
      setError(String(e));
      return null;
    }
  }
  async function save(a: Article) {
    if (
      await action('article', {
        id: a.id,
        starred: a.starred,
        note: a.note,
        review: a.review,
        watch_id: watchId || 'coding-agent',
      })
    ) {
      setSelected(a);
      setMessage('笔记与核验状态已保存');
    }
  }
  const good = sources.filter((s) => s.status === '成功').length,
    failed = sources.filter((s) => s.status === '失败').length;
  return {
    menuOpen,
    setMenuOpen,
    watchId,
    watchTopics,
    setWatchTopics,
    allSources,
    setAllSources,
    sourceWatchId,
    setSourceWatchId,
    direction,
    setDirection,
    editingId,
    editing,
    setEditing,
    profileDraft,
    setProfileDraft,
    activeWatch,
    isDeveloper,
    changeWatch,
    view,
    setView,
    tab,
    setTab,
    collapse,
    setCollapse,
    region,
    setRegion,
    topic,
    setTopic,
    kind,
    setKind,
    query,
    setQuery,
    search,
    setSearch,
    source,
    setSource,
    since,
    setSince,
    showOriginal,
    setShowOriginal,
    translations,
    setTranslations,
    translationEnabled,
    setTranslationEnabled,
    rows,
    setRows,
    sources,
    setSources,
    status,
    setStatus,
    total,
    setTotal,
    offset,
    setOffset,
    selectedRecord,
    setSelectedRecord,
    loading,
    setLoading,
    message,
    setMessage,
    error,
    setError,
    version,
    setVersion,
    articleId,
    setArticleId,
    selected,
    setSelected,
    translationIds,
    displayText,
    filter,
    action,
    save,
    good,
    failed,
  };
}

export type WorkspaceState = ReturnType<typeof useWorkspace>;
