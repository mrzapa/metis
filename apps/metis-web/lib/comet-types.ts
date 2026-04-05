/** Types for the comet-news constellation feature. */

export type CometDecision = "drift" | "approach" | "absorb";
export type CometPhase =
  | "entering"
  | "drifting"
  | "approaching"
  | "absorbing"
  | "fading"
  | "absorbed"
  | "dismissed";
export type CometSourceChannel = "rss" | "hackernews" | "reddit";

export interface CometNewsItem {
  item_id: string;
  title: string;
  summary: string;
  url: string;
  source_channel: CometSourceChannel | string;
  published_at: number;
}

export interface CometEvent {
  comet_id: string;
  news_item: CometNewsItem;
  faculty_id: string;
  secondary_faculty_id: string;
  classification_score: number;
  decision: CometDecision;
  relevance_score: number;
  gap_score: number;
  phase: CometPhase;
  created_at: number;
  decided_at: number;
  absorbed_at: number;
}

/** Client-side rendering state for an active comet on the canvas. */
export interface CometData {
  comet_id: string;
  /** Screen-space position */
  x: number;
  y: number;
  /** Velocity in screen-space pixels/frame */
  vx: number;
  vy: number;
  /** Tail history (last N screen positions) */
  tailHistory: Array<{ x: number; y: number }>;
  /** Faculty RGB color tuple */
  color: [number, number, number];
  /** Faculty the comet is classified into */
  facultyId: string;
  /** Target faculty screen position (for approach / absorb) */
  targetX: number;
  targetY: number;
  /** Current visual phase */
  phase: CometPhase;
  /** Timestamp when phase started */
  phaseStartedAt: number;
  /** Overall comet size (head radius) */
  size: number;
  /** Opacity 0-1 */
  opacity: number;
  /** Readable title for tooltip */
  title: string;
  /** News summary */
  summary: string;
  /** Source URL */
  url: string;
  /** Decision from the engine */
  decision: CometDecision;
  /** Relevance score 0-1 */
  relevanceScore: number;
}

/** Response from GET /v1/comets/sources */
export interface CometSourcesResponse {
  enabled: boolean;
  sources: CometSourceChannel[];
  available_sources: CometSourceChannel[];
  rss_feeds: string[];
  reddit_subs: string[];
  poll_interval_seconds: number;
  max_active: number;
}
