'use client';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from 'react';
import type { ArticleContent as Content } from '@/lib/api-types/media';
import { platformRequest as request, uploadRequest } from '@/lib/api';
import { clock } from './media-time';

export type MediaPanelProps = { id: string; url: string };
export function useMediaPanel({ id, url }: MediaPanelProps) {
  const [data, setData] = useState<Content | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const captionTrack = useRef<HTMLTrackElement>(null);
  const player = useRef<HTMLAudioElement>(null);
  const refresh = useCallback(
    () =>
      request<Content>('content?id=' + id)
        .then((value) => {
          setData(value);
          setError('');
        })
        .catch((e) => setError(String(e))),
    [id],
  );
  const running =
    !!data?.job && ['queued', 'running'].includes(data.job.status);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh, running]);
  useEffect(() => {
    if (!data?.segments.length) return;
    const text =
      'WEBVTT\n\n' +
      data.segments
        .map(
          (s) =>
            `${clock(s.start).replace(',', '.')} --> ${clock(s.end).replace(',', '.')}\n${s.text}`,
        )
        .join('\n\n');
    const src = URL.createObjectURL(new Blob([text], { type: 'text/vtt' }));
    if (captionTrack.current) captionTrack.current.src = src;
    return () => URL.revokeObjectURL(src);
  }, [data?.segments]);
  const media = !!data?.media?.type || /youtu(?:be\.com|\.be)/.test(url);
  async function act(path: string) {
    setBusy(true);
    setError('');
    try {
      await request(path, { id });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  function save(format: string) {
    if (!data) return;
    let text = data.body;
    const parts = data.segments;
    if (format === 'json') text = JSON.stringify(data, null, 2);
    if (format === 'srt' || format === 'vtt')
      text =
        (format === 'vtt' ? 'WEBVTT\n\n' : '') +
        parts
          .map(
            (s, i) =>
              `${format === 'srt' ? i + 1 + '\n' : ''}${format === 'vtt' ? clock(s.start).replace(',', '.') : clock(s.start)} --> ${format === 'vtt' ? clock(s.end).replace(',', '.') : clock(s.end)}\n${s.text}`,
          )
          .join('\n\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${id}.${format}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 512 * 1024 * 1024) {
      setError('文件超过512 MB');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      await uploadRequest('media-upload?id=' + id, form);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  function seek(start: number) {
    if (player.current) {
      player.current.currentTime = start;
      void player.current
        .play()
        .catch(() => setError('音频暂时无法播放，请检查原始音频链接'));
    }
  }
  return {
    data,
    error,
    busy,
    captionTrack,
    player,
    running,
    media,
    act,
    save,
    upload,
    seek,
  };
}
