'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { platformRequest as request } from '@/lib/api';
import type { Source } from '@/lib/api-types/sources';
import type { PlatformConnections } from '@/lib/api-types/platform';
import { connectionPlatform } from './source-utils';
export { connectionPlatform } from './source-utils';

const labels: Record<string, string> = {
  ready: '已连接',
  needs_login: '待登录',
  login_open: '等待确认登录',
  paused: '已暂停',
  challenge: '待人工验证',
  cooldown: '限流冷却',
  adapter_error: '页面结构待检查',
  network_error: '网络故障',
};

export default function SourceConnection({
  source,
  onChanged,
}: {
  source: Source;
  onChanged: () => void;
}) {
  const platform = connectionPlatform(source);
  const [data, setData] = useState<PlatformConnections | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const refresh = useCallback(
    () =>
      request<PlatformConnections>('platform-connections')
        .then(setData)
        .catch((error: unknown) => setError(String(error))),
    [],
  );
  useEffect(() => {
    if (!platform) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [platform, refresh]);
  if (!platform) return null;
  const items = (data?.items || []).filter((item) =>
    source.config.connection_id
      ? item.id === source.config.connection_id
      : platform !== 'blog' && item.platform === platform,
  );
  async function act(path: string, body: unknown, message: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await request(path, body);
      setMessage(message);
      onChanged();
      await refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="platform-tools source-connection"
      aria-label="此来源的账号连接"
    >
      <div className="platform-surface">
        <div className="platform-heading">
          <div>
            <span className="eyebrow">SOURCE CONNECTION</span>
            <h3>
              {platform === 'blog'
                ? '此站点的会员正文连接'
                : `此来源的 ${platform === 'x' ? 'X' : 'Reddit'} 连接`}
            </h3>
            <p>
              {platform === 'blog'
                ? '公开 RSS 正常采集。需要会员全文时，可绑定此站点的专用登录。'
                : '此来源使用该平台的专用账号。采集频率和访问预算由同一账号共享。'}
            </p>
          </div>
          <span className="source-state">
            {data?.available ? '本机执行器在线' : '执行器未连接'}
          </span>
        </div>
        {(error || data?.error) && (
          <p className="notice error" role="alert">
            {error || data?.error}
          </p>
        )}
        {message && <output className="notice">{message}</output>}
        <div className="platform-actions">
          {!source.config.connection_id && (
            <Button
              disabled={busy || !data?.available}
              onClick={() =>
                void act(
                  'source-connection',
                  { source_id: source.id },
                  '已绑定此来源的专用连接，请完成登录并确认。',
                )
              }
            >
              {platform === 'blog'
                ? '绑定会员正文连接'
                : '为此来源启用隔离采集'}
            </Button>
          )}
          {source.config.connection_id && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                void act(
                  'source-connection',
                  { source_id: source.id, disconnect: true },
                  '已解除此来源的连接绑定。',
                )
              }
            >
              解除此来源绑定
            </Button>
          )}
        </div>
        <div className="connection-list">
          {items.map((item) => (
            <div className="connection-row" key={item.id}>
              <div>
                <strong>{item.id}</strong>
                <span className="source-state">
                  {labels[item.status] || item.status}
                </span>
                <p>{item.message || '会话就绪，后台按预算巡检'}</p>
                <small>
                  今日巡检 {item.used_today}/{item.daily_limit} · 每源至少 6
                  小时
                </small>
              </div>
              <div className="platform-actions">
                <Button
                  variant="outline"
                  disabled={busy || !data?.available}
                  onClick={() =>
                    void act(
                      'platform-connection',
                      { id: item.id, action: 'login' },
                      '请在专用窗口完成登录，关闭窗口后回来确认。',
                    )
                  }
                >
                  打开登录窗口
                </Button>
                <Button
                  variant="outline"
                  disabled={busy || !data?.available}
                  onClick={() =>
                    void act(
                      'platform-connection',
                      {
                        id: item.id,
                        action: item.status === 'ready' ? 'pause' : 'confirm',
                      },
                      item.status === 'ready'
                        ? '该账号连接已暂停。'
                        : '已确认登录状态。',
                    )
                  }
                >
                  {item.status === 'ready' ? '暂停账号连接' : '确认登录 / 恢复'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
