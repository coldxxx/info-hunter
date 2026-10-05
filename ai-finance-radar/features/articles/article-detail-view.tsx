'use client';
import type { FeedArticle as Article } from '@/lib/api-types/feed';
import MediaPanel from '@/app/media-panel';
import { SemanticArticleActions } from '@/app/semantic-panel';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect } from '@/components/ui/native-select';
import { ArrowUpRight } from 'lucide-react';
import { stamp } from '@/features/workspace/display';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export default function ArticleDetailView({
  watchId,
  translations,
  sources,
  setSelectedRecord,
  setMessage,
  setVersion,
  selected,
  setSelected,
  displayText,
  save,
}: Pick<
  WorkspaceState,
  | 'watchId'
  | 'translations'
  | 'sources'
  | 'setSelectedRecord'
  | 'setMessage'
  | 'setVersion'
  | 'selected'
  | 'setSelected'
  | 'displayText'
  | 'save'
> & { selected: Article }) {
  return (
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
      <MediaPanel key={selected.id} id={selected.id} url={selected.url} />
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
        {sources.find((s) => s.id === selected.source_id)?.config.name ||
          selected.source_name ||
          '手动录入'}
        <br />
        {sources.find((s) => s.id === selected.source_id)?.config.note}
      </div>
      <SemanticArticleActions
        articleId={selected.id}
        duplicateCount={selected.duplicate_count || 1}
        watchId={watchId}
        onChange={() => {
          setSelectedRecord(null);
          setVersion((v) => v + 1);
        }}
      />
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
          onChange={(e) => setSelected({ ...selected, review: e.target.value })}
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
          onChange={(e) => setSelected({ ...selected, note: e.target.value })}
        />
      </label>
      <Button onClick={() => save(selected)}>保存笔记</Button>
    </aside>
  );
}
