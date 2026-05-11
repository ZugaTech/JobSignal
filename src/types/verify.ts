/** Shape returned by POST /v1/verify after trimming (may include legacy/extra keys). */

export interface TrustSignalRow {
  name: string;
  status: string;
  detail?: string;
  source?: string;
}

export interface PipelineSignalRow {
  id: string;
  strength?: string;
  details?: string;
}

export interface SimilarJob {
  url?: string;
  title?: string;
  company?: string;
  verdict?: string;
  confidence_score?: number | null;
}

export interface ReviewSummary {
  status?: string;
  review_confidence_score?: number | null;
  overall_sentiment?: string;
  sources_checked?: number;
  sources_found?: number;
  highlights?: unknown[];
  red_flags?: string[];
  green_flags?: string[];
  plain_summary?: string;
  reddit?: Record<string, unknown> | null;
  x_twitter?: Record<string, unknown> | null;
  message?: string;
}

export type DisplaySignalRow =
  | { kind: 'pipeline'; id: string; strength: string; detail?: string }
  | { kind: 'trust'; name: string; status: string; detail?: string };

export type ReputationPanelVariant = null | 'full' | 'unavailable' | 'no_company' | 'unconfirmed';

/** Fields added or normalized by sanitizeApiResponse(). */
export interface SanitizedVerifyExtensions {
  signals: PipelineSignalRow[];
  trust_signals: TrustSignalRow[];
  display_signal_rows: DisplaySignalRow[];
  signals_summary_line: string;
  hideSignalsSection: boolean;
  reputationPanelVariant: ReputationPanelVariant;
  verdict: 'APPLY' | 'VERIFY' | 'SKIP';
  confidence_score: number;
  confidence_label: string;
  /** Verdict confidence band from the rule engine (distinct from numeric strength score). */
  verdict_confidence_band: 'high' | 'medium' | 'low' | null;
  /** Layer scores 0–100 from backend scorer. */
  company_legitimacy_score: number;
  posting_authenticity_score: number;
  freshness_score: number;
  verified_signal_count: number;
  total_signal_count: number;
  coverage_ratio: number;
  coverage_pct: number;
  staleness_flag: boolean;
  scorer_version_display: string;
  /** How complete structured evidence is (0–100), distinct from verdict confidence. */
  evidence_completeness_score: number;
  reasons: string[];
  warnings: string[];
  llm_summary: string;
  review_summary: ReviewSummary | null;
  similarJobsRequested: boolean;
  hideSimilarJobs: boolean;
  similarJobsEmptyMessage: string | null;
  request_id: string;
  data_freshness?: string;
  company_identified?: boolean;
  input_method?: string;
  cached?: boolean;
  cached_at?: string;
  cache_expires_in?: string;
  cache_complete?: boolean;
  similar_jobs: SimilarJob[] | null;
  meta?: Record<string, unknown>;
}

export type SanitizedVerifyReport = SanitizedVerifyExtensions &
  Record<string, unknown>;
