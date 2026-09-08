/**
 * The shapes the backend returns, mirrored from backend/src/rushes/models.py.
 *
 * Kept hand-written rather than generated: it is one screen of types, and the
 * comments are where the licensing rules live for anyone touching the UI.
 */

export type SourceId = "archive" | "youtube" | "public_domain" | "stock";

export interface SearchHit {
  id: string;
  source: SourceId;
  title: string;
  description: string;
  thumbnail_url: string | null;
  /** The source's own page. Always where we send the viewer for external hits. */
  page_url: string | null;
  /** Playable media. Only ever set for clips we own and host ourselves. */
  clip_url: string | null;
  duration_seconds: number | null;
  license: string;
  attribution: string | null;
  tags: string[];
  score: number;
  raw_score: number | null;
  /** "why this matched" — either Gemini's line or deterministic keyword overlap. */
  match_reason: string;
  hosted_by_us: boolean;
}

export interface SourceReport {
  source: SourceId;
  count: number;
  duration_ms: number;
  ok: boolean;
  note: string;
}

export interface SearchPlan {
  archive_query: string;
  web_query: string;
  keywords: string[];
  setting: string;
  mood: string;
  shot_type: string;
  subjects: string[];
  sources: string[];
}

export interface SearchResponse {
  query: string;
  plan: SearchPlan;
  results: SearchHit[];
  sources: SourceReport[];
  total_ms: number;
  warnings: string[];
}

export interface StatusResponse {
  version: string;
  clickhouse: {
    configured: boolean;
    table: string;
    via: string;
    server?: Record<string, unknown>;
    clips?: number;
    mcp_running?: boolean;
    error?: string;
  };
  gemini: {
    configured: boolean;
    vertex_ai: boolean;
    model: string;
    embed_model: string;
    embedding_dim: number;
  };
  sources: Record<SourceId, boolean>;
  ranking: { strategy: string; result_limit: number };
}

/**
 * Presentation only, and the colour is load-bearing: tungsten means the clip is
 * the editor's own and plays here, print teal means it belongs to someone else
 * and we only ever link to it. `site` is the place a viewer lands if they click.
 */
export const SOURCE_META: Record<
  SourceId,
  { label: string; site: string; blurb: string; stamp: string }
> = {
  archive: {
    label: "Archive",
    site: "your archive",
    blurb: "Your own footage, matched by meaning in ClickHouse",
    stamp: "text-tungsten",
  },
  youtube: {
    label: "YouTube",
    site: "YouTube",
    blurb: "A thumbnail and a link out, never rehosted",
    stamp: "text-print-teal",
  },
  public_domain: {
    label: "Public domain",
    site: "the Internet Archive",
    blurb: "The Internet Archive, with rights to check on the source page",
    stamp: "text-print-teal",
  },
  stock: {
    label: "Stock",
    site: "Pexels",
    blurb: "A Pexels preview, downloaded from Pexels itself",
    stamp: "text-print-teal",
  },
};

export const SOURCE_ORDER: SourceId[] = [
  "archive",
  "youtube",
  "public_domain",
  "stock",
];

/** 78 -> "1:18". Null durations are common on archive.org and are just hidden. */
export function formatDuration(seconds: number | null): string | null {
  if (!seconds || seconds < 1) return null;
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(secs)}`
    : `${minutes}:${pad(secs)}`;
}
