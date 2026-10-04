'use client';

import PlatformPanel from './platform-panel';
import SourceConnection from './source-connection';
import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ChevronRight,
  ExternalLink,
  Plus,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { useUrlState, updateUrlState } from '@/lib/url-state';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export type Source = {
  id: string;
  connection_status?: string;
  body_count?: number;
  next_at?: number;
  status: string;
  checked_at: string | null;
  success_at: string | null;
  error: string;
  last_count: number;
  effective_adapter?: string;
  followed: boolean;
  topics: {
    id: string;
    name: string;
    enabled: boolean;
    include_all: boolean;
  }[];
  include_all: boolean;
  preference: {
    score: number;
    interval_hours: number;
    reason: string;
    signals: Record<string, number>;
  };
  config: {
    user_added?: boolean;
    connection_id?: string;
    platform?: string;
    adapter: string;
    enabled: boolean;
    name: string;
    region: string;
    language?: string;
    kind: string;
    url: string;
    feed_url?: string;
    search_topic?: string;
    note: string;
  };
};
type SourceDetail = {
  next_at?: number;
  source_id: string;
  entry_url: string;
  query: string;
  configured_adapter: string;
  effective_adapter: string;
  access: { mode: string; ready: boolean; message: string };
  capture_strategy: {
    id: string;
    name: string;
    adapter_name: string;
    description: string;
    parameters: { label: string; value: string }[];
  };
  steps: { title: string; detail: string; implementation: string }[];
  topics: {
    id: string;
    name: string;
    enabled: boolean;
    include_all: boolean;
    keywords: string[];
    exclude: string[];
    regions: string[];
    content_profile?: string;
  }[];
  schedule: {
    interval_hours: number;
    enabled: boolean;
    baseline: boolean;
    policy: Source['preference'];
  };
  stats: { archived: number; in_topic: number };
  recent: {
    id: string;
    title: string;
    url: string;
    published_at: string | null;
  }[];
  last_run: {
    status: string;
    found: number;
    added: number;
    finished_at: string | null;
    error: string;
  } | null;
};
type Props = {
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
const time = (value: string | null | undefined) =>
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
const adapterOf = (s: Source) => s.effective_adapter || s.config.adapter;
const adapterLabel = (adapter: string) =>
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
const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};
const needsAttention = (s: Source) =>
  s.config.enabled && !['成功', '未采集', '样本已入库'].includes(s.status);
const stateClass = (s: Source) =>
  !s.config.enabled
    ? 'paused'
    : ['成功', '样本已入库'].includes(s.status)
      ? 'ok'
      : s.status === '失败'
        ? 'bad'
        : s.status === '未采集'
          ? 'neutral'
          : 'pending';

export default function SourceManager({
  sources,
  allSources,
  watchId,
  watchName,
  isDeveloper,
  version,
  loading,
  onAction,
  onMessage,
}: Props) {
  const [query, setQuery] = useUrlState('src_q', '');
  const [state, setState] = useUrlState('src_state', '');
  const [adapter, setAdapter] = useUrlState('src_adapter', '');
  const [kind, setKind] = useUrlState('src_kind', '');
  const [region, setRegion] = useUrlState('src_region', '');
  const [platform, setPlatform] = useUrlState('src_platform', '');
  const [connection, setConnection] = useUrlState('src_connection', '');
  const [completion, setCompletion] = useUrlState('src_completion', '');
  const [sort, setSort] = useUrlState('src_sort', 'name', { values: ['name', 'count', 'recent', 'score'] });
  const [scope, setScope] = useUrlState('src_scope', 'global', { values: ['global', 'topic'] });
  const [membership, setMembership] = useUrlState('src_membership', '');
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const [includeAll, setIncludeAll] = useState(false);
  const [page, setPage] = useUrlState('src_page', 0);
  const [selectedId, setSelectedUrl] = useUrlState('source_detail', '', { history: 'push' });
  const setSelectedId = (value: string | null | ((previous: string) => string | null)) =>
    setSelectedUrl((previous) => (typeof value === 'function' ? value(previous) : value) || '');
  const [detailRequest, setDetailRequest] = useState<{
    key: string;
    data: SourceDetail | null;
    error: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const [addOpen, setAddOpen] = useUrlState('add_source', false);
  const [adding, setAdding] = useState(false);
  const [pendingAction, setPendingAction] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const selected = allSources.find((s) => s.id === selectedId);
  const directory = scope === 'topic' && watchId ? sources : allSources;
  const availableSelection = allSources.filter(
    (s) => checkedIds.includes(s.id) && !s.followed,
  );

  const requestKey = `${selectedId}/${watchId}/${version}/${retry}/${selected?.checked_at}`;
  const detail = detailRequest?.key === requestKey ? detailRequest.data : null;
  const detailError =
    detailRequest?.key === requestKey ? detailRequest.error : '';
  const detailLoading = !!selectedId && !detail && !detailError;
  function changeFilter(set: (value: string) => void, value: string) {
    set(value);
    setPage(0);
  }
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    fetch(
      '/api/source-detail?' +
        new URLSearchParams({ id: selectedId, watch_id: watchId }),
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`采集详情加载失败 (${response.status})`);
        return response.json() as Promise<SourceDetail>;
      })
      .then((data) => {
        if (!controller.signal.aborted)
          setDetailRequest({ key: requestKey, data, error: '' });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setDetailRequest({
            key: requestKey,
            data: null,
            error: String(error),
          });
      });
    return () => controller.abort();
  }, [selectedId, watchId, requestKey]);
  useEffect(() => {
    if (!selectedId) return;
    detailHeading.current?.focus();
  }, [selectedId]);
  useEffect(() => {
    if (!selectedId || deleteTarget) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') updateUrlState({ source_detail: null }, 'push');
    };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [selectedId, deleteTarget]);

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
        setSelectedId((sid) => sid === id ? null : sid);
        setDeleteTarget(null);
        onMessage('来源已删除，历史归档、收藏和笔记已保留');
      } else {
        setDeleteError('删除未完成，请重试。');
      }
    } finally {
      setPendingAction(false);
    }
  }
  const deleteDialog = (
    <AlertDialog
      open={!!deleteTarget}
      onOpenChange={(open) => {
        if (!open && !pendingAction) setDeleteTarget(null);
      }}
    >
      <AlertDialogContent className="source-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>删除来源？</AlertDialogTitle>
          <AlertDialogDescription>
            将从全局来源库删除「{deleteTarget?.config.name}」，停止后续采集并解除所有主题的关注。
          </AlertDialogDescription>
          <AlertDialogDescription>
            {deleteTarget?.topics.length
              ? `涉及主题：${deleteTarget.topics.map((t) => t.name).join('、')}。`
              : '此来源尚未被主题关注。'}
            历史归档、收藏和笔记会保留。重新添加该来源链接可恢复来源。
          </AlertDialogDescription>
        </AlertDialogHeader>
        {deleteError && <p className="source-error" role="alert">{deleteError}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pendingAction}>取消</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={pendingAction}
            onClick={() => void deleteSource()}
          >
            <Trash2 />
            {pendingAction ? '正在删除…' : '确认删除'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  if (selectedId && selected)
    return (
      <section className="source-detail-page" aria-label="信息源详情">
        {deleteDialog}
        <Button
          variant="outline"
          className="source-back"
          onClick={() => setSelectedId(null)}
        >
          <ArrowLeft />
          返回来源列表
        </Button>
        <div className="source-detail-header">
          <div>
            <span className="eyebrow">SOURCE / {selected.id}</span>
            <h2 ref={detailHeading} tabIndex={-1}>
              {selected.config.name}
            </h2>
            <a
              className="source-home-link"
              href={selected.config.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {selected.config.url}
              <ExternalLink size={14} />
            </a>
          </div>
          <div className="source-detail-actions">
            <span className={'source-state ' + stateClass(selected)}>
              {selected.config.enabled ? selected.status : '已暂停'}
            </span>
            <Button
              variant="destructive"
              disabled={pendingAction || loading}
              onClick={() => askDelete(selected)}
            >
              <Trash2 />
              删除来源
            </Button>
          </div>
        </div>
        <SourceConnection
          key={selected.id}
          source={selected}
          onChanged={() => {
            setRetry((v) => v + 1);
            void onAction('refresh-platform', {});
          }}
        />
        {selected.error && (
          <div
            className={
              'notice source-issue ' +
              (selected.status === '失败' ? 'error' : 'warning')
            }
          >
            <span>最近检查记录</span>
            <p>{selected.error}</p>
          </div>
        )}
        {detailLoading && (
          <output className="empty-state">正在读取采集实现与归档记录…</output>
        )}
        {detailError && (
          <div className="notice error" role="alert">
            {detailError}
            <Button variant="outline" onClick={() => setRetry((v) => v + 1)}>
              重试
            </Button>
          </div>
        )}
        {detail && (
          <>
            <div className="source-facts">
              <div>
                <span>实际采集方式</span>
                <strong>{adapterLabel(detail.effective_adapter)}</strong>
              </div>
              <div>
                <span>{watchId ? '来源归档 / 当前主题' : '来源归档'}</span>
                <strong className="mono">
                  {detail.stats.archived}
                  {watchId && ` / ${detail.stats.in_topic}`}
                </strong>
              </div>
              <div>
                <span>调度到期间隔</span>
                <strong>
                  {detail.schedule.enabled
                    ? `${detail.schedule.interval_hours} 小时`
                    : '未参与调度'}
                </strong>
              </div>
              <div>
                <span>最近成功 · 北京时间</span>
                <strong className="mono">{time(selected.success_at)}</strong>
                {!!detail.next_at && (
                  <small>
                    下次巡检最早{' '}
                    {time(new Date(detail.next_at * 1000).toISOString())}
                  </small>
                )}
              </div>
            </div>
            <div className="source-detail-grid">
              <div>
                <section className="shared-capture">
                  <span className="eyebrow">SHARED CAPTURE ADAPTER</span>
                  <h3>
                    {detail.capture_strategy.adapter_name} · 共用采集适配器
                  </h3>
                  <p>{detail.capture_strategy.description}</p>
                  <p>
                    这个来源只配置入口参数，所有关注它的主题共用同一份配置和采集结果。
                  </p>
                  <dl className="capture-parameters">
                    {detail.capture_strategy.parameters.map((parameter) => (
                      <div key={parameter.label}>
                        <dt>{parameter.label}</dt>
                        <dd>{parameter.value || '尚未配置'}</dd>
                      </div>
                    ))}
                  </dl>
                  {selected.config.search_topic && (
                    <p>
                      这是由关键词生成的检索源；加入其他主题后仍读取当前查询，内容再按各主题规则筛选。
                    </p>
                  )}
                </section>
                <section className="pipeline-section">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">COLLECTION PIPELINE</span>
                      <h3>采集实现流程</h3>
                    </div>
                    <span className="subtle">
                      当前配置 · {detail.steps.length} 个环节
                    </span>
                  </div>
                  <p className="pipeline-access">{detail.access.message}</p>
                  <dl className="endpoint-block">
                    <dt>实际读取入口</dt>
                    <dd>
                      <a
                        href={detail.entry_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {detail.entry_url}
                      </a>
                    </dd>
                    {detail.query && (
                      <>
                        <dt>查询条件</dt>
                        <dd>
                          <code>{detail.query}</code>
                        </dd>
                      </>
                    )}
                  </dl>
                  <ol className="pipeline-steps">
                    {detail.steps.map((step, i) => (
                      <li key={step.title}>
                        <span className="step-number">
                          {String(i + 1).padStart(2, '0')}
                        </span>
                        <div>
                          <h4>{step.title}</h4>
                          <p>{step.detail}</p>
                          <code className="implementation-ref">
                            {step.implementation}
                          </code>
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
                <section className="source-recent">
                  <div className="section-heading">
                    <h3>最近归档</h3>
                    <span className="subtle">此来源的最新 8 条 · 所有主题</span>
                  </div>
                  {detail.recent.length ? (
                    <ul>
                      {detail.recent.map((a) => (
                        <li key={a.id}>
                          <a
                            href={a.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {a.title}
                            <ExternalLink size={14} />
                          </a>
                          <time>{time(a.published_at)}</time>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty-inline">此来源还没有归档记录。</p>
                  )}
                </section>
              </div>
              <aside className="source-inspector">
                <section>
                  <span className="eyebrow">LAST CHECK</span>
                  <h3>最近采集结果</h3>
                  <dl className="inspector-facts">
                    <dt>最近检查</dt>
                    <dd>{time(selected.checked_at)}</dd>
                    <dt>筛选后候选</dt>
                    <dd>{selected.last_count} 条（含重复）</dd>
                    <dt>最近自动轮次</dt>
                    <dd>{time(detail.last_run?.finished_at)}</dd>
                    <dt>轮次新增归档</dt>
                    <dd>
                      {detail.last_run
                        ? `${detail.last_run.added} 条 / 候选 ${detail.last_run.found} 条`
                        : '暂无自动轮次记录'}
                    </dd>
                  </dl>
                  {detail.last_run?.error && (
                    <p className="source-error">{detail.last_run.error}</p>
                  )}
                </section>
                <section>
                  <span className="eyebrow">TOPIC RULES</span>
                  <h3>主题与筛选</h3>
                  {detail.topics.length ? (
                    detail.topics.map((t) => (
                      <div
                        className={
                          'binding-rule ' + (t.id === watchId ? 'current' : '')
                        }
                        key={t.id}
                      >
                        <div className="binding-title">
                          {t.name}
                          <span>
                            {t.id === watchId
                              ? '当前主题'
                              : t.enabled
                                ? '已启用'
                                : '已暂停'}
                          </span>
                        </div>
                        <p>
                          {t.include_all ? '全部收录' : '按关键词收录'}
                          {t.content_profile === 'developer'
                            ? ' · 开发者内容筛选'
                            : ''}
                          {!t.enabled ? ' · 主题已暂停' : ''}
                        </p>
                        <dl>
                          <dt>关键词</dt>
                          <dd>{t.keywords.join('、') || '无'}</dd>
                          <dt>排除词</dt>
                          <dd>{t.exclude.join('、') || '无'}</dd>
                          {t.content_profile !== 'developer' && (
                            <>
                              <dt>地区</dt>
                              <dd>{t.regions.join('、') || '不限'}</dd>
                            </>
                          )}
                        </dl>
                      </div>
                    ))
                  ) : (
                    <p className="empty-inline">尚未绑定主题。</p>
                  )}
                </section>
                {watchId && selected.followed && (
                  <section>
                    <span className="eyebrow">PREFERENCE</span>
                    <h3>兴趣与调度</h3>
                    <div className="preference-score">
                      {selected.preference?.score ?? 10}
                      <span>/ 100 · 当前主题</span>
                    </div>
                    <p>{selected.preference?.reason}</p>
                    <p>
                      后台调度使用启用主题中的最高兴趣分：
                      {detail.schedule.policy.score}。
                      {detail.schedule.baseline
                        ? '这个基础来源尚无偏好信号，后台每 6 小时检查一次。'
                        : `后台每 6 小时检查，达到 ${detail.schedule.interval_hours} 小时间隔后再按每轮配额选择。`}
                    </p>
                    <div className="source-feedback">
                      <Button
                        disabled={pendingAction}
                        variant="outline"
                        onClick={() => void feedback('prefer')}
                      >
                        多看
                      </Button>
                      <Button
                        disabled={pendingAction}
                        variant="outline"
                        onClick={() => void feedback('less')}
                      >
                        少看
                      </Button>
                      <Button
                        disabled={pendingAction}
                        variant="outline"
                        onClick={() => void feedback('reset')}
                      >
                        重置偏好
                      </Button>
                    </div>
                  </section>
                )}
                <section>
                  <span className="eyebrow">SOURCE CONTROL</span>
                  <h3>来源设置</h3>
                  <p>
                    {selected.config.note || '公开来源，保留原始链接与摘要。'}
                  </p>
                  <dl className="inspector-facts">
                    <dt>登记适配器</dt>
                    <dd>{detail.configured_adapter}</dd>
                    <dt>地区 / 类型</dt>
                    <dd>
                      {selected.config.region} / {selected.config.kind}
                    </dd>
                  </dl>
                  <Button
                    disabled={pendingAction}
                    variant="outline"
                    onClick={() =>
                      void feedback(
                        selected.config.enabled ? 'pause' : 'resume',
                      )
                    }
                  >
                    {selected.config.enabled
                      ? '暂停所有主题采集'
                      : '恢复来源采集'}
                  </Button>
                  {watchId && selected.followed && (
                    <Button
                      disabled={pendingAction}
                      className="remove-source"
                      variant="ghost"
                      onClick={async () => {
                        setPendingAction(true);
                        try {
                          if (
                            await onAction('watch-source', {
                              watch_id: watchId,
                              source_id: selected.id,
                              follow: false,
                            })
                          ) {
                            if (scope === 'topic') setSelectedId(null);
                            onMessage('来源已移出此主题，历史归档保留');
                          }
                        } finally {
                          setPendingAction(false);
                        }
                      }}
                    >
                      移出此主题
                    </Button>
                  )}
                  {watchId && !selected.followed && (
                    <Button
                      disabled={pendingAction || loading}
                      variant="outline"
                      onClick={() => void addToTopic([selected.id])}
                    >
                      <Plus />
                      加入「{watchName}」
                    </Button>
                  )}
                </section>
              </aside>
            </div>
          </>
        )}
      </section>
    );

  return (
    <section className="source-management" aria-label="来源管理">
      {deleteDialog}
      <PlatformPanel
        watchId={watchId}
        onChanged={() => void onAction('refresh-platform', {})}
      />
      <div className="source-list-toolbar">
        <div>
          <span className="eyebrow">SHARED SOURCE LIBRARY</span>
          <h2>
            全局来源库 <span>{allSources.length}</span>
          </h2>
        </div>
        <Button
          variant="outline"
          aria-expanded={addOpen}
          aria-controls="source-add-panel"
          onClick={() => setAddOpen(!addOpen)}
        >
          {addOpen ? <X /> : <Plus />}
          {addOpen ? '收起表单' : '新增信息源'}
        </Button>
      </div>
      {addOpen && (
        <div id="source-add-panel" className="source-add-panel">
          <form
            className="source-add"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const data = new FormData(form);
              setAdding(true);
              try {
                const result = await onAction('source', {
                  ...Object.fromEntries(data),
                  watch_id: data.get('bind_topic') === 'on' ? watchId : null,
                  include_all: data.get('include_all') === 'on',
                });
                if (result) {
                  onMessage(
                    '来源已保存到全局来源库。' +
                      (result.config as Source['config']).note,
                  );
                  form.reset();
                  setAddOpen(false);
                }
              } finally {
                setAdding(false);
              }
            }}
          >
            <h3>新增到全局来源库</h3>
            <p>
              粘贴作者、板块、频道或订阅链接，自动识别可用入口。已有来源可直接从下方列表选择。
            </p>
            <label htmlFor="new-source-url">
              来源链接
              <Input
                id="new-source-url"
                name="url"
                type="url"
                required
                placeholder="https://…"
              />
            </label>
            <div className="form-row">
              <label htmlFor="new-source-name">
                名称（可留空）
                <Input id="new-source-name" name="name" />
              </label>
              <label htmlFor="new-source-feed">
                RSS / Atom 地址（可留空）
                <Input
                  id="new-source-feed"
                  name="feed_url"
                  type="url"
                  placeholder="https://…/feed"
                />
              </label>
            </div>
            <label>
              <input
                type="checkbox"
                name="bind_topic"
                defaultChecked={!!watchId}
                disabled={!watchId}
              />
              {watchId
                ? `同时加入「${watchName}」`
                : '仅保存到全局来源库，稍后选择主题关注'}
            </label>
            <label>
              <input type="checkbox" name="include_all" defaultChecked />
              {isDeveloper
                ? '不限制关键词，仍应用开发者内容要求与排除词'
                : '全部收录，仍应用地区与排除词'}
            </label>
            <Button type="submit" disabled={adding}>
              {adding ? '正在识别来源…' : '保存信息源'}
            </Button>
          </form>
        </div>
      )}
      <div className="source-library-scope" aria-label="来源库范围">
        <button
          aria-pressed={scope === 'global'}
          className={scope === 'global' ? 'picked' : ''}
          onClick={() => {
            setScope('global');
            reset();
          }}
        >
          全局来源 <span>{allSources.length}</span>
        </button>
        {watchId && (
          <button
            aria-pressed={scope === 'topic'}
            className={scope === 'topic' ? 'picked' : ''}
            onClick={() => {
              setScope('topic');
              reset();
            }}
          >
            当前主题已关注 <span>{sources.length}</span>
          </button>
        )}
        <span>
          {watchId
            ? `添加到「${watchName}」`
            : '选择左侧主题后，可批量关注来源'}
        </span>
      </div>
      <div className="source-quick-filters" aria-label="快速状态筛选">
        {[
          { value: '', label: '全部状态', count: directory.length },
          {
            value: '成功',
            tone: 'success',
            label: '采集成功',
            count: directory.filter(
              (s) => s.config.enabled && s.status === '成功',
            ).length,
          },
          {
            value: 'attention',
            tone: 'warning',
            label: '需要关注',
            count: directory.filter(needsAttention).length,
          },
          {
            value: 'paused',
            label: '已暂停',
            count: directory.filter((s) => !s.config.enabled).length,
          },
        ].map((item) => (
          <button
            key={item.value}
            aria-pressed={state === item.value}
            data-tone={item.count ? item.tone : undefined}
            className={state === item.value ? 'picked' : ''}
            onClick={() => changeFilter(setState, item.value)}
          >
            {item.label}
            <span>{item.count}</span>
          </button>
        ))}
      </div>
      <div className="source-filters">
        <div className="search">
          <Search size={16} />
          <Input
            aria-label="搜索信息源"
            placeholder="名称、网址、已关注主题…"
            value={query}
            onChange={(e) => changeFilter(setQuery, e.target.value)}
          />
        </div>
        <NativeSelect
          aria-label="平台"
          value={platform}
          onChange={(e) => changeFilter(setPlatform, e.target.value)}
        >
          <option value="">全部平台</option>
          {[
            ...new Set(
              directory.map((s) => s.config.platform || host(s.config.url)),
            ),
          ]
            .sort()
            .map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
        </NativeSelect>
        <NativeSelect
          aria-label="连接状态"
          value={connection}
          onChange={(e) => changeFilter(setConnection, e.target.value)}
        >
          <option value="">全部连接状态</option>
          {[
            ...new Set(directory.map((s) => s.connection_status || '无需登录')),
          ].map((p) => (
            <option key={p} value={p}>
              {(
                {
                  ready: '已连接',
                  needs_login: '待登录',
                  login_open: '登录中',
                  challenge: '待验证',
                  cooldown: '冷却中',
                  paused: '暂停',
                } as Record<string, string>
              )[p] || p}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="正文完成度"
          value={completion}
          onChange={(e) => changeFilter(setCompletion, e.target.value)}
        >
          <option value="">全部正文状态</option>
          <option value="body">已有正文或转写</option>
          <option value="metadata">仅有标题摘要</option>
        </NativeSelect>

        {watchId && scope === 'global' && (
          <NativeSelect
            aria-label="当前主题关注筛选"
            value={membership}
            onChange={(e) => changeFilter(setMembership, e.target.value)}
          >
            <option value="">全部关注关系</option>
            <option value="unfollowed">当前主题未关注</option>
            <option value="followed">当前主题已关注</option>
          </NativeSelect>
        )}
        <NativeSelect
          aria-label="采集状态筛选"
          value={state}
          onChange={(e) => changeFilter(setState, e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="enabled">已启用</option>
          <option value="attention">需要关注</option>
          <option value="paused">已暂停</option>
          {[...new Set(directory.map((s) => s.status))].sort().map((s) => (
            <option key={s}>{s}</option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="采集方式筛选"
          value={adapter}
          onChange={(e) => changeFilter(setAdapter, e.target.value)}
        >
          <option value="">全部采集方式</option>
          {[...new Set(directory.map(adapterOf))].sort().map((a) => (
            <option key={a} value={a}>
              {adapterLabel(a)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="来源类型筛选"
          value={kind}
          onChange={(e) => changeFilter(setKind, e.target.value)}
        >
          <option value="">全部类型</option>
          {[...new Set(directory.map((s) => s.config.kind))].sort().map((k) => (
            <option key={k}>{k}</option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="来源地区筛选"
          value={region}
          onChange={(e) => changeFilter(setRegion, e.target.value)}
        >
          <option value="">全部地区</option>
          {[...new Set(directory.map((s) => s.config.region))]
            .sort()
            .map((r) => (
              <option key={r}>{r}</option>
            ))}
        </NativeSelect>
        <NativeSelect
          aria-label="来源排序"
          value={sort}
          onChange={(e) => changeFilter(setSort, e.target.value)}
        >
          <option value="score">
            {watchId ? '当前主题兴趣分优先' : '兴趣分优先'}
          </option>
          <option value="recent">最近成功优先</option>
          <option value="count">候选数优先</option>
          <option value="name">名称排序</option>
        </NativeSelect>
      </div>
      <div className="source-result-info" aria-live="polite">
        <span>
          显示 {filtered.length} / {directory.length} 个来源
          {filteredCount > 0 && ` · ${filteredCount} 项筛选`}
        </span>
        {filteredCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={reset}>
            清除筛选
          </Button>
        ) : (
          <span>
            {watchId ? '点击查看流程 · 勾选可批量关注' : '点击来源查看采集流程'}
          </span>
        )}
      </div>
      {watchId && availableSelection.length > 0 && (
        <div className="source-batch-bar">
          <span>已选 {availableSelection.length} 个未关注来源</span>
          <label>
            <input
              type="checkbox"
              checked={includeAll}
              onChange={(e) => setIncludeAll(e.target.checked)}
            />
            {isDeveloper
              ? '不限制关键词，仍应用开发者要求与排除词'
              : '不限制关键词，仍应用地区与排除词'}
          </label>
          <Button
            variant="outline"
            disabled={
              pendingAction || loading || availableSelection.length === 0
            }
            onClick={() =>
              void addToTopic(
                availableSelection.map((s) => s.id),
                includeAll,
              )
            }
          >
            <Plus />
            {pendingAction ? '正在加入…' : `加入「${watchName}」`}
          </Button>
          {checkedIds.length > 0 && (
            <Button
              variant="ghost"
              disabled={pendingAction}
              onClick={() => setCheckedIds([])}
            >
              清空选择
            </Button>
          )}
        </div>
      )}
      <div className="source-table-wrap">
        <table className="source-table">
          <thead>
            <tr>
              {watchId && (
                <th scope="col" className="source-check-col">
                  <input
                    type="checkbox"
                    aria-label="选择本页未关注来源"
                    disabled={
                      pendingAction ||
                      loading ||
                      !filtered
                        .slice(currentPage * 25, (currentPage + 1) * 25)
                        .some((s) => !s.followed)
                    }
                    checked={
                      filtered
                        .slice(currentPage * 25, (currentPage + 1) * 25)
                        .some((s) => !s.followed) &&
                      filtered
                        .slice(currentPage * 25, (currentPage + 1) * 25)
                        .filter((s) => !s.followed)
                        .every((s) => checkedIds.includes(s.id))
                    }
                    onChange={(e) => {
                      const ids = filtered
                        .slice(currentPage * 25, (currentPage + 1) * 25)
                        .filter((s) => !s.followed)
                        .map((s) => s.id);
                      setCheckedIds(
                        e.target.checked
                          ? [...new Set([...checkedIds, ...ids])]
                          : checkedIds.filter((id) => !ids.includes(id)),
                      );
                    }}
                  />
                </th>
              )}
              <th scope="col" className="source-identity-col">
                信息源
              </th>
              <th scope="col" className="source-state-col">
                采集状态
              </th>
              <th scope="col" className="source-adapter-col">
                共用适配器 / 类型
              </th>
              <th scope="col" className="source-topics-col">
                已关注主题
              </th>
              <th
                scope="col"
                className="source-number"
                title={watchId ? '当前主题下的兴趣分' : '共享调度使用的兴趣分'}
              >
                兴趣分
              </th>
              <th scope="col" className="source-number">
                候选数
              </th>
              <th scope="col" className="source-time-col">
                最近成功
              </th>
              <th scope="col" className="source-detail-col">
                <span className="sr-only">来源操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered
              .slice(currentPage * 25, (currentPage + 1) * 25)
              .map((s) => (
                <tr key={s.id}>
                  {watchId && (
                    <td className="source-check-col">
                      <input
                        type="checkbox"
                        aria-label={`选择 ${s.config.name}`}
                        disabled={s.followed || pendingAction}
                        checked={s.followed || checkedIds.includes(s.id)}
                        onChange={(e) =>
                          setCheckedIds(
                            e.target.checked
                              ? [...checkedIds, s.id]
                              : checkedIds.filter((id) => id !== s.id),
                          )
                        }
                      />
                    </td>
                  )}
                  <td>
                    <button
                      className="source-name"
                      onClick={() => setSelectedId(s.id)}
                      aria-label={`查看 ${s.config.name} 的采集流程`}
                    >
                      {s.config.name}
                    </button>
                    <span className="source-domain">
                      {host(s.config.url)} · {s.config.region}
                    </span>
                  </td>
                  <td>
                    <span className={'source-state ' + stateClass(s)}>
                      {s.config.enabled ? s.status : '已暂停'}
                    </span>
                    {s.error && (
                      <span className="source-row-error" title={s.error}>
                        {s.error}
                      </span>
                    )}
                  </td>
                  <td>
                    <span>{adapterLabel(adapterOf(s))}</span>
                    <small>
                      {' · '}
                      {s.body_count ? `${s.body_count} 条含正文` : '仅标题摘要'}
                      {s.config.connection_id &&
                        ` · ${s.connection_status || '待连接'}`}
                    </small>
                    <span className="source-domain">{s.config.kind}</span>
                  </td>
                  <td>
                    <span
                      className="source-topic-names"
                      title={(s.topics || []).map((t) => t.name).join('、')}
                    >
                      {(s.topics || []).map((t) => t.name).join('、') ||
                        '尚未被主题关注'}
                    </span>
                    {watchId &&
                      (s.followed ? (
                        <span className="source-followed">当前主题已关注</span>
                      ) : (
                        <button
                          className="source-inline-add"
                          disabled={pendingAction}
                          onClick={() => void addToTopic([s.id])}
                        >
                          加入当前主题
                        </button>
                      ))}
                  </td>
                  <td className="source-number mono">
                    {watchId && !s.followed ? '—' : (s.preference?.score ?? 10)}
                  </td>
                  <td className="source-number mono">{s.last_count}</td>
                  <td className="source-time mono">{time(s.success_at)}</td>
                  <td className="source-row-actions">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`展开 ${s.config.name} 详情`}
                      onClick={() => setSelectedId(s.id)}
                    >
                      <ChevronRight />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="source-delete-button"
                      disabled={pendingAction || loading}
                      aria-label={`删除 ${s.config.name}`}
                      title="删除来源"
                      onClick={() => askDelete(s)}
                    >
                      <Trash2 />
                    </Button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {loading ? (
          <output className="empty-state">正在加载来源…</output>
        ) : (
          filtered.length === 0 && (
            <div className="empty-state">
              <p>
                {directory.length
                  ? '没有符合筛选条件的来源。'
                  : scope === 'topic'
                    ? '此主题还没有关注来源，可从全局来源库快速添加。'
                    : '全局来源库还没有信息源。'}
              </p>
              {directory.length ? (
                <Button variant="outline" onClick={reset}>
                  清除筛选
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() =>
                    scope === 'topic' ? setScope('global') : setAddOpen(true)
                  }
                >
                  {scope === 'topic' ? '从全局来源库选择' : '新增第一个来源'}
                </Button>
              )}
            </div>
          )
        )}
      </div>
      <div className="source-table-foot">
        <span>候选数为最近检查筛选后的条目，包含重复链接。</span>
        {pages > 1 && (
          <div className="source-pagination">
            <Button
              variant="outline"
              disabled={currentPage === 0}
              onClick={() => setPage(currentPage - 1)}
            >
              上一页
            </Button>
            <span>
              {currentPage + 1} / {pages}
            </span>
            <Button
              variant="outline"
              disabled={currentPage + 1 >= pages}
              onClick={() => setPage(currentPage + 1)}
            >
              下一页
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
