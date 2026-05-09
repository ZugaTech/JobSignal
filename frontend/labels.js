// JobSignal UI labels: human-readable signal/status strings only (loaded before app.js).
// Static tooling tokens: ingestionNote recRecommendations recSection

const SIGNAL_LABEL_MAP = {
  careers_domain_match: "Official domain match",
  careers_page_match: "Found on careers page",
  company_linkedin_presence: "Verified company presence",
  company_registry_presence: "Company registry check",
  cross_platform_freshness: "Cross-platform freshness",
  first_seen_estimate: "First seen online",
  posting_duplication_signal: "Duplicate posting check",
  staleness_flag: "Posting age check",
  company_reputation_signal: "Reputation scan",
  live_page_fetch: "Job page accessibility",
  domain_match_after_redirect: "Website consistency check",
  posting_url: "Posting source",
  fetch_ok: "Job page accessibility",
  domain_align: "Website consistency check",
  url_canonical: "Posting source",
  input_text_only: "Text-only input",
};

const STATUS_LABEL_MAP = {
  none: "Not checked",
  null: "Not checked",
  low: "Weak signal",
  medium: "Partial signal",
  high: "Confirmed",
  pass: "Passed",
  fail: "Flagged",
  unknown: "Inconclusive",
  unverified: "Unverified",
};

const REASON_MAP = {
  HARD_RED_FLAG: "High-risk patterns were detected in this posting.",
  INCOMPLETE_EVIDENCE: "We could not gather a complete profile for this role.",
  INSUFFICIENT_DATA: "Not enough information was available to assess this posting.",
  REC_SEARCH_EMPTY: "No cross-platform results were found to compare against.",
  CONFIDENCE_LOW: "Evidence was too limited for a confident verdict.",
  CONFIDENCE_MEDIUM: "Some signals were unclear. Treat this as a guide, not a guarantee.",
};

const LEAK_MARKERS = [
  "the user wants",
  "key constraints",
  "data provided",
  "wait, there's",
  "constraints:",
  "instructions:",
  "system prompt",
  "you are a",
  "as an ai",
  "here is the",
  "given the following",
  "based on the following evidence",
  "write a",
  "generate a",
];

function getSignalLabel(key) {
  const k = String(key ?? "").trim();
  if (!k) return "Signal";
  if (SIGNAL_LABEL_MAP[k]) return SIGNAL_LABEL_MAP[k];
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function getStatusLabel(status) {
  const s = String(status ?? "").trim().toLowerCase();
  if (!s) return "Not checked";
  if (STATUS_LABEL_MAP[s]) return STATUS_LABEL_MAP[s];
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function getReasonLabel(code) {
  const c = String(code ?? "").trim();
  if (REASON_MAP[c]) return REASON_MAP[c];
  return c.replace(/_/g, " ").replace(/\b\w/g, (c2) => c2.toUpperCase()) + ".";
}

function sanitizeField(value, fallback) {
  if (value === undefined || value === null) return fallback;
  if (typeof value === "number" && Number.isNaN(value)) return fallback;
  const s = String(value).trim();
  const low = s.toLowerCase();
  if (!s || low === "none" || low === "null" || low === "undefined" || low === "nan") return fallback;
  return s;
}

function containsLeakMarker(text) {
  const t = String(text || "").toLowerCase();
  return LEAK_MARKERS.some((m) => t.includes(m));
}

function isUncheckedSignalStrength(strength) {
  const s = String(strength ?? "").trim().toLowerCase();
  return !s || s === "none" || s === "null";
}

function formatReasonForDisplay(entry) {
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

function sanitizeApiResponse(raw) {
  const out = { ...(raw && typeof raw === "object" ? raw : {}) };
  const signals = Array.isArray(out.signals) ? out.signals.filter(Boolean) : [];
  out.signals = signals;
  out.hideSignalsSection = signals.length === 0;

  const v0 = sanitizeField(out.verdict, "VERIFY").toUpperCase();
  out.verdict = ["APPLY", "VERIFY", "SKIP"].includes(v0) ? v0 : "VERIFY";

  if (out.confidence_score === undefined || out.confidence_score === null || Number.isNaN(Number(out.confidence_score))) {
    out.confidence_score = null;
  } else {
    out.confidence_score = Math.max(0, Math.min(100, Number(out.confidence_score)));
  }

  out.confidence_label = sanitizeField(out.confidence_label, "");

  const reasonsIn = Array.isArray(out.reasons) ? out.reasons : [];
  out.reasons = reasonsIn.map((r) => formatReasonForDisplay(r));
  if (!out.reasons.length) {
    out.reasons = ["Not enough verified information was available."];
  }

  let llm = sanitizeField(out.llm_summary, "");
  if (!llm || llm.indexOf(".") === -1 || containsLeakMarker(llm)) {
    out.llm_summary = "Summary unavailable. Please try again.";
  } else {
    out.llm_summary = llm.slice(0, 2000);
  }

  const rs = out.review_summary;
  let hasRep = false;
  if (rs && typeof rs === "object") {
    const st = String(rs.status || "").toLowerCase();
    if (st !== "unavailable" && st !== "company_not_identified") {
      const ps = sanitizeField(rs.plain_summary, "");
      if (ps) {
        hasRep = true;
        if (containsLeakMarker(ps)) {
          out.review_summary = { ...rs, plain_summary: "Summary unavailable. Please try again." };
        }
      }
    }
  }
  out.hideReputationPanel = !hasRep;

  const sj = out.similar_jobs;
  const meta = out.meta && typeof out.meta === "object" ? out.meta : {};
  const requested = !!meta.similar_jobs_requested;
  out.similarJobsRequested = requested;
  if (sj == null) {
    out.hideSimilarJobs = true;
    out.similarJobsEmptyMessage = null;
  } else if (Array.isArray(sj) && sj.length === 0 && requested) {
    out.hideSimilarJobs = false;
    out.similarJobsEmptyMessage =
      "No similar postings met the high-confidence bar for this check. Try again later or paste a fuller job description.";
  } else if (Array.isArray(sj) && sj.length === 0 && !requested) {
    out.hideSimilarJobs = true;
    out.similarJobsEmptyMessage = null;
  } else {
    out.hideSimilarJobs = false;
    out.similarJobsEmptyMessage = null;
  }

  out.request_id = sanitizeField(out.request_id, "");

  return out;
}
