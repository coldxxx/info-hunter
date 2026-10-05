'use client';
import { useState } from 'react';
import type { SemanticPair as Pair } from '@/lib/api-types/semantic';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { ArrowUpRight } from 'lucide-react';
import { relations, date } from './semantic-display';

export default function PairCard({
  pair,
  onReview,
  busy,
}: {
  pair: Pair;
  onReview: (pair: Pair, relation: string, note: string) => void;
  busy: boolean;
}) {
  const [relation, setRelation] = useState(
    pair.reviewed_relation || pair.relation,
  );
  const [note, setNote] = useState(pair.review_note || '');
  return (
    <article className="semantic-pair">
      <div className="semantic-pair-heading">
        <span className="semantic-relation" data-relation={pair.relation}>
          {relations[pair.relation]}
        </span>
        <span>
          {pair.reviewed_relation
            ? '人工复核：' + relations[pair.reviewed_relation]
            : pair.status === 'auto'
              ? '已自动折叠'
              : '待复核'}
        </span>
        <span className="semantic-score">
          检索相似度 {pair.similarity.toFixed(3)}
        </span>
      </div>
      <div className="semantic-comparison">
        {([pair.left, pair.right] as const).map((a, i) => (
          <section key={a.id}>
            <div className="semantic-source">
              {i === 0 ? '资料 A' : '资料 B'} · {a.publisher} · {a.language}
            </div>
            <a href={a.url} target="_blank" rel="noreferrer">
              <h3>
                {a.title} <ArrowUpRight size={14} />
              </h3>
            </a>
            <time>{date(a.published_at)}</time>
            <p>{a.excerpt || '未提供摘要；请打开原文核对。'}</p>
            {(a.has_full_text || a.truncated) && (
              <details className="semantic-original">
                <summary>查看模型检查的原文{a.truncated ? '片段' : ''}</summary>
                <pre>{a.review_text}</pre>
                {a.truncated && (
                  <small>后续正文未进入此次判断，请打开原文继续核对。</small>
                )}
              </details>
            )}
            <blockquote>
              {i === 0 ? pair.decision.evidence_a : pair.decision.evidence_b}
            </blockquote>
          </section>
        ))}
      </div>
      <div className="semantic-reason">
        <strong>判断依据</strong>
        <p>{pair.decision.reason}</p>
        <small>
          检查范围：{pair.decision.text_scope} · 同一事件：
          {pair.decision.same_event ? '是' : '否'} · 信息增量：
          {pair.decision.new_information ? '有' : '无'} · 事实冲突：
          {pair.decision.contradiction ? '有' : '无'}
        </small>
        {!!pair.decision.guards.length && (
          <p className="semantic-guard">{pair.decision.guards.join('；')}</p>
        )}
      </div>
      <div className="semantic-review-controls">
        <label>
          复核关系
          <NativeSelect
            aria-label={'复核关系 ' + pair.left.title}
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
          >
            {Object.entries(relations).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Input
          aria-label="复核备注"
          placeholder="复核备注（可选）"
          value={note}
          maxLength={1000}
          onChange={(e) => setNote(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => onReview(pair, relation, note)}
        >
          保存复核
        </Button>
      </div>
      <small className="semantic-card-foot">
        确认重复会合并两组的展示；其他关系保留独立文章。原文、收藏和笔记保留。判断模型：
        {pair.model}
      </small>
    </article>
  );
}
