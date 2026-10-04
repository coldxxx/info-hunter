'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Source } from '@/lib/api-types/sources';
import type { SourceViewProps } from './use-source-manager';

type SourceAddFormProps = Pick<
  SourceViewProps,
  | 'watchId'
  | 'watchName'
  | 'isDeveloper'
  | 'onAction'
  | 'onMessage'
  | 'adding'
  | 'setAdding'
  | 'setAddOpen'
>;

export default function SourceAddForm({
  watchId,
  watchName,
  isDeveloper,
  onAction,
  onMessage,
  adding,
  setAdding,
  setAddOpen,
}: SourceAddFormProps) {
  return (
    <div id="source-add-panel" className="source-add-panel">
      <form
        className="source-add"
        onSubmit={async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const data = new FormData(form);
          setAdding(true);
          try {
            const result = await onAction('source', {
              ...Object.fromEntries(data),
              watch_id: data.get('bind_topic') === 'on' ? watchId : null,
              include_all: data.get('include_all') === 'on',
            });
            if (result) {
              onMessage(
                '来源已保存到全局来源库。' +
                  (result.config as Source['config']).note,
              );
              form.reset();
              setAddOpen(false);
            }
          } finally {
            setAdding(false);
          }
        }}
      >
        <h3>新增到全局来源库</h3>
        <p>
          粘贴作者、板块、频道或订阅链接，自动识别可用入口。已有来源可直接从下方列表选择。
        </p>
        <label htmlFor="new-source-url">
          来源链接
          <Input
            id="new-source-url"
            name="url"
            type="url"
            required
            placeholder="https://…"
          />
        </label>
        <div className="form-row">
          <label htmlFor="new-source-name">
            名称（可留空）
            <Input id="new-source-name" name="name" />
          </label>
          <label htmlFor="new-source-feed">
            RSS / Atom 地址（可留空）
            <Input
              id="new-source-feed"
              name="feed_url"
              type="url"
              placeholder="https://…/feed"
            />
          </label>
        </div>
        <label>
          <input
            type="checkbox"
            name="bind_topic"
            defaultChecked={!!watchId}
            disabled={!watchId}
          />
          {watchId
            ? `同时加入「${watchName}」`
            : '仅保存到全局来源库，稍后选择主题关注'}
        </label>
        <label>
          <input type="checkbox" name="include_all" defaultChecked />
          {isDeveloper
            ? '不限制关键词，仍应用开发者内容要求与排除词'
            : '全部收录，仍应用地区与排除词'}
        </label>
        <Button type="submit" disabled={adding}>
          {adding ? '正在识别来源…' : '保存信息源'}
        </Button>
      </form>
    </div>
  );
}
