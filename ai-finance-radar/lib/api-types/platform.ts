export type PlatformConnection = {
  id: string;
  platform: string;
  status: string;
  message: string;
  used_today: number;
  daily_limit: number;
  last_success: number;
  retry_at: number;
};

export type PlatformConnections = {
  available: boolean;
  error?: string;
  items: PlatformConnection[];
  storage?: { bytes: number; free_bytes: number };
  reddit?: { approval_confirmed: boolean };
};

export type Podcast = {
  name: string;
  author: string;
  feed_url: string;
  url: string;
  updated_at: string;
  reason: string;
};
