'use client';
import type { FeedArticle as Article } from '@/lib/api-types/feed';
import { pageRequest as api } from '@/lib/api';
import { useEffect } from 'react';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export function useArticleDetailLoading({
  selectedRecord,
  setSelectedRecord,
  setError,
  articleId,
}: Pick<
  WorkspaceState,
  'selectedRecord' | 'setSelectedRecord' | 'setError' | 'articleId'
>) {
  useEffect(() => {
    if (!articleId || selectedRecord?.id === articleId) return;
    const controller = new AbortController();
    api<{ items: Article[] }>(
      'articles?' + new URLSearchParams({ id: articleId }),
      undefined,
      {
        signal: controller.signal,
        httpError: () => '资料详情读取失败',
      },
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!data.items[0]) throw new Error('该资料不存在或已过期');
        setSelectedRecord(data.items[0]);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setError(String(error));
      });
    return () => controller.abort();
  }, [articleId, selectedRecord?.id, setSelectedRecord, setError]);
}
