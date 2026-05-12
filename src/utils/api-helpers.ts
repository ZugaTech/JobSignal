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
  formatPipelineSignalDetail,
  formatReasonForDisplay,
  formatWarningForDisplay,
  isUnsafeUserProse,
  sanitizeField,
  sanitizeProseForUi,
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
    const name0 = sanitizeField(r.name, '');
    const name = name0 && !isUnsafeUserProse(name0) ? name0 : name0 ? 'Public check' : '';
    const status = sanitizeField(r.status, '');
    const detail0 = typeof r.detail === 'string' ? r.detail.trim() : '';
    const detail =
      detail0 && !isUnsafeUserProse(detail0) ? (detail0.length > 400 ? detail0.slice(0, 400) : detail0) : undefined;
    if (!name && !status) continue;
    out.push({
      name: name || 'Signal',
      status: status || 'Insufficient evidence',
      detail,
      source: typeof r.source === 'string' ? r.source : undefined,
    });
  }
  return out;
}

function buildDisplayRows(signals: PipelineSignalRow[], trustSignals: TrustSignalRow[]): DisplaySignalRow[] {
  const userSignals = signals.filter((s) => s.id && !INTERNAL_SIGNAL_IDS.has(s.id));
  if (userSignals.length > 0) {
    return userSignals.map((s) => {
      const raw = formatPipelineSignalDetail(s.id, typeof s.details === 'string' ? s.details : undefined);
      const detail = raw && !isUnsafeUserProse(raw) ? raw : undefined;
      return {
        kind: 'pipeline' as const,
        id: s.id,
        strength: String(s.strength ?? ''),
        detail,
      };
    });
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

  const SUMMARY_FALLBACK = 'Summary unavailable. Please try again.';
  let llm = sanitizeField(out.llm_summary, '');
  if (!llm) {
    out.llm_summary = SUMMARY_FALLBACK;
  } else {
    const cleaned = sanitizeProseForUi(llm, SUMMARY_FALLBACK, 2000);
    if (cleaned.indexOf('.') === -1) {
      out.llm_summary = SUMMARY_FALLBACK;
    } else {
      out.llm_summary = cleaned;
    }
  }

  const rs = out.review_summary;
  let reviewObj: Record<string, unknown> | null = null;
  if (rs && typeof rs === 'object' && !Array.isArray(rs)) {
    reviewObj = rs as Record<string, unknown>;
    const ps = sanitizeField(reviewObj.plain_summary, '');
    const cleanseBullet = (arr: unknown): string[] =>
      Array.isArray(arr)
        ? (arr as unknown[])
            .map((x) => sanitizeField(x, '').trim())
            .filter((x) => x.length > 0 && !isUnsafeUserProse(x))
            .slice(0, 8)
        : [];
    const rr0 = sanitizeField(reviewObj.reliability_report, '');
    const rr = rr0 && !isUnsafeUserProse(rr0) ? rr0 : '';
    if (ps) {
      const cleanedPs = sanitizeProseForUi(ps, SUMMARY_FALLBACK, 2000);
      reviewObj = {
        ...reviewObj,
        plain_summary: cleanedPs.indexOf('.') === -1 ? SUMMARY_FALLBACK : cleanedPs,
        red_flags: cleanseBullet(reviewObj.red_flags),
        green_flags: cleanseBullet(reviewObj.green_flags),
        reliability_report: rr,
      };
    } else {
      reviewObj = {
        ...reviewObj,
        red_flags: cleanseBullet(reviewObj.red_flags),
        green_flags: cleanseBullet(reviewObj.green_flags),
        reliability_report: rr,
      };
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

  if (Array.isArray(out.similar_jobs) && out.similar_jobs.length > 0) {
    out.similar_jobs = out.similar_jobs.map((job: unknown) => {
      if (!job || typeof job !== 'object') return job;
      const j = job as Record<string, unknown>;
      const title = sanitizeField(j.title, '');
      const company = sanitizeField(j.company, '');
      return {
        ...j,
        title: title && !isUnsafeUserProse(title) ? String(title).slice(0, 300) : 'Job posting',
        company: company && !isUnsafeUserProse(company) ? String(company).slice(0, 160) : '',
      };
    });
  }

  out.request_id = sanitizeField(out.request_id, '');
  out.data_freshness = sanitizeField(out.data_freshness, '');

  return out as SanitizedVerifyReport;
}
