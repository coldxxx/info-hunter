'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { Search, Bookmark } from 'lucide-react';
import { topics, stamp } from '@/features/workspace/display';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
import ArticleDetailView from '@/features/articles/article-detail-view';
export default function ArchiveView({
  watchId,
  direction,
  isDeveloper,
  collapse,
  setCollapse,
  region,
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
  total,
  offset,
  setOffset,
  setSelectedRecord,
  loading,
  setMessage,
  setVersion,
  selected,
  setSelected,
  displayText,
  filter,
  action,
  save,
}: Pick<
  WorkspaceState,
  | 'watchId'
  | 'direction'
  | 'isDeveloper'
  | 'collapse'
  | 'setCollapse'
  | 'region'
  | 'topic'
  | 'setTopic'
  | 'kind'
  | 'setKind'
  | 'query'
  | 'setQuery'
  | 'source'
  | 'setSource'
  | 'since'
  | 'setSince'
  | 'showOriginal'
  | 'setShowOriginal'
  | 'translations'
  | 'translationEnabled'
  | 'rows'
  | 'sources'
  | 'total'
  | 'offset'
  | 'setOffset'
  | 'setSelectedRecord'
  | 'loading'
  | 'setMessage'
  | 'setVersion'
  | 'selected'
  | 'setSelected'
  | 'displayText'
  | 'filter'
  | 'action'
  | 'save'
>) {
  return (
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
          {isDeveloper ? direction || '全部技术内容' : region || '全部地区'} /{' '}
          {total} 条线索
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setCollapse(collapse === '0' ? '1' : '0')}
        >
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
                    className={'kind ' + (a.kind === '论坛' ? 'forum' : '')}
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
                  <span className="content-status">{a.content_status}</span>
                )}
                <p className="excerpt">
                  {displayText(a, 'excerpt') || '来源未提供摘要，请查看原文。'}
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
                    onClick={() => save({ ...a, starred: a.starred ? 0 : 1 })}
                  >
                    <Bookmark fill={a.starred ? 'currentColor' : 'none'} />
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
          <ArticleDetailView
            watchId={watchId}
            translations={translations}
            sources={sources}
            setSelectedRecord={setSelectedRecord}
            setMessage={setMessage}
            setVersion={setVersion}
            selected={selected}
            setSelected={setSelected}
            displayText={displayText}
            save={save}
          />
        )}
      </div>
    </>
  );
}
