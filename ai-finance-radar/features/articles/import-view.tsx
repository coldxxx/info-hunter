'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect } from '@/components/ui/native-select';
import { Plus } from 'lucide-react';
import { regions } from '@/features/workspace/display';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export default function ImportView({
  watchId,
  isDeveloper,
  setMessage,
  action,
}: Pick<WorkspaceState, 'watchId' | 'isDeveloper' | 'setMessage' | 'action'>) {
  return (
    <section className="import-panel">
      <h2>收录研报与论坛线索</h2>
      <p>
        用于你已有权限查看的资料。保存链接与自己的摘录，不会自动获取付费全文。
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const data = Object.fromEntries(new FormData(form));
          const r = await action('import', {
            ...data,
            watch_id: watchId || 'coding-agent',
          });
          if (r) {
            setMessage(r.added ? '资料已收录' : '该链接已在资料库中');
            form.reset();
          }
        }}
      >
        <label htmlFor="import-title">
          标题
          <Input id="import-title" name="title" required maxLength={1000} />
        </label>
        <label htmlFor="import-url">
          原始链接
          <Input
            id="import-url"
            name="url"
            type="url"
            required
            placeholder="https://…"
          />
        </label>
        <div className="form-row">
          <label htmlFor="import-publisher">
            发布者
            <Input
              id="import-publisher"
              name="publisher"
              required
              placeholder="机构 / 媒体 / 作者"
            />
          </label>
          {isDeveloper ? (
            <input type="hidden" name="region" value="全球" />
          ) : (
            <>
              {' '}
              <label htmlFor="import-region">
                地区
                <NativeSelect id="import-region" name="region">
                  {regions.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </NativeSelect>
              </label>
            </>
          )}
          <label htmlFor="import-kind">
            类型
            <NativeSelect id="import-kind" name="kind">
              {[
                '研报',
                '研究观点',
                '论坛',
                '视频',
                '播客',
                '新闻',
                '公司发布',
              ].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </NativeSelect>
          </label>
        </div>
        <div className="form-row">
          <label htmlFor="import-date">
            发布日期（可留空）
            <Input id="import-date" name="published_at" type="date" />
          </label>
          <label htmlFor="import-language">
            原文语言
            <Input
              id="import-language"
              name="language"
              placeholder="中文 / English / 日本語 / 한국어"
            />
          </label>
        </div>
        <label htmlFor="import-excerpt">
          授权摘要或自己的摘录
          <Textarea
            id="import-excerpt"
            name="excerpt"
            rows={8}
            maxLength={20000}
          />
        </label>
        <Button type="submit">
          <Plus />
          收录到资料库
        </Button>
      </form>
    </section>
  );
}
