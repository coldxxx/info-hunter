'use client';
import { Button } from '@/components/ui/button';
import ConnectionsView from './connections-view';
import PodcastsView from './podcasts-view';
import { WechatView, OpmlView } from './platform-import-views';
import {
  usePlatformPanel,
  type PlatformPanelProps,
} from './use-platform-panel';

export default function PlatformPanel(props: PlatformPanelProps) {
  const { watchId } = props;
  const controller = usePlatformPanel(props);
  const { tab, setTab, error, setError, message, setMessage } = controller;
  return (
    <section className="platform-tools" aria-label="平台接入与发现">
      <div className="platform-tabs">
        {[
          ['connections', '平台连接'],
          ['podcasts', '发现播客'],
          ['wechat', '公众号与文章'],
          ['opml', '导入 OPML'],
        ].map(([id, name]) => (
          <Button
            key={id}
            variant={tab === id ? 'default' : 'outline'}
            onClick={() => {
              setTab(tab === id ? '' : id);
              setError('');
              setMessage('');
            }}
            aria-expanded={tab === id}
          >
            {name}
          </Button>
        ))}
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {message && <output className="notice">{message}</output>}
      {tab === 'connections' && <ConnectionsView {...controller} />}
      {tab === 'podcasts' && <PodcastsView watchId={watchId} {...controller} />}
      {tab === 'wechat' && <WechatView watchId={watchId} {...controller} />}
      {tab === 'opml' && <OpmlView watchId={watchId} {...controller} />}
    </section>
  );
}
