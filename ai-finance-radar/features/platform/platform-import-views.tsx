'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type {
  PlatformPanelController,
  PlatformPanelProps,
} from './use-platform-panel';

type WechatViewProps = Pick<PlatformPanelProps, 'watchId'> &
  Pick<PlatformPanelController, 'busy' | 'act'>;
export function WechatView({ watchId, busy, act }: WechatViewProps) {
  return (
    <div className="platform-surface">
      <h3>微信公众号</h3>
      <p>
        在本机公众号桥接中扫码登录，添加公众号，并设置每 12
        小时更新、首次一页。然后把生成的 RSS 地址接入这里。
      </p>
      <a
        className="original-link"
        href="http://127.0.0.1:43203"
        target="_blank"
        rel="noreferrer"
      >
        打开本机公众号桥接 ↗
      </a>
      <form
        className="platform-form"
        onSubmit={(e) => {
          e.preventDefault();
          void act(
            'wechat-source',
            {
              ...Object.fromEntries(new FormData(e.currentTarget)),
              watch_id: watchId || null,
              include_all:
                new FormData(e.currentTarget).get('include_all') === 'on',
            },
            '公众号已接入全局来源库',
          );
        }}
      >
        <Input
          name="name"
          placeholder="公众号名称"
          aria-label="公众号名称"
          required
        />
        <Input
          name="url"
          type="url"
          placeholder="分享文章链接（可选）"
          aria-label="公众号分享链接"
        />
        <Input
          name="feed_url"
          type="url"
          placeholder="http://127.0.0.1:43203/… RSS 地址"
          aria-label="公众号RSS地址"
          required
        />
        {watchId && (
          <label className="check-label">
            <input type="checkbox" name="include_all" />
            全部收录到当前主题（默认按关键词筛选）
          </label>
        )}
        <Button type="submit" disabled={busy}>
          连接公众号订阅
        </Button>
      </form>
      <h3>收录一篇文章</h3>
      <p>也可以直接导入公开公众号或博客文章；需要登录时会提示。</p>
      <form
        className="platform-search"
        onSubmit={(e) => {
          e.preventDefault();
          void act(
            'import-link',
            {
              url: new FormData(e.currentTarget).get('url'),
              watch_id: watchId,
            },
            '文章全文已收录',
          );
        }}
      >
        <Input
          name="url"
          type="url"
          required
          aria-label="文章链接"
          placeholder="粘贴文章分享链接"
        />
        <Button type="submit" disabled={busy}>
          获取正文
        </Button>
      </form>
    </div>
  );
}

type OpmlViewProps = Pick<PlatformPanelProps, 'watchId'> &
  Pick<PlatformPanelController, 'busy' | 'act' | 'setError'>;
export function OpmlView({ watchId, busy, act, setError }: OpmlViewProps) {
  return (
    <div className="platform-surface">
      <h3>导入现有订阅</h3>
      <p>支持 OPML 文件，一次最多 100 个来源；已有来源会复用。</p>
      <input
        type="file"
        accept=".opml,.xml"
        aria-label="选择OPML文件"
        disabled={busy}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          if (file.size > 90000) {
            setError('OPML 文件不能超过90 KB');
            return;
          }
          await act(
            'opml',
            { text: await file.text(), watch_id: watchId || null },
            '订阅已处理；请检查来源状态，无法识别的入口会保留为待接入',
          );
        }}
      />
    </div>
  );
}
