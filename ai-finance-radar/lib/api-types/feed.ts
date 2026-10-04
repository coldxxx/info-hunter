export type WatchTopic = {
  id: string;
  name: string;
  description: string;
  keywords: string[];
  exclude: string[];
  regions: string[];
  enabled: boolean;
  news_search: boolean;
  content_profile?: 'standard' | 'developer';
  article_count: number;
  source_count: number;
};

export type Translation = {
  status: string;
  title: string;
  excerpt: string;
  error: string;
};

export type FeedArticle = {
  content_status?: string;
  media?: { type?: string };
  duplicate_count?: number;
  duplicates?: FeedArticle[];
  match_reason?: string;
  engineering_category?: string;
  id: string;
  title: string;
  url: string;
  excerpt: string;
  publisher: string;
  region: string;
  language: string;
  kind: string;
  topics: string[];
  published_at: string | null;
  collected_at: string;
  source_id: string;
  source_name?: string;
  starred: number;
  note: string;
  review: string;
};

export type CollectorStatus = {
  count: number;
  busy: boolean;
  last_run: { finished_at: string | null } | null;
};
