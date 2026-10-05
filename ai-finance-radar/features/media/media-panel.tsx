'use client';
import { Button } from '@/components/ui/button';
import { useMediaPanel, type MediaPanelProps } from './use-media-panel';
import { clock } from './media-time';

export default function MediaPanel({ id, url }: MediaPanelProps) {
  const {
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
  } = useMediaPanel({ id, url });
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
            onChange={upload}
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
                      onClick={() => seek(s.start)}
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
