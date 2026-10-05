'use client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { NativeSelect } from '@/components/ui/native-select';
import { regions } from '@/features/workspace/display';
import type { WorkspaceState } from '@/features/workspace/use-workspace';
export default function TopicsView({
  watchTopics,
  editing,
  setEditing,
  profileDraft,
  setProfileDraft,
  changeWatch,
  setTab,
  setMessage,
  action,
}: Pick<
  WorkspaceState,
  | 'watchTopics'
  | 'editing'
  | 'setEditing'
  | 'profileDraft'
  | 'setProfileDraft'
  | 'changeWatch'
  | 'setTab'
  | 'setMessage'
  | 'action'
>) {
  return (
    <section className="import-panel">
      <h2>自定义关注主题</h2>
      <p>
        每个主题独立设置关键词、来源和兴趣偏好。暂停主题会停止其自动采集；共享来源仍可能为其他主题更新。
      </p>
      <div className="source-grid">
        {watchTopics.map((t) => (
          <article className="source-card" key={t.id}>
            <h3>{t.name}</h3>
            <p>{t.description}</p>
            <p>
              {t.article_count} 条资料 · {t.source_count} 个来源 ·{' '}
              {t.enabled ? '采集中' : '已暂停'}
            </p>
            <div className="source-feedback">
              <Button variant="outline" onClick={() => changeWatch(t.id)}>
                查看资讯
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setEditing(t);
                }}
              >
                编辑
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  void action('watch-topic', {
                    id: t.id,
                    enabled: !t.enabled,
                  })
                }
              >
                {t.enabled ? '暂停主题' : '恢复主题'}
              </Button>
            </div>
          </article>
        ))}
      </div>
      <Button
        variant="outline"
        onClick={() => {
          setEditing(null);
        }}
      >
        新建主题
      </Button>
      <form
        key={editing?.id || 'new'}
        className="source-add"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = e.currentTarget;
          const d = new FormData(f);
          const r = await action('watch-topic', {
            ...(editing ? { id: editing.id } : {}),
            name: d.get('name'),
            description: d.get('description'),
            keywords: d.get('keywords'),
            exclude: d.get('exclude'),
            content_profile: profileDraft,
            regions: profileDraft === 'developer' ? [] : d.getAll('regions'),
            news_search: d.get('news_search') === 'on',
            enabled: d.get('enabled') === 'on',
          });
          if (r) {
            changeWatch(String(r.id));
            setEditing(null);
            setTab('来源管理');
            setMessage(
              '主题已保存。请从全局来源库选择已有信息源，批量加入此主题。',
            );
          }
        }}
      >
        <h3>{editing ? '编辑 ' + editing.name : '新建主题'}</h3>
        <label htmlFor="topic-name">
          主题名称
          <Input
            id="topic-name"
            name="name"
            required
            maxLength={80}
            defaultValue={editing?.name || ''}
            placeholder="例如：Coding 与 Agent / 网络安全 / 游戏开发"
          />
        </label>
        <label htmlFor="topic-description">
          关注说明
          <Textarea
            id="topic-description"
            name="description"
            defaultValue={editing?.description || ''}
          />
        </label>
        <label htmlFor="topic-keywords">
          主题关键词（任意一个匹配后，再按内容侧重筛选）
          <Textarea
            id="topic-keywords"
            name="keywords"
            required
            rows={5}
            defaultValue={editing?.keywords.join('\n') || ''}
            placeholder="Agent, MCP, 编程助手, coding"
          />
        </label>
        <label htmlFor="topic-content_profile">
          内容侧重
          <NativeSelect
            id="topic-content_profile"
            name="content_profile"
            value={profileDraft}
            onChange={(e) =>
              setProfileDraft(e.target.value as 'standard' | 'developer')
            }
          >
            <option value="standard">一般资讯 · 按关键词筛选</option>
            <option value="developer">开发者内容 · 需要具体技术线索</option>
          </NativeSelect>
        </label>
        {profileDraft === 'developer' && (
          <p>
            优先收录工具更新、实现方法、代码、评测与排障内容，按技术方向浏览。筛选依据标题与摘要，不代表事实已核验；手动收录会保留。
          </p>
        )}
        <label htmlFor="topic-exclude">
          排除词
          <Textarea
            id="topic-exclude"
            name="exclude"
            defaultValue={editing?.exclude.join('\n') || ''}
            placeholder="例如：招聘, 课程广告"
          />
        </label>
        {profileDraft !== 'developer' && (
          <>
            {' '}
            <p>
              地区不勾选表示不限地区；公开新闻检索默认使用全球与中国大陆入口。
            </p>
            <div className="source-feedback">
              {regions.map((r) => (
                <label key={r}>
                  <input
                    type="checkbox"
                    name="regions"
                    value={r}
                    defaultChecked={editing?.regions.includes(r)}
                  />{' '}
                  {r}
                </label>
              ))}
            </div>
          </>
        )}
        <label>
          <input
            type="checkbox"
            name="news_search"
            defaultChecked={editing?.news_search ?? true}
          />{' '}
          自动添加公开新闻检索入口
        </label>
        <label>
          <input
            type="checkbox"
            name="enabled"
            defaultChecked={editing?.enabled ?? true}
          />{' '}
          启用主题采集
        </label>
        <Button type="submit">保存主题</Button>
        <p>
          检索公开新闻索引和已关注来源；视频、播客默认保存标题与摘要，登录或付费内容需要已有授权入口。
        </p>
      </form>
    </section>
  );
}
