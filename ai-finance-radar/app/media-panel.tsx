'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { request } from './platform-panel';
type Segment = { start: number; end: number; text: string };
type Content = {
  body: string;
  origin: string;
  status: string;
  segments: Segment[];
  media: { type?: string; url?: string };
  error?: string;
  job?: { status: string; progress?: number; stage?: string; error?: string };
};
function clock(n: number) {
  const ms = Math.max(0, Math.round(n * 1000));
  return `${String(Math.floor(ms / 3600000)).padStart(2, '0')}:${String(Math.floor(ms / 60000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`;
}
export default function MediaPanel({ id, url }: { id: string; url: string }) {
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
  return (
    <section className="media-panel" aria-label="正文与转写">
      <div className="platform-heading">
        <h3>{media ? '音视频文字' : '文章正文'}</h3>
        <span className="source-state">{data?.status || '读取中'}</span>
      </div>
      {(error || data?.error) && (
        <p className="notice error" role="alert">
          {error || data?.error}
        </p>
      )}
      <div className="platform-actions">
        {(!data?.body || (media && data.origin === 'article')) && (
          <Button
            disabled={busy || running}
            onClick={() => void act(media ? 'extract' : 'read-article')}
          >
            {busy ? '处理中…' : media ? '提取文字' : '获取全文'}
          </Button>
        )}
        {running && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void act('transcription-cancel')}
          >
            取消任务
          </Button>
        )}
      </div>
      {media && data?.origin === 'article' && (
        <p className="platform-note">
          现有正文来自节目页面。点击提取文字可继续获取字幕或转写音轨。
        </p>
      )}
      {data?.job && (
        <div className="transcription-progress">
          <p>
            {
              (
                {
                  queued: '排队中',
                  running: '正在处理',
                  completed: '处理完成',
                  cancelled: '已取消',
                  failed: '处理失败',
                } as Record<string, string>
              )[data.job.status]
            }{' '}
            · {data.job.stage || ''}
          </p>
          {running && <progress max={100} value={data.job.progress || 0} />}
          <p>{data.job.error}</p>
        </div>
      )}
      {data?.media.type === 'podcast' && data.media.url && (
        <audio
          ref={player}
          src={data.media.url}
          controls
          preload="none"
          aria-label="播放播客音频"
        >
          <track ref={captionTrack} kind="captions" label="文字稿" />
        </audio>
      )}
      {media && (
        <label className="media-upload">
          或上传已有音频 / 视频（最大 512 MB）
          <input
            type="file"
            accept="audio/*,video/*"
            disabled={busy || running}
            onChange={async (e) => {
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
                const response = await fetch('/api/media-upload?id=' + id, {
                  method: 'POST',
                  body: form,
                });
                const result = (await response.json()) as { error?: string };
                if (!response.ok) throw new Error(result.error);
                await refresh();
              } catch (e) {
                setError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
      )}
      {data?.body && (
        <>
          <p className="platform-note">
            文字来源：
            {(
              {
                article: '网页 / RSS 正文',
                'manual-caption': '发布者字幕',
                'automatic-caption': '平台自动字幕',
                'publisher-transcript': '节目文字稿',
                'local-asr': '本地模型转写',
              } as Record<string, string>
            )[data.origin] || data.origin}
          </p>
          <div className="platform-actions">
            {['txt', 'srt', 'vtt', 'json'].map((f) => (
              <Button
                key={f}
                variant="outline"
                disabled={(f === 'srt' || f === 'vtt') && !data.segments.length}
                onClick={() => save(f)}
              >
                导出 {f.toUpperCase()}
              </Button>
            ))}
          </div>
          <details className="transcript-text" open>
            <summary>
              完整文字 · {data.body.length.toLocaleString()} 字符
            </summary>
            {data.segments.length ? (
              data.segments.map((s, i) => (
                <p key={i}>
                  {data.media.type === 'podcast' && data.media.url ? (
                    <button
                      className="segment-time"
                      onClick={() => {
                        if (player.current) {
                          player.current.currentTime = s.start;
                          void player.current
                            .play()
                            .catch(() =>
                              setError('音频暂时无法播放，请检查原始音频链接'),
                            );
                        }
                      }}
                    >
                      {clock(s.start).split(',')[0]}
                    </button>
                  ) : (
                    <a
                      href={
                        url +
                        (url.includes('?') ? '&' : '?') +
                        't=' +
                        Math.floor(s.start)
                      }
                      target="_blank"
                      rel="noreferrer"
                      className="segment-time"
                    >
                      {clock(s.start).split(',')[0]}
                    </a>
                  )}{' '}
                  {s.text}
                </p>
              ))
            ) : (
              <div style={{ whiteSpace: 'pre-wrap' }}>{data.body}</div>
            )}
          </details>
        </>
      )}
    </section>
  );
}
