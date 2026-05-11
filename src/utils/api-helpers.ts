import type {
  DisplaySignalRow,
  PipelineSignalRow,
  ReputationPanelVariant,
  ReviewSummary,
  SanitizedVerifyReport,
  TrustSignalRow,
} from '../types/verify';
import {
  buildSignalsSummaryLine,
  containsLeakMarker,
  formatPipelineSignalDetail,
  formatReasonForDisplay,
  formatWarningForDisplay,
  sanitizeField,
  scoreToConfidenceLabel,
} from './formatters';

const INTERNAL_SIGNAL_IDS = new Set(['url_canonical', 'input_text_only']);

function clampScore0to100(n: unknown): number {
  const x = Number(n);
  if (Number.isNaN(x)) return 0;
  return Math.max(0, Math.min(100, Math.round(x)));
}

function clampNonNegInt(n: unknown): number {
  const x = Number(n);
  if (Number.isNaN(x) || x < 0) return 0;
  return Math.round(x);
}

function normalizePipelineSignals(raw: unknown): PipelineSignalRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((s): s is PipelineSignalRow => Boolean(s) && typeof s === 'object' && typeof (s as PipelineSignalRow).id === 'string');
}

function normalizeTrustSignals(raw: unknown): TrustSignalRow[] {
  if (!Array.isArray(raw)) return [];
  const out: TrustSignalRow[] = [];
  for (const row of raw) {
    if (!row || typeof row !== 'object') continue;
    const r = row as Record<string, unknown>;
    const name = sanitizeField(r.name, '');
    const status = sanitizeField(r.status, '');
    if (!name && !status) continue;
    out.push({
      name: name || 'Signal',
      status: status || 'Insufficient evidence',
      detail: typeof r.detail === 'string' ? r.detail : undefined,
      source: typeof r.source === 'string' ? r.source : undefined,
    });
  }
  return out;
}

function buildDisplayRows(signals: PipelineSignalRow[], trustSignals: TrustSignalRow[]): DisplaySignalRow[] {
  const userSignals = signals.filter((s) => s.id && !INTERNAL_SIGNAL_IDS.has(s.id));
  if (userSignals.length > 0) {
    return userSignals.map((s) => ({
      kind: 'pipeline' as const,
      id: s.id,
      strength: String(s.strength ?? ''),
      detail: formatPipelineSignalDetail(s.id, typeof s.details === 'string' ? s.details : undefined),
    }));
  }
  return trustSignals.map((t) => ({
    kind: 'trust' as const,
    name: t.name,
    status: t.status,
    detail: t.detail,
  }));
}

function resolveReputationVariant(rs: Record<string, unknown> | null): ReputationPanelVariant {
  if (!rs || typeof rs !== 'object') return null;
  const st = String(rs.status ?? '').toLowerCase();
  if (st === 'unavailable') return 'unavailable';
  if (st === 'employer_unconfirmed') return 'unconfirmed';
  if (st === 'company_not_identified') return 'no_company';

  const ps = sanitizeField(rs.plain_summary, '');
  const reddit = rs.reddit as Record<string, unknown> | undefined | null;
  const xt = rs.x_twitter as Record<string, unknown> | undefined | null;
  const hasSocial = Boolean(reddit?.found) || Boolean(xt?.found);
  const reds = Array.isArray(rs.red_flags) ? rs.red_flags.length : 0;
  const greens = Array.isArray(rs.green_flags) ? rs.green_flags.length : 0;
  const score = rs.review_confidence_score;
  const hasScore = typeof score === 'number' && !Number.isNaN(score);

  if (ps || hasSocial || reds + greens > 0 || hasScore) return 'full';
  return null;
}

export function sanitizeApiResponse(raw: unknown): SanitizedVerifyReport {
  const out = { ...(raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}) };

  const cacheObj = out.cache && typeof out.cache === 'object' ? (out.cache as Record<string, unknown>) : null;
  out.cached = Boolean(out.cached) || Boolean(cacheObj?.hit);

  const signals = normalizePipelineSignals(out.signals);
  out.signals = signals;

  const trustSignals = normalizeTrustSignals(out.trust_signals);
  out.trust_signals = trustSignals;

  const displayRows = buildDisplayRows(signals, trustSignals);
  out.display_signal_rows = displayRows;
  out.signals_summary_line = buildSignalsSummaryLine(
    displayRows.map((r) =>
      r.kind === 'pipeline'
        ? { kind: 'pipeline', strength: r.strength }
        : { kind: 'trust', status: r.status },
    ),
  );
  out.hideSignalsSection = displayRows.length === 0;

  const v0 = sanitizeField(out.verdict, 'VERIFY').toUpperCase();
  out.verdict = ['APPLY', 'VERIFY', 'SKIP'].includes(v0) ? v0 : 'VERIFY';

  let scoreNum: number;
  if (out.confidence_score === undefined || out.confidence_score === null || Number.isNaN(Number(out.confidence_score))) {
    scoreNum = 0;
  } else {
    scoreNum = Math.max(0, Math.min(100, Number(out.confidence_score)));
  }
  out.confidence_score = scoreNum;

  const derivedLbl = scoreToConfidenceLabel(scoreNum);
  out.confidence_label = derivedLbl || sanitizeField(out.confidence_label, '');

  const bandRaw =
    typeof out.confidence === 'string' ? out.confidence.trim().toLowerCase() : '';
  out.verdict_confidence_band =
    bandRaw === 'high' || bandRaw === 'medium' || bandRaw === 'low' ? bandRaw : null;

  out.company_legitimacy_score = clampScore0to100(out.company_legitimacy_score);
  out.posting_authenticity_score = clampScore0to100(out.posting_authenticity_score);
  out.freshness_score = clampScore0to100(out.freshness_score);
  out.verified_signal_count = clampNonNegInt(out.verified_signal_count);
  out.total_signal_count = clampNonNegInt(out.total_signal_count);
  const cr = Number(out.coverage_ratio);
  out.coverage_ratio = Number.isFinite(cr) ? cr : 0;
  out.coverage_pct = Number.isFinite(cr) ? Math.round(cr * 100) : 0;
  out.staleness_flag = Boolean(out.staleness_flag);

  const metaObj = out.meta && typeof out.meta === 'object' ? (out.meta as Record<string, unknown>) : {};
  out.scorer_version_display =
    typeof metaObj.scorer_version === 'string' ? metaObj.scorer_version.trim() : '';

  const ecsRaw = Number((out as Record<string, unknown>).evidence_completeness_score);
  out.evidence_completeness_score = Number.isFinite(ecsRaw) ? clampScore0to100(ecsRaw) : 0;

  const reasonsIn = Array.isArray(out.reasons) ? out.reasons : [];
  const reasonLines = reasonsIn.map((r: unknown) => formatReasonForDisplay(r));
  const seenReason = new Set<string>();
  const reasonsDeduped: string[] = [];
  for (const line of reasonLines) {
    const k = line.trim().toLowerCase();
    if (!k || seenReason.has(k)) continue;
    seenReason.add(k);
    reasonsDeduped.push(line);
  }
  out.reasons = reasonsDeduped.length ? reasonsDeduped : ['Not enough verified information was available.'];

  const warningsIn = Array.isArray(out.warnings) ? out.warnings : [];
  const warnLines = warningsIn.map((w: unknown) => formatWarningForDisplay(w));
  const seenWarn = new Set<string>();
  const warningsDeduped: string[] = [];
  for (const line of warnLines) {
    const k = line.trim().toLowerCase();
    if (!k || seenWarn.has(k)) continue;
    seenWarn.add(k);
    warningsDeduped.push(line);
  }
  out.warnings = warningsDeduped;

  let llm = sanitizeField(out.llm_summary, '');
  if (!llm || llm.indexOf('.') === -1 || containsLeakMarker(llm)) {
    out.llm_summary = 'Summary unavailable. Please try again.';
  } else {
    out.llm_summary = llm.slice(0, 2000);
  }

  const rs = out.review_summary;
  let reviewObj: Record<string, unknown> | null = null;
  if (rs && typeof rs === 'object' && !Array.isArray(rs)) {
    reviewObj = rs as Record<string, unknown>;
    const ps = sanitizeField(reviewObj.plain_summary, '');
    if (ps && containsLeakMarker(ps)) {
      reviewObj = { ...reviewObj, plain_summary: 'Summary unavailable. Please try again.' };
    }
    out.review_summary = reviewObj as ReviewSummary;
  } else {
    out.review_summary = null;
    reviewObj = null;
  }

  out.reputationPanelVariant = resolveReputationVariant(reviewObj);

  const sj = out.similar_jobs;
  const meta = out.meta && typeof out.meta === 'object' ? (out.meta as Record<string, unknown>) : {};
  const requested = Boolean(meta.similar_jobs_requested);
  out.similarJobsRequested = requested;

  if (sj == null) {
    out.hideSimilarJobs = true;
    out.similarJobsEmptyMessage = null;
  } else if (Array.isArray(sj) && sj.length === 0 && requested) {
    out.hideSimilarJobs = false;
    out.similarJobsEmptyMessage =
      'No similar postings met the high-confidence bar for this check. Try again later or paste a fuller job description.';
  } else if (Array.isArray(sj) && sj.length === 0 && !requested) {
    out.hideSimilarJobs = true;
    out.similarJobsEmptyMessage = null;
  } else {
    out.hideSimilarJobs = false;
    out.similarJobsEmptyMessage = null;
  }

  out.request_id = sanitizeField(out.request_id, '');
  out.data_freshness = sanitizeField(out.data_freshness, '');

  return out as SanitizedVerifyReport;
}
