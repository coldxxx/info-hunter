export type SemanticConfig = {
  enabled: boolean; mode: 'review' | 'auto'; embedding_model: string; judge_model: string;
  embedding_url: string; judge_url: string; candidate_threshold: number; auto_threshold: number;
  top_k: number; window_days: number; daily_pair_limit: number;
};

export type SemanticArticle = { id: string; title: string; url: string; excerpt: string; publisher: string; language: string; published_at: string | null; kind: string; review_text: string; has_full_text: boolean; truncated: boolean };

export type SemanticPair = {
  id: string; left: SemanticArticle; right: SemanticArticle; similarity: number; relation: string; model: string;
  status: string; reviewed_relation: string | null; review_note: string | null; updated_at: number;
  decision: { confidence: number; reason: string; evidence_a: string; evidence_b: string;
    guards: string[]; text_scope: string; same_event: boolean; new_information: boolean; contradiction: boolean };
};

export type SemanticStatus = {
  config: SemanticConfig; jobs: Record<string, number>; relations: Record<string, number>; awaiting: number;
  reviewed: number; collapsed: number; last_error: string;
  auto_gate: { ready: boolean; requirement: string; report: { count?: number; precision?: number; recall?: number } };
  budget: { used: number; limit: number; resumes_at: number | null };
  index: { total: number; indexed: number };
  events: { id: number; action: string; target: string; created_at: number; undone_by: number | null }[];
};
