import { sanitizeField, scoreToConfidenceLabel, formatReasonForDisplay, containsLeakMarker } from './formatters';

export function sanitizeApiResponse(raw: any) {
  const out = { ...(raw && typeof raw === 'object' ? raw : {}) };
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

  const derivedLbl = scoreToConfidenceLabel(out.confidence_score);
  out.confidence_label = derivedLbl || sanitizeField(out.confidence_label, "");

  const reasonsIn = Array.isArray(out.reasons) ? out.reasons : [];
  out.reasons = reasonsIn.map((r: any) => formatReasonForDisplay(r));
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
