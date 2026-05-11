import { SIGNAL_LABEL_MAP, STATUS_LABEL_MAP, REASON_MAP, LEAK_MARKERS, COPY_REWRITE_MAP, JD_SPECIFICITY_DETAIL_MAP } from './constants';

export function formatPipelineSignalDetail(signalId: string, detail: string | undefined): string | undefined {
  if (!detail) return undefined;
  const d = detail.trim();
  if (signalId === 'jd_specificity') {
    const low = d.toLowerCase();
    for (const [k, v] of Object.entries(JD_SPECIFICITY_DETAIL_MAP)) {
      if (low === k.toLowerCase() || low.startsWith(k.toLowerCase())) return v;
    }
  }
  return d;
}

/** Strip engineering-only fragments from evidence detail shown in primary UI. */
const INTERNAL_DETAIL_HINT = /specificity=|registrable|fingerprint|bytes\s+fetched|scorer\s*v|pipeline\s*v|canonical\s+domain\s+hash/i;

export function sanitizeEvidenceDetailForDisplay(
  signalId: string | undefined,
  detail: string | undefined,
): string | undefined {
  const formatted = formatPipelineSignalDetail(signalId || '', detail);
  if (!formatted) return undefined;
  if (INTERNAL_DETAIL_HINT.test(formatted)) return undefined;
  return formatted;
}

export function getSignalLabel(key: string): string {
  const k = String(key ?? "").trim();
  if (!k) return "Signal";
  if (SIGNAL_LABEL_MAP[k]) return SIGNAL_LABEL_MAP[k];
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function getStatusLabel(status: string): string {
  const s = String(status ?? "").trim().toLowerCase();
  if (!s) return "Insufficient evidence";
  if (STATUS_LABEL_MAP[s]) return STATUS_LABEL_MAP[s];
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function getReasonLabel(code: string): string {
  const c = String(code ?? "").trim();
  if (REASON_MAP[c]) return REASON_MAP[c];
  return c.replace(/_/g, " ").replace(/\b\w/g, (c2) => c2.toUpperCase()) + ".";
}

/** Product-facing confidence tier: avoids model-y "moderate/low" wording. */
export function scoreToConfidenceLabel(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(Number(score))) return "";
  const n = Math.max(0, Math.min(100, Number(score)));
  if (n <= 0) return "Limited confidence";
  if (n < 34) return "Limited confidence";
  if (n < 67) return "Mixed confidence";
  return "Strong confidence";
}

export function sanitizeField(value: any, fallback: string): string {
  if (value === undefined || value === null) return fallback;
  if (typeof value === "number" && Number.isNaN(value)) return fallback;
  const s = String(value).trim();
  const low = s.toLowerCase();
  if (!s || low === "none" || low === "null" || low === "undefined" || low === "nan") return fallback;
  return s;
}

export function containsLeakMarker(text: string): boolean {
  const t = String(text || "").toLowerCase();
  if (LEAK_MARKERS.some((m) => t.includes(m))) return true;
  if (
    t.includes('fetch_ok') ||
    t.includes('domain_align') ||
    t.includes('careers_page_match') ||
    t.includes('careers_domain_match') ||
    t.includes('company_reputation_signal')
  ) {
    return true;
  }
  if (/\b[a-z]+_[a-z0-9_]+\b/.test(t) && (t.includes('signal') || t.includes('signals:'))) return true;
  if (/\b(t1|t2|t3)\b/.test(t)) return true;
  if (/\b(gate|gates)\b/.test(t)) return true;
  if (/\btier\b/.test(t)) return true;
  if (t.includes("apply gate") || t.includes("medium+ with") || t.includes("high with support")) return true;
  return false;
}

export function formatReasonForDisplay(entry: any): string {
  if (typeof entry === "string") {
    const t = sanitizeField(entry, "");
    if (!t) return "Not enough verified information was available.";
    if (/^[A-Z][A-Z0-9_]+$/.test(t.trim())) return getReasonLabel(t.trim());
    return t;
  }
  const msg = sanitizeField(entry?.message, "");
  if (msg) return msg;
  const code = sanitizeField(entry?.code, "");
  if (code) return getReasonLabel(code);
  return "Not enough verified information was available.";
}

/** Warnings use the same { code, message } contract as reasons. */
export const formatWarningForDisplay = formatReasonForDisplay;

/** Normalize typographic dashes in user-facing copy (API strings may still use them). */
export function normalizeDisplayDashes(text: string): string {
  if (!text) return "";
  return text.replace(/\u2014/g, " - ").replace(/\u2013/g, "-");
}

export function rewriteMicrocopy(text: string): string {
  if (!text) return "";
  let out = normalizeDisplayDashes(text);
  for (const [old, replacement] of Object.entries(COPY_REWRITE_MAP)) {
    out = out.replace(old, replacement);
  }
  return normalizeDisplayDashes(out);
}

/** Drop bullet reasons that mostly repeat the narrative summary (VERIFY copy bloat). */
export function filterReasonsAgainstSummary(summary: string, reasons: string[]): string[] {
  const s = String(summary || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
  if (!s || !reasons.length) return reasons;
  return reasons.filter((r) => {
    const t = String(r || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
    if (!t || t.length < 24) return true;
    if (s.includes(t)) return false;
    if (t.length >= 40 && s.slice(0, Math.min(120, s.length)).includes(t.slice(0, 48))) return false;
    return true;
  });
}

/** Reputation panel body: strip instruction-echo and model monologue before display. */
export function sanitizeReputationPlainSummary(text: string | undefined | null): string {
  const raw = String(text || "").trim();
  if (!raw) return "";
  if (containsLeakMarker(raw)) {
    return "Public employer reviews did not surface clearly enough for a clean summary here.";
  }
  return rewriteMicrocopy(raw);
}

export function formatCachedAgo(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "Verified earlier";
    const days = Math.floor((Date.now() - t) / 86400000);
    if (days <= 0) return "Verified today";
    if (days === 1) return "Verified 1 day ago";
    return `Verified ${days} days ago`;
  } catch {
    return "Verified earlier";
  }
}

/** Map pipeline strength or API trust `status` text to a dot color bucket. */
export function signalStrengthDotClass(raw: string | undefined | null): 'green' | 'amber' | 'red' | 'neutral' {
  const s = String(raw ?? "")
    .trim()
    .toLowerCase();
  if (!s) return "neutral";
  if (s === "high" || s === "pass" || s.includes("strong") || s === "verified") return "green";
  if (s === "medium" || s.includes("partial")) return "amber";
  if (s === "fail" || s === "danger" || s.includes("flag")) return "red";
  if (s === "low" || s.includes("weak")) return "amber";
  return "neutral";
}

export function isSafeHttpUrl(href: string | undefined | null): boolean {
  if (!href || typeof href !== "string") return false;
  try {
    const u = new URL(href.trim());
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export function buildSignalsSummaryLine(
  rows: Array<{ kind: 'pipeline'; strength: string } | { kind: 'trust'; status: string }>,
): string {
  if (!rows.length) return 'No public checks were returned for this analysis.';
  let strong = 0;
  let flagged = 0;
  let inconclusive = 0;
  for (const row of rows) {
    const bucket = signalStrengthDotClass(row.kind === 'pipeline' ? row.strength : row.status);
    if (bucket === 'green') strong += 1;
    else if (bucket === 'red') flagged += 1;
    else inconclusive += 1;
  }
  const bits: string[] = [];
  if (strong) bits.push(`${strong} looked solid`);
  if (flagged) bits.push(`${flagged} raised concerns or conflicts`);
  if (inconclusive) bits.push(`${inconclusive} were unclear from public data`);
  return `Quick read: ${bits.join('; ')}.`;
}
