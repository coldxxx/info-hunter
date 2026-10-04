'use client';
import type { WatchTopic, Translation, FeedArticle as Article, CollectorStatus as Status } from '@/lib/api-types/feed';
import { pageRequest as api } from '@/lib/api';
import { useEffect, useState } from 'react';
import MediaPanel from './media-panel';
import SemanticPanel, { SemanticArticleActions } from './semantic-panel';
import SourceManager, { type Source } from './source-manager';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect } from '@/components/ui/native-select';
import { useUrlState, updateUrlState, viewNames, viewKey } from '@/lib/url-state';
import {
  RadioTower,
  Search,
  RefreshCw,
  Bookmark,
  ArrowUpRight,
  Database,
  Globe2,
  Plus,
  Menu,
  X,
} from 'lucide-react';
const engineeringCategories = [
  '工具更新',
  '工程实践',
  '开源项目',
  '评测与性能',
  '安全与可靠性',
  '模型与研究',
  '手动收录',
];
const regions = ['全球', '中国大陆', '日本', '韩国', '台湾'];
const topics = [
  '算力与芯片',
  '资本开支与基础设施',
  '模型与商业化',
  '业绩与估值',
  '政策与供应链',
];
const stamp = (v: string | null) =>
  v
    ? new Date(v).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '时间未知';
export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [watchId] = useUrlState('watch', 'coding-agent', { history: 'push' });
  const [watchTopics, setWatchTopics] = useState<WatchTopic[]>([]);
  const [allSources, setAllSources] = useState<Source[]>([]);
  const [sourceWatchId, setSourceWatchId] = useState<string | null>(null);
  const [direction, setDirection] = useUrlState('direction', '');
  const [editingId] = useUrlState('edit_topic', '', { history: 'push' });
  const editing = watchTopics.find((topic) => topic.id === editingId) || null;
  const setEditing = (topic: WatchTopic | null) => updateUrlState({ edit_topic: topic?.id || null, draft_profile: null }, 'push');
  const [profileDraft, setProfileDraft] = useUrlState('draft_profile', editing?.content_profile || 'standard', { values: ['standard', 'developer'] });
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
    updateUrlState({ watch: id === 'coding-agent' ? null : id, topic: null, source: null,
      region: null, direction: null, q: null, article: null, offset: null,
      view: tab === '来源管理' ? 'sources' : null }, 'push');
  }
  const [view, setView] = useUrlState('view', 'feed', { values: Object.keys(viewNames), history: 'push' });
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
  const [articleId, setArticleId] = useUrlState('article', '', { history: 'push' });
  const selected = selectedRecord?.id === articleId ? selectedRecord : null;
  function setSelected(article: Article | null) {
    setSelectedRecord(article);
    setArticleId(article?.id || '');
  }
  useEffect(() => {
    if (!articleId || selectedRecord?.id === articleId) return;
    const controller = new AbortController();
    api<{ items: Article[] }>('articles?' + new URLSearchParams({ id: articleId }), undefined, {
      signal: controller.signal,
      httpError: () => '资料详情读取失败',
    })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!data.items[0]) throw new Error('该资料不存在或已过期');
        setSelectedRecord(data.items[0]);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setError(String(error));
      });
    return () => controller.abort();
  }, [articleId, selectedRecord?.id]);
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
  useEffect(() => {
    if (query === search) return;
    const t = setTimeout(() => {
      setSearch(query);
    }, 350);
    return () => clearTimeout(t);
  }, [query, search]);
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
  }, [version, watchId]);
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
  ]);
  const translationIds = Array.from(
    new Set([...(selected ? [selected.id] : []), ...rows.map((a) => a.id)]),
  )
    .slice(0, 50)
    .join(',');
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
  }, [translationIds, tab]);
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
  return (
    <div className="radar-shell">
      <div className="mobile-bar">
        <div className="brand">
          <RadioTower />
          <div>信息雷达</div>
        </div>
        <button
          aria-label={menuOpen ? '关闭导航' : '打开导航'}
          aria-expanded={menuOpen}
          aria-controls="radar-navigation"
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? <X /> : <Menu />}
        </button>
      </div>
      {menuOpen && (
        <button
          className="menu-shade visible"
          aria-label="关闭导航遮罩"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        id="radar-navigation"
        aria-label="工作台导航"
        className={'rail ' + (menuOpen ? 'menu-open' : '')}
      >
        <div className="brand">
          <RadioTower size={28} />
          <div>
            信息雷达<small>SIGNAL RADAR</small>
          </div>
        </div>
        <div className="rail-label">关注主题</div>
        <NativeSelect
          aria-label="关注主题"
          value={watchId}
          onChange={(e) => changeWatch(e.target.value)}
        >
          {watchTopics.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
              {t.enabled ? '' : '（暂停）'}
            </option>
          ))}
          <option value="">全部主题</option>
        </NativeSelect>
        <div className="rail-label">研究工作台</div>
        {['信息流', '收藏', '来源管理', '录入资料', '主题设置', '语义去重'].map((t, i) => (
          <button
            key={t}
            className={'nav-item ' + (tab === t ? 'active' : '')}
            aria-current={tab === t ? 'page' : undefined}
            onClick={() => {
              setMenuOpen(false);
              setSelectedRecord(null);
              updateUrlState({ view: t === '信息流' ? null : viewKey(t),
                offset: null, article: null, source_detail: null,
                ...(!watchId && (t === '来源管理' || t === '录入资料') ? { watch: null } : {}) }, 'push');
              setMessage('');
            }}
          >
            {
              [
                <Globe2 size={18} key="g" />,
                <Bookmark size={18} key="b" />,
                <Database size={18} key="d" />,
                <Plus size={18} key="p" />,
                <Search size={18} key="t" />,
                <RefreshCw size={18} key="s" />,
              ][i]
            }
            {t}
          </button>
        ))}
        {isDeveloper ? (
          <>
            <div className="rail-label">技术方向</div>
            {['', ...engineeringCategories].map((d) => (
              <button
                key={d}
                className={'region-item ' + (direction === d ? 'chosen' : '')}
                onClick={() => {
                  filter(setDirection, d);
                  setTab('信息流');
                  setMenuOpen(false);
                }}
              >
                {d || '全部技术内容'}
              </button>
            ))}
          </>
        ) : (
          <>
            {' '}
            <div className="rail-label">关注地区</div>
            <button
              className={'region-item ' + (!region ? 'chosen' : '')}
              onClick={() => {
                filter(setRegion, '');
                setMenuOpen(false);
              }}
            >
              全部地区<span>ALL</span>
            </button>
            {regions.map((r, i) => (
              <button
                key={r}
                className={'region-item ' + (region === r ? 'chosen' : '')}
                onClick={() => {
                  setMenuOpen(false);
                  filter(setRegion, r);
                  setTab('信息流');
                }}
              >
                {r}
                <span>{['GL', 'CN', 'JP', 'KR', 'TW'][i]}</span>
              </button>
            ))}
          </>
        )}
        <div className="rail-foot">
          <span className="live-dot" /> 本地研究资料库<p>保留来源 · 独立核验</p>
        </div>
      </aside>
      <main
        className={
          'workspace ' + (tab === '来源管理' ? 'sources-workspace' : '')
        }
      >
        <header className="topbar">
          <div className="hero-copy">
            <span className="eyebrow">
              {tab === '来源管理'
                ? '全局来源库'
                : activeWatch?.name || '全部主题'}{' '}
              / SIGNAL RADAR
            </span>
            <h1>{tab === '信息流' ? '捕捉值得关注的信号。' : tab}</h1>
            <p className="hero-description">
              {tab === '信息流'
                ? activeWatch?.description ||
                  '跟踪你的兴趣，把散落的资讯变成值得留下的线索。'
                : tab === '收藏'
                  ? '留下值得再读的内容，让灵感有处可寻。'
                  : tab === '来源管理'
                    ? '所有主题共用信息源与采集适配器，按需关注并查看实现流程。'
                    : tab === '语义去重'
                      ? '比较事实与信息增量，保留每一份原始证据。'
                    : tab === '主题设置'
                      ? '你的好奇心，决定下一条信息流。'
                      : '链接、摘录与思考，一起进入你的资料库。'}
            </p>
          </div>
          <div className="toolbar">
            <Button
              variant="outline"
              className="backup-cta"
              onClick={async () => {
                const r = await action('backup');
                if (r) setMessage('本地快照已保存：' + r.path);
              }}
            >
              <Database />
              备份
            </Button>
            <Button
              disabled={status.busy}
              className="collect-cta"
              onClick={async () => {
                if (await action('collect', { watch_id: watchId })) {
                  setStatus((s) => ({ ...s, busy: true }));
                  setMessage('正在采集，来源状态会自动更新');
                }
              }}
            >
              <RefreshCw className={status.busy ? 'spin' : ''} />
              {status.busy ? '采集中' : '更新信息'}
            </Button>
          </div>
        </header>
        {tab !== '来源管理' && tab !== '语义去重' && (
          <section className="overview">
            <div>
              <strong className="signal-value">
                {status.count.toLocaleString()}
              </strong>
              <span>已归档线索</span>
            </div>
            <div>
              <strong className={good ? 'success-value' : 'muted-value'}>
                {good}
                <small> / {sources.length}</small>
              </strong>
              <span>最近采集成功的来源</span>
            </div>
            <div>
              <strong className={failed ? 'warning-value' : 'muted-value'}>
                {failed}
              </strong>
              <span>采集失败 · 查看来源管理</span>
            </div>
            <div>
              <strong className="time-value">
                {stamp(status.last_run?.finished_at || null)}
              </strong>
              <span>上次采集结束 · 本地时间</span>
            </div>
          </section>
        )}
        {error && (
          <div role="alert" className="notice error">
            {error}
          </div>
        )}
        {message && (
          <output className="notice">
            {message}
            <button aria-label="关闭提示" onClick={() => setMessage('')}>
              ×
            </button>
          </output>
        )}
        {(tab === '信息流' || tab === '收藏') && (
          <>
            <div className="filters">
              <div className="search">
                <Search size={18} />
                <Input
                  aria-label="搜索标题、摘要与笔记"
                  placeholder="搜索原文、中文译文、笔记，例如 Agent、MCP、代码审查…"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setOffset(0);
                  }}
                />
              </div>
              <NativeSelect
                aria-label="来源类型"
                value={kind}
                onChange={(e) => filter(setKind, e.target.value)}
              >
                <option value="">所有类型</option>
                {[
                  '公司发布',
                  '新闻',
                  '研究观点',
                  '研报',
                  '论坛',
                  '视频',
                  '博客/播客',
                  '播客',
                ].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="来源"
                value={source}
                onChange={(e) => filter(setSource, e.target.value)}
              >
                <option value="">所有来源</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.config.name}
                  </option>
                ))}
              </NativeSelect>
              <Input
                aria-label="发布日期起始"
                type="date"
                className="date-filter"
                value={since}
                onChange={(e) => filter(setSince, e.target.value)}
              />
            </div>
            {watchId === 'ai' && (
              <div className="topic-bar">
                <button
                  className={!topic ? 'picked' : ''}
                  onClick={() => filter(setTopic, '')}
                >
                  全部分类
                </button>
                {topics.map((t) => (
                  <button
                    key={t}
                    className={topic === t ? 'picked' : ''}
                    onClick={() => filter(setTopic, t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
            {isDeveloper && (
              <p className="translation-state">
                关注能用于开发的工具、实现方法与工程经验。按标题与摘要筛选，内容仍需独立核验。
              </p>
            )}
            <div className="list-heading">
              <span>
                {isDeveloper
                  ? direction || '全部技术内容'
                  : region || '全部地区'}{' '}
                / {total} 条线索
              </span>
              <Button size="sm" variant="outline" onClick={() => setCollapse(collapse === '0' ? '1' : '0')}>
                {collapse === '0' ? '折叠重复入口' : '展开所有入口'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowOriginal((v) => !v)}
              >
                {showOriginal ? '显示中文译文' : '查看原文'}
                {translationEnabled ? ' · 本地翻译' : ''}
              </Button>
            </div>
            <div className={'reading-grid ' + (selected ? 'has-detail' : '')}>
              <section className="article-list" aria-busy={loading}>
                {loading ? (
                  <div className="empty-state">正在读取本地资料…</div>
                ) : rows.length === 0 ? (
                  <div className="empty-state">
                    暂无符合条件的资料。可调整筛选，或点击“更新信息”。
                  </div>
                ) : (
                  rows.map((a) => (
                    <article
                      key={a.id}
                      className={
                        'article ' + (selected?.id === a.id ? 'selected' : '')
                      }
                    >
                      <div className="article-meta">
                        <span
                          className={
                            'kind ' + (a.kind === '论坛' ? 'forum' : '')
                          }
                        >
                          {a.kind}
                        </span>
                        {isDeveloper ? (
                          <span className="article-category">
                            {a.engineering_category}
                          </span>
                        ) : (
                          <span>{a.region}</span>
                        )}
                        <span>{a.publisher}</span>
                        <time>{stamp(a.published_at)}</time>
                        {(a.duplicate_count || 1) > 1 && (
                          <button
                            onClick={() => {
                              setSelected(a);
                              setMessage('');
                            }}
                          >
                            同文 {a.duplicate_count} 个入口
                          </button>
                        )}
                      </div>
                      <button
                        className="article-title"
                        onClick={() => {
                          setSelected(a);
                          setMessage('');
                        }}
                      >
                        {displayText(a, 'title')}
                      </button>
                      {a.content_status && (
                        <span className="content-status">
                          {a.content_status}
                        </span>
                      )}
                      <p className="excerpt">
                        {displayText(a, 'excerpt') ||
                          '来源未提供摘要，请查看原文。'}
                      </p>
                      {translations[a.id] && (
                        <p
                          className="translation-state"
                          data-state={translations[a.id]?.status}
                        >
                          {translations[a.id]?.status === '完成'
                            ? '机器翻译 · 可切换原文'
                            : translations[a.id]?.status === '失败'
                              ? translations[a.id]?.error || '翻译失败'
                              : '本地翻译排队中…'}
                          {translations[a.id]?.status === '失败' && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                void action('translate', {
                                  ids: [a.id],
                                  retry: true,
                                })
                              }
                            >
                              重试翻译
                            </Button>
                          )}
                        </p>
                      )}
                      <div className="article-bottom">
                        <div>
                          {(watchId === 'ai' ? a.topics : []).map((t) => (
                            <span className="tag" key={t}>
                              {t}
                            </span>
                          ))}
                          <span className="review" data-state={a.review}>
                            {a.review}
                          </span>
                          {a.match_reason && (
                            <small className="translation-state">
                              {a.match_reason}
                            </small>
                          )}
                        </div>
                        <Button
                          aria-label={a.starred ? '取消收藏' : '收藏'}
                          aria-pressed={!!a.starred}
                          className="bookmark-toggle"
                          variant="ghost"
                          size="icon"
                          onClick={() =>
                            save({ ...a, starred: a.starred ? 0 : 1 })
                          }
                        >
                          <Bookmark
                            fill={a.starred ? 'currentColor' : 'none'}
                          />
                        </Button>
                      </div>
                    </article>
                  ))
                )}
                <div className="pagination">
                  <Button
                    variant="outline"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    上一页
                  </Button>
                  <span>
                    {Math.floor(offset / 50) + 1} /{' '}
                    {Math.max(1, Math.ceil(total / 50))}
                  </span>
                  <Button
                    variant="outline"
                    disabled={offset + 50 >= total}
                    onClick={() => setOffset(offset + 50)}
                  >
                    下一页
                  </Button>
                </div>
              </section>
              {selected && (
                <aside className="detail">
                  <div className="detail-top">
                    <span>阅读与核验</span>
                    <Button variant="ghost" onClick={() => setSelected(null)}>
                      关闭
                    </Button>
                  </div>
                  <h2>{displayText(selected, 'title')}</h2>
                  <p className="article-meta">
                    {selected.publisher} · {selected.language}
                  </p>
                  <p>{displayText(selected, 'excerpt') || '暂无摘要'}</p>
                  <MediaPanel
                    key={selected.id}
                    id={selected.id}
                    url={selected.url}
                  />
                  {translations[selected.id]?.status === '完成' && (
                    <details>
                      <summary>原文对照</summary>
                      <h3>{selected.title}</h3>
                      <p>{selected.excerpt}</p>
                    </details>
                  )}
                  <a
                    className="original-link"
                    href={selected.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    打开原文 / 索引链接 <ArrowUpRight size={16} />
                  </a>
                  <div className="provenance">
                    发布：{stamp(selected.published_at)}
                    <br />
                    采集：{stamp(selected.collected_at)}
                    <br />
                    入口：
                    {sources.find((s) => s.id === selected.source_id)?.config
                      .name || selected.source_name || '手动录入'}
                    <br />
                    {
                      sources.find((s) => s.id === selected.source_id)?.config
                        .note
                    }
                  </div>
                  <SemanticArticleActions articleId={selected.id} duplicateCount={selected.duplicate_count || 1} watchId={watchId} onChange={() => { setSelectedRecord(null); setVersion(v => v + 1); }} />
                  {!!selected.duplicates?.length && (
                    <details className="provenance">
                      <summary>同文入口（{selected.duplicate_count}）</summary>
                      <p>
                        当前版本：{selected.publisher}
                        。各入口的收藏、笔记与核验状态独立保留；切换前请保存笔记。
                      </p>
                      {selected.duplicates.map((v) => (
                        <div key={v.id}>
                          <p>{v.title}</p>
                          <p>
                            {v.publisher} · {v.starred ? '已收藏 · ' : ''}
                            {v.note ? '有笔记 · ' : ''}
                            {v.review}
                          </p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              const { duplicates, ...current } = selected;
                              setSelected({
                                ...v,
                                duplicate_count: selected.duplicate_count,
                                duplicates: [
                                  current,
                                  ...(duplicates || []).filter(
                                    (other) => other.id !== v.id,
                                  ),
                                ],
                              });
                              setMessage('');
                            }}
                          >
                            查看此入口
                          </Button>
                        </div>
                      ))}
                    </details>
                  )}
                  <label htmlFor="review-state">
                    核验状态
                    <NativeSelect
                      id="review-state"
                      value={selected.review}
                      onChange={(e) =>
                        setSelected({ ...selected, review: e.target.value })
                      }
                    >
                      {['未核验', '已核验', '存疑'].map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </NativeSelect>
                  </label>
                  <label htmlFor="research-note">
                    研究笔记
                    <Textarea
                      id="research-note"
                      rows={7}
                      placeholder="记录工程价值、使用场景、支持证据与待核实事项…"
                      value={selected.note}
                      onChange={(e) =>
                        setSelected({ ...selected, note: e.target.value })
                      }
                    />
                  </label>
                  <Button onClick={() => save(selected)}>保存笔记</Button>
                </aside>
              )}
            </div>
          </>
        )}
        {tab === '主题设置' && (
          <section className="import-panel">
            <h2>自定义关注主题</h2>
            <p>
              每个主题独立设置关键词、来源和兴趣偏好。暂停主题会停止其自动采集；共享来源仍可能为其他主题更新。
            </p>
            <div className="source-grid">
              {watchTopics.map((t) => (
                <article className="source-card" key={t.id}>
                  <h3>{t.name}</h3>
                  <p>{t.description}</p>
                  <p>
                    {t.article_count} 条资料 · {t.source_count} 个来源 ·{' '}
                    {t.enabled ? '采集中' : '已暂停'}
                  </p>
                  <div className="source-feedback">
                    <Button variant="outline" onClick={() => changeWatch(t.id)}>
                      查看资讯
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setEditing(t);
                      }}
                    >
                      编辑
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() =>
                        void action('watch-topic', {
                          id: t.id,
                          enabled: !t.enabled,
                        })
                      }
                    >
                      {t.enabled ? '暂停主题' : '恢复主题'}
                    </Button>
                  </div>
                </article>
              ))}
            </div>
            <Button
              variant="outline"
              onClick={() => {
                setEditing(null);
              }}
            >
              新建主题
            </Button>
            <form
              key={editing?.id || 'new'}
              className="source-add"
              onSubmit={async (e) => {
                e.preventDefault();
                const f = e.currentTarget;
                const d = new FormData(f);
                const r = await action('watch-topic', {
                  ...(editing ? { id: editing.id } : {}),
                  name: d.get('name'),
                  description: d.get('description'),
                  keywords: d.get('keywords'),
                  exclude: d.get('exclude'),
                  content_profile: profileDraft,
                  regions:
                    profileDraft === 'developer' ? [] : d.getAll('regions'),
                  news_search: d.get('news_search') === 'on',
                  enabled: d.get('enabled') === 'on',
                });
                if (r) {
                  changeWatch(String(r.id));
                  setEditing(null);
                  setTab('来源管理');
                  setMessage(
                    '主题已保存。请从全局来源库选择已有信息源，批量加入此主题。',
                  );
                }
              }}
            >
              <h3>{editing ? '编辑 ' + editing.name : '新建主题'}</h3>
              <label htmlFor="topic-name">
                主题名称
                <Input
                  id="topic-name"
                  name="name"
                  required
                  maxLength={80}
                  defaultValue={editing?.name || ''}
                  placeholder="例如：Coding 与 Agent / 网络安全 / 游戏开发"
                />
              </label>
              <label htmlFor="topic-description">
                关注说明
                <Textarea
                  id="topic-description"
                  name="description"
                  defaultValue={editing?.description || ''}
                />
              </label>
              <label htmlFor="topic-keywords">
                主题关键词（任意一个匹配后，再按内容侧重筛选）
                <Textarea
                  id="topic-keywords"
                  name="keywords"
                  required
                  rows={5}
                  defaultValue={editing?.keywords.join('\n') || ''}
                  placeholder="Agent, MCP, 编程助手, coding"
                />
              </label>
              <label htmlFor="topic-content_profile">
                内容侧重
                <NativeSelect
                  id="topic-content_profile"
                  name="content_profile"
                  value={profileDraft}
                  onChange={(e) =>
                    setProfileDraft(e.target.value as 'standard' | 'developer')
                  }
                >
                  <option value="standard">一般资讯 · 按关键词筛选</option>
                  <option value="developer">
                    开发者内容 · 需要具体技术线索
                  </option>
                </NativeSelect>
              </label>
              {profileDraft === 'developer' && (
                <p>
                  优先收录工具更新、实现方法、代码、评测与排障内容，按技术方向浏览。筛选依据标题与摘要，不代表事实已核验；手动收录会保留。
                </p>
              )}
              <label htmlFor="topic-exclude">
                排除词
                <Textarea
                  id="topic-exclude"
                  name="exclude"
                  defaultValue={editing?.exclude.join('\n') || ''}
                  placeholder="例如：招聘, 课程广告"
                />
              </label>
              {profileDraft !== 'developer' && (
                <>
                  {' '}
                  <p>
                    地区不勾选表示不限地区；公开新闻检索默认使用全球与中国大陆入口。
                  </p>
                  <div className="source-feedback">
                    {regions.map((r) => (
                      <label key={r}>
                        <input
                          type="checkbox"
                          name="regions"
                          value={r}
                          defaultChecked={editing?.regions.includes(r)}
                        />{' '}
                        {r}
                      </label>
                    ))}
                  </div>
                </>
              )}
              <label>
                <input
                  type="checkbox"
                  name="news_search"
                  defaultChecked={editing?.news_search ?? true}
                />{' '}
                自动添加公开新闻检索入口
              </label>
              <label>
                <input
                  type="checkbox"
                  name="enabled"
                  defaultChecked={editing?.enabled ?? true}
                />{' '}
                启用主题采集
              </label>
              <Button type="submit">保存主题</Button>
              <p>
                检索公开新闻索引和已关注来源；视频、播客默认保存标题与摘要，登录或付费内容需要已有授权入口。
              </p>
            </form>
          </section>
        )}
        {tab === '语义去重' && <SemanticPanel watchId={watchId} onChange={() => setVersion(v => v + 1)} />}
        {tab === '来源管理' && (
          <SourceManager
            key={watchId}
            sources={sources}
            allSources={allSources}
            watchId={watchId}
            watchName={activeWatch?.name || '当前主题'}
            isDeveloper={isDeveloper}
            version={version}
            loading={sourceWatchId !== watchId || watchTopics.length === 0}
            onAction={action}
            onMessage={setMessage}
          />
        )}
        {tab === '录入资料' && (
          <section className="import-panel">
            <h2>收录研报与论坛线索</h2>
            <p>
              用于你已有权限查看的资料。保存链接与自己的摘录，不会自动获取付费全文。
            </p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const data = Object.fromEntries(new FormData(form));
                const r = await action('import', {
                  ...data,
                  watch_id: watchId || 'coding-agent',
                });
                if (r) {
                  setMessage(r.added ? '资料已收录' : '该链接已在资料库中');
                  form.reset();
                }
              }}
            >
              <label htmlFor="import-title">
                标题
                <Input
                  id="import-title"
                  name="title"
                  required
                  maxLength={1000}
                />
              </label>
              <label htmlFor="import-url">
                原始链接
                <Input
                  id="import-url"
                  name="url"
                  type="url"
                  required
                  placeholder="https://…"
                />
              </label>
              <div className="form-row">
                <label htmlFor="import-publisher">
                  发布者
                  <Input
                    id="import-publisher"
                    name="publisher"
                    required
                    placeholder="机构 / 媒体 / 作者"
                  />
                </label>
                {isDeveloper ? (
                  <input type="hidden" name="region" value="全球" />
                ) : (
                  <>
                    {' '}
                    <label htmlFor="import-region">
                      地区
                      <NativeSelect id="import-region" name="region">
                        {regions.map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </NativeSelect>
                    </label>
                  </>
                )}
                <label htmlFor="import-kind">
                  类型
                  <NativeSelect id="import-kind" name="kind">
                    {[
                      '研报',
                      '研究观点',
                      '论坛',
                      '视频',
                      '播客',
                      '新闻',
                      '公司发布',
                    ].map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </NativeSelect>
                </label>
              </div>
              <div className="form-row">
                <label htmlFor="import-date">
                  发布日期（可留空）
                  <Input id="import-date" name="published_at" type="date" />
                </label>
                <label htmlFor="import-language">
                  原文语言
                  <Input
                    id="import-language"
                    name="language"
                    placeholder="中文 / English / 日本語 / 한국어"
                  />
                </label>
              </div>
              <label htmlFor="import-excerpt">
                授权摘要或自己的摘录
                <Textarea
                  id="import-excerpt"
                  name="excerpt"
                  rows={8}
                  maxLength={20000}
                />
              </label>
              <Button type="submit">
                <Plus />
                收录到资料库
              </Button>
            </form>
          </section>
        )}
        <footer>
          <strong>SIGNAL RADAR</strong>
          <span>信息雷达 · 原文优先 · 独立核验</span>
        </footer>
      </main>
    </div>
  );
}
