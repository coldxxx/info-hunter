'use client';
import { ArrowLeft, ExternalLink, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Source } from '@/lib/api-types/sources';
import SourceConnection from './source-connection';
import { adapterLabel, stateClass, time } from './source-utils';
import type { SourceViewProps } from './use-source-manager';

type SourceDetailViewProps = SourceViewProps & { selected: Source };

export default function SourceDetailView({
  watchId,
  watchName,
  loading,
  onAction,
  onMessage,
  selected,
  setSelectedId,
  pendingAction,
  setPendingAction,
  askDelete,
  detailHeading,
  setRetry,
  detailLoading,
  detailError,
  detail,
  feedback,
  scope,
  addToTopic,
}: SourceDetailViewProps) {
  return (
    <>
      <Button
        variant="outline"
        className="source-back"
        onClick={() => setSelectedId(null)}
      >
        <ArrowLeft />
        返回来源列表
      </Button>
      <div className="source-detail-header">
        <div>
          <span className="eyebrow">SOURCE / {selected.id}</span>
          <h2 ref={detailHeading} tabIndex={-1}>
            {selected.config.name}
          </h2>
          <a
            className="source-home-link"
            href={selected.config.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {selected.config.url}
            <ExternalLink size={14} />
          </a>
        </div>
        <div className="source-detail-actions">
          <span className={'source-state ' + stateClass(selected)}>
            {selected.config.enabled ? selected.status : '已暂停'}
          </span>
          <Button
            variant="destructive"
            disabled={pendingAction || loading}
            onClick={() => askDelete(selected)}
          >
            <Trash2 />
            删除来源
          </Button>
        </div>
      </div>
      <SourceConnection
        key={selected.id}
        source={selected}
        onChanged={() => {
          setRetry((v) => v + 1);
          void onAction('refresh-platform', {});
        }}
      />
      {selected.error && (
        <div
          className={
            'notice source-issue ' +
            (selected.status === '失败' ? 'error' : 'warning')
          }
        >
          <span>最近检查记录</span>
          <p>{selected.error}</p>
        </div>
      )}
      {detailLoading && (
        <output className="empty-state">正在读取采集实现与归档记录…</output>
      )}
      {detailError && (
        <div className="notice error" role="alert">
          {detailError}
          <Button variant="outline" onClick={() => setRetry((v) => v + 1)}>
            重试
          </Button>
        </div>
      )}
      {detail && (
        <>
          <div className="source-facts">
            <div>
              <span>实际采集方式</span>
              <strong>{adapterLabel(detail.effective_adapter)}</strong>
            </div>
            <div>
              <span>{watchId ? '来源归档 / 当前主题' : '来源归档'}</span>
              <strong className="mono">
                {detail.stats.archived}
                {watchId && ` / ${detail.stats.in_topic}`}
              </strong>
            </div>
            <div>
              <span>调度到期间隔</span>
              <strong>
                {detail.schedule.enabled
                  ? `${detail.schedule.interval_hours} 小时`
                  : '未参与调度'}
              </strong>
            </div>
            <div>
              <span>最近成功 · 北京时间</span>
              <strong className="mono">{time(selected.success_at)}</strong>
              {!!detail.next_at && (
                <small>
                  下次巡检最早{' '}
                  {time(new Date(detail.next_at * 1000).toISOString())}
                </small>
              )}
            </div>
          </div>
          <div className="source-detail-grid">
            <div>
              <section className="shared-capture">
                <span className="eyebrow">SHARED CAPTURE ADAPTER</span>
                <h3>{detail.capture_strategy.adapter_name} · 共用采集适配器</h3>
                <p>{detail.capture_strategy.description}</p>
                <p>
                  这个来源只配置入口参数，所有关注它的主题共用同一份配置和采集结果。
                </p>
                <dl className="capture-parameters">
                  {detail.capture_strategy.parameters.map((parameter) => (
                    <div key={parameter.label}>
                      <dt>{parameter.label}</dt>
                      <dd>{parameter.value || '尚未配置'}</dd>
                    </div>
                  ))}
                </dl>
                {selected.config.search_topic && (
                  <p>
                    这是由关键词生成的检索源；加入其他主题后仍读取当前查询，内容再按各主题规则筛选。
                  </p>
                )}
              </section>
              <section className="pipeline-section">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">COLLECTION PIPELINE</span>
                    <h3>采集实现流程</h3>
                  </div>
                  <span className="subtle">
                    当前配置 · {detail.steps.length} 个环节
                  </span>
                </div>
                <p className="pipeline-access">{detail.access.message}</p>
                <dl className="endpoint-block">
                  <dt>实际读取入口</dt>
                  <dd>
                    <a
                      href={detail.entry_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {detail.entry_url}
                    </a>
                  </dd>
                  {detail.query && (
                    <>
                      <dt>查询条件</dt>
                      <dd>
                        <code>{detail.query}</code>
                      </dd>
                    </>
                  )}
                </dl>
                <ol className="pipeline-steps">
                  {detail.steps.map((step, i) => (
                    <li key={step.title}>
                      <span className="step-number">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <div>
                        <h4>{step.title}</h4>
                        <p>{step.detail}</p>
                        <code className="implementation-ref">
                          {step.implementation}
                        </code>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
              <section className="source-recent">
                <div className="section-heading">
                  <h3>最近归档</h3>
                  <span className="subtle">此来源的最新 8 条 · 所有主题</span>
                </div>
                {detail.recent.length ? (
                  <ul>
                    {detail.recent.map((a) => (
                      <li key={a.id}>
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {a.title}
                          <ExternalLink size={14} />
                        </a>
                        <time>{time(a.published_at)}</time>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-inline">此来源还没有归档记录。</p>
                )}
              </section>
            </div>
            <aside className="source-inspector">
              <section>
                <span className="eyebrow">LAST CHECK</span>
                <h3>最近采集结果</h3>
                <dl className="inspector-facts">
                  <dt>最近检查</dt>
                  <dd>{time(selected.checked_at)}</dd>
                  <dt>筛选后候选</dt>
                  <dd>{selected.last_count} 条（含重复）</dd>
                  <dt>最近自动轮次</dt>
                  <dd>{time(detail.last_run?.finished_at)}</dd>
                  <dt>轮次新增归档</dt>
                  <dd>
                    {detail.last_run
                      ? `${detail.last_run.added} 条 / 候选 ${detail.last_run.found} 条`
                      : '暂无自动轮次记录'}
                  </dd>
                </dl>
                {detail.last_run?.error && (
                  <p className="source-error">{detail.last_run.error}</p>
                )}
              </section>
              <section>
                <span className="eyebrow">TOPIC RULES</span>
                <h3>主题与筛选</h3>
                {detail.topics.length ? (
                  detail.topics.map((t) => (
                    <div
                      className={
                        'binding-rule ' + (t.id === watchId ? 'current' : '')
                      }
                      key={t.id}
                    >
                      <div className="binding-title">
                        {t.name}
                        <span>
                          {t.id === watchId
                            ? '当前主题'
                            : t.enabled
                              ? '已启用'
                              : '已暂停'}
                        </span>
                      </div>
                      <p>
                        {t.include_all ? '全部收录' : '按关键词收录'}
                        {t.content_profile === 'developer'
                          ? ' · 开发者内容筛选'
                          : ''}
                        {!t.enabled ? ' · 主题已暂停' : ''}
                      </p>
                      <dl>
                        <dt>关键词</dt>
                        <dd>{t.keywords.join('、') || '无'}</dd>
                        <dt>排除词</dt>
                        <dd>{t.exclude.join('、') || '无'}</dd>
                        {t.content_profile !== 'developer' && (
                          <>
                            <dt>地区</dt>
                            <dd>{t.regions.join('、') || '不限'}</dd>
                          </>
                        )}
                      </dl>
                    </div>
                  ))
                ) : (
                  <p className="empty-inline">尚未绑定主题。</p>
                )}
              </section>
              {watchId && selected.followed && (
                <section>
                  <span className="eyebrow">PREFERENCE</span>
                  <h3>兴趣与调度</h3>
                  <div className="preference-score">
                    {selected.preference?.score ?? 10}
                    <span>/ 100 · 当前主题</span>
                  </div>
                  <p>{selected.preference?.reason}</p>
                  <p>
                    后台调度使用启用主题中的最高兴趣分：
                    {detail.schedule.policy.score}。
                    {detail.schedule.baseline
                      ? '这个基础来源尚无偏好信号，后台每 6 小时检查一次。'
                      : `后台每 6 小时检查，达到 ${detail.schedule.interval_hours} 小时间隔后再按每轮配额选择。`}
                  </p>
                  <div className="source-feedback">
                    <Button
                      disabled={pendingAction}
                      variant="outline"
                      onClick={() => void feedback('prefer')}
                    >
                      多看
                    </Button>
                    <Button
                      disabled={pendingAction}
                      variant="outline"
                      onClick={() => void feedback('less')}
                    >
                      少看
                    </Button>
                    <Button
                      disabled={pendingAction}
                      variant="outline"
                      onClick={() => void feedback('reset')}
                    >
                      重置偏好
                    </Button>
                  </div>
                </section>
              )}
              <section>
                <span className="eyebrow">SOURCE CONTROL</span>
                <h3>来源设置</h3>
                <p>
                  {selected.config.note || '公开来源，保留原始链接与摘要。'}
                </p>
                <dl className="inspector-facts">
                  <dt>登记适配器</dt>
                  <dd>{detail.configured_adapter}</dd>
                  <dt>地区 / 类型</dt>
                  <dd>
                    {selected.config.region} / {selected.config.kind}
                  </dd>
                </dl>
                <Button
                  disabled={pendingAction}
                  variant="outline"
                  onClick={() =>
                    void feedback(selected.config.enabled ? 'pause' : 'resume')
                  }
                >
                  {selected.config.enabled
                    ? '暂停所有主题采集'
                    : '恢复来源采集'}
                </Button>
                {watchId && selected.followed && (
                  <Button
                    disabled={pendingAction}
                    className="remove-source"
                    variant="ghost"
                    onClick={async () => {
                      setPendingAction(true);
                      try {
                        if (
                          await onAction('watch-source', {
                            watch_id: watchId,
                            source_id: selected.id,
                            follow: false,
                          })
                        ) {
                          if (scope === 'topic') setSelectedId(null);
                          onMessage('来源已移出此主题，历史归档保留');
                        }
                      } finally {
                        setPendingAction(false);
                      }
                    }}
                  >
                    移出此主题
                  </Button>
                )}
                {watchId && !selected.followed && (
                  <Button
                    disabled={pendingAction || loading}
                    variant="outline"
                    onClick={() => void addToTopic([selected.id])}
                  >
                    <Plus />
                    加入「{watchName}」
                  </Button>
                )}
              </section>
            </aside>
          </div>
        </>
      )}
    </>
  );
}
