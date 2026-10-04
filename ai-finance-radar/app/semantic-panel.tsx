'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { GitCompareArrows, RefreshCw, Undo2, ArrowUpRight } from 'lucide-react';
import { useUrlState } from '@/lib/url-state';

const relations: Record<string, string> = {
  duplicate: '重复信息', complement: '同事件有增量', conflict: '同事件有冲突',
  related: '主题相关', unrelated: '不相关', uncertain: '信息不足',
};
type Config = {
  enabled: boolean; mode: 'review' | 'auto'; embedding_model: string; judge_model: string;
  embedding_url: string; judge_url: string; candidate_threshold: number; auto_threshold: number;
  top_k: number; window_days: number; daily_pair_limit: number;
};
type Article = { id: string; title: string; url: string; excerpt: string; publisher: string; language: string; published_at: string | null; kind: string; review_text: string; has_full_text: boolean; truncated: boolean };
type Pair = {
  id: string; left: Article; right: Article; similarity: number; relation: string; model: string;
  status: string; reviewed_relation: string | null; review_note: string | null; updated_at: number;
  decision: { confidence: number; reason: string; evidence_a: string; evidence_b: string;
    guards: string[]; text_scope: string; same_event: boolean; new_information: boolean; contradiction: boolean };
};
type Status = {
  config: Config; jobs: Record<string, number>; relations: Record<string, number>; awaiting: number;
  reviewed: number; collapsed: number; last_error: string;
  auto_gate: { ready: boolean; requirement: string; report: { count?: number; precision?: number; recall?: number } };
  budget: { used: number; limit: number; resumes_at: number | null };
  index: { total: number; indexed: number };
  events: { id: number; action: string; target: string; created_at: number; undone_by: number | null }[];
};
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api/semantic/' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const result: unknown = await response.json();
  if (!response.ok) throw new Error(result && typeof result === 'object' && 'error' in result ? String(result.error) : '请求失败，请检查本地服务');
  return result as T;
}
const date = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '发布日期未知';

function PairCard({ pair, onReview, busy }: { pair: Pair; onReview: (pair: Pair, relation: string, note: string) => void; busy: boolean }) {
  const [relation, setRelation] = useState(pair.reviewed_relation || pair.relation);
  const [note, setNote] = useState(pair.review_note || '');
  return <article className="semantic-pair">
    <div className="semantic-pair-heading">
      <span className="semantic-relation" data-relation={pair.relation}>{relations[pair.relation]}</span>
      <span>{pair.reviewed_relation ? '人工复核：' + relations[pair.reviewed_relation] : pair.status === 'auto' ? '已自动折叠' : '待复核'}</span>
      <span className="semantic-score">检索相似度 {pair.similarity.toFixed(3)}</span>
    </div>
    <div className="semantic-comparison">
      {([pair.left, pair.right] as const).map((a, i) => <section key={a.id}>
        <div className="semantic-source">{i === 0 ? '资料 A' : '资料 B'} · {a.publisher} · {a.language}</div>
        <a href={a.url} target="_blank" rel="noreferrer"><h3>{a.title} <ArrowUpRight size={14}/></h3></a>
        <time>{date(a.published_at)}</time>
        <p>{a.excerpt || '未提供摘要；请打开原文核对。'}</p>
        {(a.has_full_text || a.truncated) && <details className="semantic-original"><summary>查看模型检查的原文{a.truncated ? '片段' : ''}</summary><pre>{a.review_text}</pre>{a.truncated && <small>后续正文未进入此次判断，请打开原文继续核对。</small>}</details>}
        <blockquote>{i === 0 ? pair.decision.evidence_a : pair.decision.evidence_b}</blockquote>
      </section>)}
    </div>
    <div className="semantic-reason"><strong>判断依据</strong><p>{pair.decision.reason}</p>
      <small>检查范围：{pair.decision.text_scope} · 同一事件：{pair.decision.same_event ? '是' : '否'} · 信息增量：{pair.decision.new_information ? '有' : '无'} · 事实冲突：{pair.decision.contradiction ? '有' : '无'}</small>
      {!!pair.decision.guards.length && <p className="semantic-guard">{pair.decision.guards.join('；')}</p>}
    </div>
    <div className="semantic-review-controls">
      <label>复核关系<NativeSelect aria-label={'复核关系 ' + pair.left.title} value={relation} onChange={e => setRelation(e.target.value)}>
        {Object.entries(relations).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </NativeSelect></label>
      <Input aria-label="复核备注" placeholder="复核备注（可选）" value={note} maxLength={1000} onChange={e => setNote(e.target.value)}/>
      <Button variant="outline" disabled={busy} onClick={() => onReview(pair, relation, note)}>保存复核</Button>
    </div>
    <small className="semantic-card-foot">确认重复会合并两组的展示；其他关系保留独立文章。原文、收藏和笔记保留。判断模型：{pair.model}</small>
  </article>;
}

export default function SemanticPanel({ watchId, onChange }: { watchId: string; onChange: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [list, setList] = useState<{ total: number; items: Pair[] }>({ total: 0, items: [] });
  const [filter, setFilter] = useUrlState('semantic_status', 'review', { values: ['review', 'reviewed', 'all'] });
  const [relationFilter, setRelationFilter] = useUrlState('semantic_relation', '', { values: ['', ...Object.keys(relations)] });
  const [offset, setOffset] = useUrlState('semantic_offset', 0);
  const previousWatch = useRef(watchId);
  useEffect(() => { if (previousWatch.current !== watchId) { previousWatch.current = watchId; setOffset(0); } }, [watchId, setOffset]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const refresh = useCallback(async () => {
    const q = new URLSearchParams({ status: filter, watch_id: watchId, offset: String(offset), relation: relationFilter });
    const [s, p] = await Promise.all([request<Status>('status'), request<{ total: number; items: Pair[] }>('pairs?' + q)]);
    setStatus(s); setDraft(current => current || s.config); setList(p);
  }, [filter, watchId, offset, relationFilter]);
  useEffect(() => {
    let live = true;
    const run = () => refresh().catch(e => { if (live) setError(String(e.message)); });
    void run(); const timer = setInterval(run, 5000);
    return () => { live = false; clearInterval(timer); };
  }, [refresh]);
  async function act(path: string, body: unknown, success: string) {
    setBusy(true); setError(''); setMessage('');
    try { const result = await request<Record<string, unknown>>(path, body); await refresh(); onChange(); setMessage(success); return result; }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  if (!status || !draft) return <div className="empty-state">{error || '正在读取语义去重状态…'}</div>;
  const outstanding = (status.jobs.queued || 0) + (status.jobs.running || 0);
  return <section className="semantic-panel">
    <div className="semantic-intro"><GitCompareArrows size={24}/><div><h2>让重复的信息收拢，让新的证据留下。</h2><p>先检索相似资料，再判断事件、信息增量和冲突。复核结果可撤销，拆分后会记住你的选择。</p></div></div>
    <div className="semantic-metrics">
      <div><span>待复核资料对 · 全库</span><strong>{status.awaiting}</strong></div>
      <div><span>后台待处理</span><strong>{outstanding}</strong></div>
      <div><span>人工复核</span><strong>{status.reviewed}</strong></div>
      <div><span>已完成资料</span><strong>{status.jobs.completed || 0}</strong></div>
    </div>
    <div className="semantic-actions">
      <span className="semantic-run-state">{status.config.enabled ? status.config.mode === 'auto' ? '自动折叠模式' : '人工复核模式' : '后台处理已暂停'}</span>
      <Button variant="outline" disabled={busy} onClick={() => void act('settings', { enabled: !status.config.enabled }, status.config.enabled ? '后台处理已暂停；正在完成的模型请求会收尾。' : '后台处理已开启，新资料会自动排队。')}>
        {status.config.enabled ? '暂停处理' : '开启处理'}</Button>
      <Button variant="outline" disabled={busy || !status.config.enabled} onClick={() => void act('run', { watch_id: watchId, retry: true }, '已为当前资料范围排队；后台可在重启后继续。')}><RefreshCw size={16}/>处理历史资料</Button>
      <Button variant="outline" disabled={busy} onClick={async () => {
        const r = await act('health', {}, '');
        if (r) setMessage(r.ready ? '向量模型与判断模型均可连接。' : (r.models as { error: string }[]).map(m => m.error).filter(Boolean).join('；'));
      }}>检查模型连接</Button>
      <Button variant="outline" onClick={async () => {
        try { const labels = await request<{ cases: unknown[] }>('labels'); const url = URL.createObjectURL(new Blob([JSON.stringify(labels.cases, null, 2)], { type: 'application/json' }));
          const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'semantic-reviewed-pairs.json'; anchor.click(); URL.revokeObjectURL(url); }
        catch (e) { setError(String(e)); }
      }}>导出复核样本</Button>
    </div>
    <p className="semantic-scope">全库向量索引 {status.index.indexed} / {status.index.total} 篇{status.index.indexed < status.index.total ? '；首次索引完成后开始判断资料关系。' : '；相似资料正在逐步分析。'}</p>
    <p className="semantic-scope">最近 24 小时判断 {status.budget.used} / {status.budget.limit} 对{status.budget.resumes_at ? '，预算已用完，将在 ' + date(new Date(status.budget.resumes_at * 1000).toISOString()) + ' 后自动继续。' : '；相似候选与判断结果会缓存。'}</p>
    {status.jobs.failed > 0 && <div className="semantic-guard">{status.jobs.failed} 条处理失败，可通过“处理历史资料”重试。{status.last_error}</div>}
    {error && <p role="alert" className="semantic-guard">{error}</p>}
    {message && <output className="semantic-message">{message}</output>}
    <details className="semantic-settings"><summary>模型与处理设置</summary>
      <div className="semantic-settings-grid">
        {([['embedding_model', '向量模型标识'], ['judge_model', '判断模型标识'], ['embedding_url', '向量服务地址（留空使用本机）'], ['judge_url', '判断服务地址（留空使用本机）']] as const).map(([key, label]) => <label key={key}>{label}<Input value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })}/></label>)}
        <label htmlFor="semantic-run-mode">处理模式<NativeSelect id="semantic-run-mode" value={draft.mode} onChange={e => setDraft({ ...draft, mode: e.target.value as Config['mode'] })}><option value="review">人工复核</option><option value="auto" disabled={!status.auto_gate.ready}>验证后自动折叠</option></NativeSelect></label>
        {([['candidate_threshold', '候选相似度下限', 0, 1, 0.01], ['top_k', '每篇最多候选数', 1, 20, 1], ['window_days', '候选发布日期范围（天）', 1, 90, 1], ['daily_pair_limit', '每日判断预算（资料对）', 1, 5000, 1], ['auto_threshold', '自动折叠模型分数下限', 0, 1, 0.01]] as const).map(([key, label, min, max, step]) => <label key={key}>{label}<Input type="number" min={min} max={max} step={step} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: Number(e.target.value) })}/></label>)}
      </div>
      <p>模型分数不代表已测得的正确率。自动折叠条件：{status.auto_gate.requirement}。当前验证样本 {status.auto_gate.report.count || 0} 对。</p>
      <Button variant="outline" disabled={busy} onClick={() => void act('settings', { ...draft, enabled: status.config.enabled }, '设置已保存；模型或策略改变后资料将重新排队。')}>保存设置</Button>
    </details>
    <div className="semantic-list-heading"><h2>资料关系复核</h2><div>
      <NativeSelect aria-label="复核状态" value={filter} onChange={e => { setFilter(e.target.value); setOffset(0); }}><option value="review">待复核</option><option value="reviewed">已复核</option><option value="all">全部判断</option></NativeSelect>
      <NativeSelect aria-label="关系类型" value={relationFilter} onChange={e => { setRelationFilter(e.target.value); setOffset(0); }}><option value="">所有关系</option>{Object.entries(relations).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</NativeSelect>
    </div></div>
    <p className="semantic-scope">{watchId ? '当前主题内的资料对' : '全部主题的资料对'} · {list.total} 对。主题相关和有增量的报道保留独立展示。</p>
    {list.items.length ? list.items.map(pair => <PairCard key={pair.id + pair.updated_at + (pair.reviewed_relation || '')} pair={pair} busy={busy} onReview={(p, relation, note) => void act('review', { pair_id: p.id, relation, note, expected: p.updated_at }, relation === 'duplicate' ? '已确认重复并折叠展示，可以在操作记录中撤销。' : '已保存关系，资料保持独立。')}/>) : <div className="empty-state">{outstanding && status.config.enabled ? '后台正在处理，找到候选后会在这里显示。' : '当前范围没有符合条件的资料对。'}</div>}
    <div className="semantic-pagination"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</Button><span>{list.total ? offset + 1 : 0}–{Math.min(offset + 20, list.total)} / {list.total}</span><Button variant="outline" disabled={offset + 20 >= list.total} onClick={() => setOffset(offset + 20)}>下一页</Button></div>
    {!!status.events.length && <details className="semantic-settings"><summary>最近操作 · 可撤销</summary>{status.events.map(event => <div className="semantic-audit" key={event.id}><span>{new Date(event.created_at * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })} · {event.action === 'split' ? '拆分文章' : event.action === 'undo' ? '撤销操作' : '复核关系'} #{event.id}</span>{!event.undone_by && event.action !== 'undo' && <Button variant="outline" size="sm" disabled={busy} onClick={() => void act('undo', { event_id: event.id }, '操作已撤销，信息流分组已恢复。')}><Undo2 size={14}/>撤销</Button>}</div>)}</details>}
  </section>;
}

export function SemanticArticleActions({ articleId, duplicateCount, watchId, onChange }: { articleId: string; duplicateCount: number; watchId: string; onChange: () => void }) {
  const [items, setItems] = useState<Pair[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { let live = true; void request<{ items: Pair[] }>('pairs?' + new URLSearchParams({ status: 'all', article_id: articleId, watch_id: watchId })).then(r => { if (live) setItems(r.items); }).catch(() => {}); return () => { live = false; }; }, [articleId, watchId]);
  return <div className="semantic-article-actions">
    {duplicateCount > 1 && <Button variant="outline" size="sm" onClick={async () => { try { await request('split', { article_id: articleId }); onChange(); } catch (e) { setError(String(e)); } }}>将此入口拆为独立文章</Button>}
    {!!items.length && <details><summary>相关资料与语义判断（{items.length}）</summary>{items.map(p => { const other = p.left.id === articleId ? p.right : p.left; return <div key={p.id}><span>{relations[p.reviewed_relation || p.relation]}</span> · <a href={other.url} target="_blank" rel="noreferrer">{other.title}</a><p>{p.decision.reason}</p></div>; })}</details>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
