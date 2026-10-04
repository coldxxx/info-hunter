export type Source = {
  id: string;
  connection_status?: string;
  body_count?: number;
  next_at?: number;
  status: string;
  checked_at: string | null;
  success_at: string | null;
  error: string;
  last_count: number;
  effective_adapter?: string;
  followed: boolean;
  topics: {
    id: string;
    name: string;
    enabled: boolean;
    include_all: boolean;
  }[];
  include_all: boolean;
  preference: {
    score: number;
    interval_hours: number;
    reason: string;
    signals: Record<string, number>;
  };
  config: {
    user_added?: boolean;
    connection_id?: string;
    platform?: string;
    adapter: string;
    enabled: boolean;
    name: string;
    region: string;
    language?: string;
    kind: string;
    url: string;
    feed_url?: string;
    search_topic?: string;
    note: string;
  };
};

export type SourceDetail = {
  next_at?: number;
  source_id: string;
  entry_url: string;
  query: string;
  configured_adapter: string;
  effective_adapter: string;
  access: { mode: string; ready: boolean; message: string };
  capture_strategy: {
    id: string;
    name: string;
    adapter_name: string;
    description: string;
    parameters: { label: string; value: string }[];
  };
  steps: { title: string; detail: string; implementation: string }[];
  topics: {
    id: string;
    name: string;
    enabled: boolean;
    include_all: boolean;
    keywords: string[];
    exclude: string[];
    regions: string[];
    content_profile?: string;
  }[];
  schedule: {
    interval_hours: number;
    enabled: boolean;
    baseline: boolean;
    policy: Source['preference'];
  };
  stats: { archived: number; in_topic: number };
  recent: {
    id: string;
    title: string;
    url: string;
    published_at: string | null;
  }[];
  last_run: {
    status: string;
    found: number;
    added: number;
    finished_at: string | null;
    error: string;
  } | null;
};
