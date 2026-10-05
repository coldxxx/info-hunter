'use client';
import { Button } from '@/components/ui/button';
import type { PlatformPanelController } from './use-platform-panel';

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
type ConnectionsViewProps = Pick<
  PlatformPanelController,
  'state' | 'busy' | 'act'
>;
export default function ConnectionsView({
  state,
  busy,
  act,
}: ConnectionsViewProps) {
  return (
    <div className="platform-surface">
      <div className="platform-heading">
        <div>
          <span className="eyebrow">PRIVATE CONNECTIONS</span>
          <h3>独立账号 · 共用采集</h3>
          <p>
            在普通专用窗口手动登录，完成后关闭该平台的所有登录窗口，再回到这里确认。
            登录状态只保存在项目专用配置中。
          </p>
        </div>
        <span className="source-state">
          {state?.available ? '本机执行器在线' : '执行器未连接'}
        </span>
      </div>
      {state?.error && <p className="notice warning">{state.error}</p>}
      <div className="platform-actions">
        {['x', 'reddit'].map((platform) => (
          <Button
            key={platform}
            variant="outline"
            disabled={busy || !state?.available}
            onClick={() =>
              void act(
                'platform-connection',
                { platform, action: 'login' },
                '已打开普通专用窗口。请登录小号，关闭该平台的登录窗口后确认登录',
              )
            }
          >
            打开 {platform === 'x' ? 'X' : 'Reddit'} 登录
          </Button>
        ))}
      </div>
      <div className="connection-list">
        {state?.items.map((item) => (
          <div className="connection-row" key={item.id}>
            <div>
              <strong>{item.id}</strong>
              <span className="source-state">
                {labels[item.status] || item.status}
              </span>
              <p>{item.message || '会话就绪，后台按预算巡检'}</p>
              <small>
                今日巡检 {item.used_today}/{item.daily_limit} · 每源至少 6 小时
                {item.retry_at > 0 &&
                  ` · 恢复时间 ${new Date(item.retry_at * 1000).toLocaleString('zh-CN')}`}
              </small>
            </div>
            <div className="platform-actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  void act(
                    'platform-connection',
                    { id: item.id, action: 'login' },
                    '请在普通专用窗口完成登录，关闭该平台的登录窗口后确认',
                  )
                }
              >
                打开窗口
              </Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  void act(
                    'platform-connection',
                    {
                      id: item.id,
                      action: item.status === 'ready' ? 'pause' : 'confirm',
                    },
                    item.status === 'ready' ? '已暂停' : '已确认登录，可以采集',
                  )
                }
              >
                {item.status === 'ready' ? '暂停' : '确认登录 / 恢复'}
              </Button>
            </div>
          </div>
        ))}
      </div>
      <p className="platform-note">
        Reddit 官方 API：
        {state?.reddit?.approval_confirmed ? '已确认审批' : '尚未确认审批'}。
        <a
          href="https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki"
          target="_blank"
          rel="noreferrer"
        >
          申请免费访问
        </a>
        ；获批后使用本机配置命令接入，同一来源继续复用。
      </p>
      {state?.storage && (
        <div className="platform-actions">
          <small>
            媒体缓存 {(state.storage.bytes / 1024 ** 3).toFixed(2)} GB · 7
            天保留
          </small>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              void act(
                'media-cleanup',
                {},
                '已清理超过7天的媒体缓存，文字结果保留',
              )
            }
          >
            清理过期媒体
          </Button>
        </div>
      )}
    </div>
  );
}
