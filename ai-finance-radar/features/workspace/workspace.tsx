'use client';
import SemanticPanel from '@/app/semantic-panel';
import SourceManager from '@/app/source-manager';
import { Button } from '@/components/ui/button';
import { NativeSelect } from '@/components/ui/native-select';
import { updateUrlState, viewKey } from '@/lib/url-state';
import {
  RadioTower,
  Search,
  RefreshCw,
  Bookmark,
  Database,
  Globe2,
  Plus,
  Menu,
  X,
} from 'lucide-react';
import {
  engineeringCategories,
  regions,
  stamp,
} from '@/features/workspace/display';
import TopicsView from '@/features/topics/topics-view';
import ImportView from '@/features/articles/import-view';
import ArchiveView from '@/features/feed/archive-view';
import { useWorkspace } from './use-workspace';
export default function Workspace() {
  const {
    menuOpen,
    setMenuOpen,
    watchId,
    watchTopics,
    allSources,
    sourceWatchId,
    direction,
    setDirection,
    editing,
    setEditing,
    profileDraft,
    setProfileDraft,
    activeWatch,
    isDeveloper,
    changeWatch,
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
    source,
    setSource,
    since,
    setSince,
    showOriginal,
    setShowOriginal,
    translations,
    translationEnabled,
    rows,
    sources,
    status,
    setStatus,
    total,
    offset,
    setOffset,
    setSelectedRecord,
    loading,
    message,
    setMessage,
    error,
    version,
    setVersion,
    selected,
    setSelected,
    displayText,
    filter,
    action,
    save,
    good,
    failed,
  } = useWorkspace();
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
        {['信息流', '收藏', '来源管理', '录入资料', '主题设置', '语义去重'].map(
          (t, i) => (
            <button
              key={t}
              className={'nav-item ' + (tab === t ? 'active' : '')}
              aria-current={tab === t ? 'page' : undefined}
              onClick={() => {
                setMenuOpen(false);
                setSelectedRecord(null);
                updateUrlState(
                  {
                    view: t === '信息流' ? null : viewKey(t),
                    offset: null,
                    article: null,
                    source_detail: null,
                    ...(!watchId && (t === '来源管理' || t === '录入资料')
                      ? { watch: null }
                      : {}),
                  },
                  'push',
                );
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
          ),
        )}
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
          <ArchiveView
            watchId={watchId}
            direction={direction}
            isDeveloper={isDeveloper}
            collapse={collapse}
            setCollapse={setCollapse}
            region={region}
            topic={topic}
            setTopic={setTopic}
            kind={kind}
            setKind={setKind}
            query={query}
            setQuery={setQuery}
            source={source}
            setSource={setSource}
            since={since}
            setSince={setSince}
            showOriginal={showOriginal}
            setShowOriginal={setShowOriginal}
            translations={translations}
            translationEnabled={translationEnabled}
            rows={rows}
            sources={sources}
            total={total}
            offset={offset}
            setOffset={setOffset}
            setSelectedRecord={setSelectedRecord}
            loading={loading}
            setMessage={setMessage}
            setVersion={setVersion}
            selected={selected}
            setSelected={setSelected}
            displayText={displayText}
            filter={filter}
            action={action}
            save={save}
          />
        )}
        {tab === '主题设置' && (
          <TopicsView
            watchTopics={watchTopics}
            editing={editing}
            setEditing={setEditing}
            profileDraft={profileDraft}
            setProfileDraft={setProfileDraft}
            changeWatch={changeWatch}
            setTab={setTab}
            setMessage={setMessage}
            action={action}
          />
        )}
        {tab === '语义去重' && (
          <SemanticPanel
            watchId={watchId}
            onChange={() => setVersion((v) => v + 1)}
          />
        )}
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
          <ImportView
            watchId={watchId}
            isDeveloper={isDeveloper}
            setMessage={setMessage}
            action={action}
          />
        )}
        <footer>
          <strong>SIGNAL RADAR</strong>
          <span>信息雷达 · 原文优先 · 独立核验</span>
        </footer>
      </main>
    </div>
  );
}
