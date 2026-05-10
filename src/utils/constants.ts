export const SIGNAL_LABEL_MAP: Record<string, string> = {
  careers_domain_match: "Official domain match",
  careers_page_match: "Found on careers page",
  company_linkedin_presence: "Verified company presence",
  company_registry_presence: "Company registry check",
  cross_platform_freshness: "Cross-platform freshness",
  first_seen_estimate: "First seen online",
  posting_duplication_signal: "Duplicate posting check",
  staleness_flag: "Posting age check",
  company_reputation_signal: "Reputation scan",
  jd_specificity: "Job description quality",
  jd_red_flags: "Job description risk patterns",
  jd_missing_fields: "Missing job details",
  live_page_fetch: "Job page accessibility",
  domain_match_after_redirect: "Website consistency check",
  posting_url: "Posting source",
  fetch_ok: "Job page accessibility",
  domain_align: "Website consistency check",
  url_canonical: "Posting source",
  input_text_only: "Text-only input",
};

/** Maps jd_specificity backend detail tokens to UI copy. */
export const JD_SPECIFICITY_DETAIL_MAP: Record<string, string> = {
  "specificity=low": "Low detail",
  "specificity=medium": "Moderate detail",
  "specificity=high": "High detail",
};

export const STATUS_LABEL_MAP: Record<string, string> = {
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

export const REASON_MAP: Record<string, string> = {
  HARD_RED_FLAG: "High-risk patterns were detected in this posting.",
  INCOMPLETE_EVIDENCE: "We could not gather a complete profile for this role.",
  INSUFFICIENT_DATA: "Not enough information was available to assess this posting.",
  REC_SEARCH_EMPTY: "No cross-platform results were found to compare against.",
  CONFIDENCE_LOW: "Evidence was too limited for a confident verdict.",
  CONFIDENCE_MEDIUM: "Some signals were unclear. Treat this as a guide, not a guarantee.",
};

export const LEAK_MARKERS = [
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

export const COPY_REWRITE_MAP: Record<string, string> = {
  "Limited certainty — verify on the employer's official careers page.": "We found mixed signals. Verify directly before applying.",
  "Primary page evidence insufficient for a confident recommendation.": "We could not fully confirm this listing through official sources.",
  "Live page fetch successful.": "The job page is accessible and active.",
  "Treat this output as advisory; verify on official channels when unsure.": "Use this as a guide. Always verify on the company's official site.",
  "High-risk signals were detected, so this posting is not recommended.": "This posting raised serious concerns. We recommend skipping it.",
  "Evidence collection was partial. Unable to build a complete profile for this role.": "We could only verify part of this posting. Proceed with caution.",
  "Search returned no usable URLs for the built queries.": "No matching results were found across public job platforms.",
  "This posting shows enough risk patterns to skip.": "Multiple red flags found. This one is not worth your time.",
  "This posting appears legitimate based on available signals.": "This looks like a real opportunity. Signals check out.",
};
