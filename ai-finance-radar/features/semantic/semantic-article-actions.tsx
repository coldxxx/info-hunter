'use client';
import { useEffect, useState } from 'react';
import type { SemanticPair as Pair } from '@/lib/api-types/semantic';
import { semanticRequest as request } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { relations } from './semantic-display';

export function SemanticArticleActions({
  articleId,
  duplicateCount,
  watchId,
  onChange,
}: {
  articleId: string;
  duplicateCount: number;
  watchId: string;
  onChange: () => void;
}) {
  const [items, setItems] = useState<Pair[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    void request<{ items: Pair[] }>(
      'pairs?' +
        new URLSearchParams({
          status: 'all',
          article_id: articleId,
          watch_id: watchId,
        }),
    )
      .then((r) => {
        if (live) setItems(r.items);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [articleId, watchId]);
  return (
    <div className="semantic-article-actions">
      {duplicateCount > 1 && (
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            try {
              await request('split', { article_id: articleId });
              onChange();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          将此入口拆为独立文章
        </Button>
      )}
      {!!items.length && (
        <details>
          <summary>相关资料与语义判断（{items.length}）</summary>
          {items.map((p) => {
            const other = p.left.id === articleId ? p.right : p.left;
            return (
              <div key={p.id}>
                <span>{relations[p.reviewed_relation || p.relation]}</span> ·{' '}
                <a href={other.url} target="_blank" rel="noreferrer">
                  {other.title}
                </a>
                <p>{p.decision.reason}</p>
              </div>
            );
          })}
        </details>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
