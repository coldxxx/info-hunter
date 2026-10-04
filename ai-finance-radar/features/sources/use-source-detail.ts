'use client';
import { useEffect, useRef, useState } from 'react';
import { pageRequest } from '@/lib/api';
import type { Source, SourceDetail } from '@/lib/api-types/sources';
import { updateUrlState } from '@/lib/url-state';

type SourceDetailOptions = {
  selectedId: string;
  watchId: string;
  version: number;
  checkedAt: string | null | undefined;
  deleteTarget: Source | null;
};

export function useSourceDetail({
  selectedId,
  watchId,
  version,
  checkedAt,
  deleteTarget,
}: SourceDetailOptions) {
  const [detailRequest, setDetailRequest] = useState<{
    key: string;
    data: SourceDetail | null;
    error: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const requestKey = `${selectedId}/${watchId}/${version}/${retry}/${checkedAt}`;
  const detail = detailRequest?.key === requestKey ? detailRequest.data : null;
  const detailError =
    detailRequest?.key === requestKey ? detailRequest.error : '';
  const detailLoading = !!selectedId && !detail && !detailError;
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    pageRequest<SourceDetail>(
      'source-detail?' +
        new URLSearchParams({ id: selectedId, watch_id: watchId }),
      undefined,
      {
        signal: controller.signal,
        httpError: (status) => `采集详情加载失败 (${status})`,
      },
    )
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
      if (event.key === 'Escape')
        updateUrlState({ source_detail: null }, 'push');
    };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [selectedId, deleteTarget]);

  return { detail, detailError, detailLoading, detailHeading, setRetry };
}
