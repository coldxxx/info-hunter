export type Segment = { start: number; end: number; text: string };

export type ArticleContent = {
  body: string;
  origin: string;
  status: string;
  segments: Segment[];
  media: { type?: string; url?: string };
  error?: string;
  job?: { status: string; progress?: number; stage?: string; error?: string };
};
