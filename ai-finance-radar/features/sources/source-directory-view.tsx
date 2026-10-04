'use client';
import { ChevronRight, Plus, Search, Trash2, X } from 'lucide-react';
import PlatformPanel from '@/app/platform-panel';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import SourceAddForm from './source-add-form';
import {
  adapterOf,
  adapterLabel,
  host,
  needsAttention,
  stateClass,
  time,
} from './source-utils';
import type { SourceViewProps } from './use-source-manager';

export default function SourceDirectoryView({
  sources,
  allSources,
  watchId,
  watchName,
  isDeveloper,
  loading,
  onAction,
  onMessage,
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
  setSelectedId,
  addOpen,
  setAddOpen,
  adding,
  setAdding,
  pendingAction,
  directory,
  availableSelection,
  filtered,
  pages,
  currentPage,
  filteredCount,
  reset,
  changeFilter,
  addToTopic,
  askDelete,
}: SourceViewProps) {
  return (
    <>
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
        <SourceAddForm
          watchId={watchId}
          watchName={watchName}
          isDeveloper={isDeveloper}
          onAction={onAction}
          onMessage={onMessage}
          adding={adding}
          setAdding={setAdding}
          setAddOpen={setAddOpen}
        />
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
    </>
  );
}
