/**
 * JobSignal UI - calls POST /v1/verify.
 * Supports: Single URL, Description, Screenshot, and Batch URLs.
 */

const $ = (id) => document.getElementById(id);

const PHASE = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  WARNING: "warning",
  ERROR: "error",
};

const MAX_URL_CHARS = 2048;
const MAX_TEXT_CHARS = 100000;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const JOB_URL_HINTS = ["job", "jobs", "career", "careers", "position", "apply", "hiring", "linkedin.com/jobs", "indeed.com", "greenhouse.io", "lever.co", "workday"];
const JOB_TEXT_HINTS = ["responsibilities", "requirements", "salary", "experience", "apply", "qualifications", "role", "benefits"];

function readInputs() {
  return {
    url: $("jobUrl").value,
    text: $("jobText").value,
    file: $("jobImage").files?.[0] ?? null,
    recommendations: $("recRecommendations").checked,
  };
}

function validateClientInputs(urlRaw, textRaw, file) {
  const url = String(urlRaw ?? "").trim();
  const text = String(textRaw ?? "").trim();
  if (!url && !text && !file) {
    return { ok: false, message: "Enter a job URL, pasted description, and/or a screenshot." };
  }
  if (file && file.size > MAX_IMAGE_BYTES) {
    return { ok: false, message: "Screenshot must be 5MB or smaller." };
  }
  if (url.length > MAX_URL_CHARS) return { ok: false, message: `URL exceeds ${MAX_URL_CHARS} characters.` };
  if (text.length > MAX_TEXT_CHARS) return { ok: false, message: `Description exceeds ${MAX_TEXT_CHARS} characters.` };
  if (url && !/^https?:\/\//i.test(url)) return { ok: false, message: "Only http(s) URLs are supported." };
  return { ok: true, message: "" };
}

function setPhase(phase) {
  const root = document.querySelector(".shell");
  root.dataset.uiPhase = phase;
  const loading = phase === PHASE.LOADING;
  $("skeletonPanel").classList.toggle("hidden", !loading);
  $("btnSpinner").classList.toggle("hidden", !loading);
  $("btnLabel").textContent = loading ? "Checking..." : "Check posting";
  $("btnRun").disabled = loading;
}

function setCacheOverlay(hit) {
  const root = document.querySelector(".shell");
  root.dataset.cache = hit ? "hit" : "miss";
  $("cacheBadge").classList.toggle("hidden", !hit);
}

function verdictStyle(verdict) {
  if (verdict === "APPLY") return { color: "#22c55e", icon: "✓" };
  if (verdict === "SKIP") return { color: "#ef4444", icon: "✕" };
  return { color: "#f59e0b", icon: "?" };
}

// ── FIX 3: Strength label mapping ───────────────────────────────────────────
const STRENGTH_LABEL = { high: "Verified", medium: "Partial", low: "Weak", none: "Inconclusive" };

function signalStrengthLabel(raw) {
  return STRENGTH_LABEL[String(raw || "").toLowerCase()] ?? String(raw || "unverified");
}

function classifySignal(signal) {
  const st = String(signal?.strength || "").toLowerCase();
  if (st === "high") return { color: "#22c55e", dot: "#22c55e" };
  if (st === "medium") return { color: "#f59e0b", dot: "#f59e0b" };
  if (st === "low") return { color: "#ef4444", dot: "#ef4444" };
  return { color: "#525252", dot: "#525252" }; // none / unverified
}

// ── FIX 3: Signal tooltips ───────────────────────────────────────────────────
const SIGNAL_HINTS = {
  careers_domain_match: "Does the job URL match the company's official domain?",
  careers_page_match: "Is this role listed on the company's own careers page?",
  company_linkedin_presence: "Does the company have a verified LinkedIn page?",
  company_registry_presence: "Is the company registered in a public business directory?",
  cross_platform_freshness: "Is this posting also appearing on other trusted platforms?",
  first_seen_estimate: "How recently was this listing first detected online?",
  posting_duplication_signal: "Is this listing copied verbatim across unrelated sites?",
  staleness_flag: "Has this posting been live for over 30 days without updates?",
  company_reputation_signal: "Are there negative reports or scam associations for this company?",
  fetch_ok: "Could we successfully load and read the job listing page?",
  domain_align: "Does the final URL redirect to the expected company domain?",
  url_canonical: "Is the job link a direct, canonical URL with no suspicious parameters?",
  recruiter_unverified: "Could we independently confirm the recruiter's identity?",
  jd_missing_fields: "Does the job description include all expected fields (salary, location, company)?",
  jd_red_flags: "Does the text contain language commonly used in fraudulent postings?",
  jd_specificity: "Is the job description specific and detailed, or suspiciously vague?",
};

// ── FIX 2: Reason/Warning code → plain English ───────────────────────────────
const CODE_MAP = {
  HARD_RED_FLAG: "High-risk patterns detected in this posting",
  INCOMPLETE_EVIDENCE: "We could not gather a full profile for this role",
  REC_SEARCH_EMPTY: "Search returned no cross-platform results to compare",
  CONFIDENCE_LOW: "Too little data to make a confident call",
  CONFIDENCE_MEDIUM: "Some signals were unclear; treat this as advisory",
  INSUFFICIENT_DATA: "Not enough information to assess this posting",
  CACHE_HIT: "Result served from a recent shared check",
  LLM_ERROR: "AI signal extraction was unavailable for this check",
  SERPER_UNVERIFIED: "Search-based signals could not be retrieved",
  FETCH_FAILED: "The job listing page could not be loaded",
};

function humanCode(code) {
  if (CODE_MAP[code]) return CODE_MAP[code];
  // fallback: strip underscores, title-case
  return code.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function summarizeForUser(report) {
  const v = report.verdict;
  if (v === "APPLY") return "Signals look strong, but still verify details before applying.";
  if (v === "SKIP") return "This posting shows enough risk patterns to skip.";
  return "Treat this as uncertain and verify on official channels.";
}

// ── FIX 1 helper: render the collapsed signal summary bar ───────────────────
function renderSignalSummary(signals, container) {
  const total = signals.length;
  let passed = 0, flagged = 0, inconclusive = 0;
  signals.forEach(s => {
    const st = String(s.strength || "").toLowerCase();
    if (st === "high" || st === "medium") passed++;
    else if (st === "low") flagged++;
    else inconclusive++;
  });

  // Summary line
  const summary = document.createElement("p");
  summary.className = "signal-summary-line";
  summary.innerHTML = `We checked <strong>${total}</strong> trust signals:` +
    `<span style="color:#22c55e;font-weight:600">${passed} passed</span>, ` +
    `<span style="color:#ef4444;font-weight:600">${flagged} flagged</span>, ` +
    `<span style="color:#525252;font-weight:600">${inconclusive} inconclusive</span>`;
  container.appendChild(summary);

  // Dot bar
  const bar = document.createElement("div");
  bar.className = "signal-dot-bar";
  signals.forEach(s => {
    const { dot } = classifySignal(s);
    const d = document.createElement("span");
    d.className = "signal-dot-mini";
    d.style.background = dot;
    d.title = `${s.label || s.id}: ${signalStrengthLabel(s.strength)}`;
    bar.appendChild(d);
  });
  container.appendChild(bar);

  // Toggle link
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "signal-toggle-btn";
  toggle.innerHTML = `<span id="signalToggleChevron" class="sig-chevron">▶</span> View detailed breakdown`;
  container.appendChild(toggle);

  // Full list (hidden by default)
  const fullList = document.createElement("ul");
  fullList.id = "signalChecklist";
  fullList.className = "signal-checklist signal-list-hidden";
  container.appendChild(fullList);

  toggle.addEventListener("click", () => {
    const hidden = fullList.classList.toggle("signal-list-hidden");
    $("signalToggleChevron").style.transform = hidden ? "" : "rotate(90deg)";
  });

  return fullList;
}

function renderReputation(summary) {
  const container = $("repContent");
  container.innerHTML = "";
  if (!summary || !summary.highlights || summary.highlights.length === 0) {
    container.innerHTML = `<p class="muted italic small">Company reputation data unavailable for this posting.</p>`;
    return;
  }

  const scoreColor = summary.review_confidence_score >= 70 ? "#22c55e" : (summary.review_confidence_score >= 40 ? "#f59e0b" : "#ef4444");
  
  const scoreHtml = `
    <div class="rep-score-wrapper">
      <div class="rep-score-badge" style="border-color: ${scoreColor}; color: ${scoreColor}">
        <span class="rep-score-num">${summary.review_confidence_score}</span>
        <span class="rep-score-label">employer score</span>
      </div>
      <div class="sentiment-badge" data-sentiment="${summary.overall_sentiment.replace(' ', '-')}">
        ${summary.overall_sentiment.toUpperCase()}
      </div>
    </div>
  `;
  container.innerHTML += scoreHtml;

  const sourcesHtml = summary.highlights.map(h => `
    <div class="rep-source-row">
      <span class="rep-platform">${h.platform}</span>
      <span class="rep-rating">${h.rating ? `★ ${h.rating}` : 'N/A'}</span>
      <span class="rep-reliability badge-${h.reliability}">${h.reliability.toUpperCase()}</span>
    </div>
  `).join("");
  container.innerHTML += `<div class="rep-sources-list">${sourcesHtml}</div>`;

  if (summary.green_flags.length > 0) {
    const greenHtml = summary.green_flags.map(f => `<div class="rep-flag green">✓ ${f}</div>`).join("");
    container.innerHTML += `<div class="rep-flags-box">${greenHtml}</div>`;
  }
  if (summary.red_flags.length > 0) {
    const redHtml = summary.red_flags.map(f => `<div class="rep-flag amber">⚠ ${f}</div>`).join("");
    container.innerHTML += `<div class="rep-flags-box">${redHtml}</div>`;
  }

  container.innerHTML += `<p class="rep-summary-text">${summary.plain_summary}</p>`;
  container.innerHTML += `<div class="muted smallest mt-2">Sources: ${summary.highlights.map(h => h.platform).join(", ")}</div>`;
}

function renderReport(report) {
  $("verdict").textContent = report.verdict;
  const style = verdictStyle(report.verdict);
  $("verdictChip").dataset.verdict = report.verdict;
  $("verdictIcon").textContent = style.icon;

  const pct = report.confidence_score || (report.confidence === "high" ? 88 : (report.confidence === "medium" ? 62 : 34));
  $("confidencePct").textContent = `${pct}%`;
  $("confidenceFill").style.width = `${pct}%`;
  $("confidence").textContent = report.confidence;

  // ── FIX 1: Replace static checklist with aggregate summary ──────────────
  const signalSection = $("signalSection");
  signalSection.innerHTML = ""; // clear previous render
  const signals = report.signals || [];
  const checklist = renderSignalSummary(signals, signalSection);

  // Populate the full hidden list
  signals.forEach((s) => {
    const state = classifySignal(s);
    const label = s.status || signalStrengthLabel(s.strength);
    const hint = SIGNAL_HINTS[s.id] || "";
    const isNone = String(s.strength || "").toLowerCase() === "none" || !s.strength;
    const badgeStyle = isNone
      ? `color:#525252; border-color:#52525266; font-style:italic`
      : `color:${state.color}; border-color:${state.color}66`;

    const li = document.createElement("li");
    li.className = "signal-item";
    li.innerHTML = `
      <div class="signal-left">
        <span class="signal-dot" style="background-color:${state.dot}"></span>
        <div class="signal-name-block">
          <span class="signal-name">${s.label || s.id}</span>
          ${hint ? `<span class="signal-hint">${hint}</span>` : ""}
        </div>
      </div>
      <span class="signal-badge" style="${badgeStyle}">${label}</span>
    `;
    checklist.appendChild(li);
  });

  // ── FIX 2: Plain-English reasons ──────────────────────────────
  $("reasonList").innerHTML = (report.reasons || []).map(r =>
    `<li>${r.message}</li>`
  ).join("");

  // ── REPUTATION PANEL ──────────────────────────────────────────
  renderReputation(report.review_summary);

  // ── FIX 2: Meaning box prominence ───────────────────────────────────────
  $("meaningBox").textContent = report.llm_summary || summarizeForUser(report);
  $("requestIdLine").textContent = report.request_id ? `Reference ID: ${report.request_id}` : "";

  const uncertain = report.verdict === "VERIFY" || report.confidence !== "high";
  $("uncertaintyStrip").classList.toggle("hidden", !uncertain);
}

function renderRecommendations(report) {
  const section = document.getElementById("recSection");
  const list = document.getElementById("recList");
  const recs = report.recommendations || [];
  if (!section || !list) return; // elements not present in this layout
  if (!recs.length) { section.classList.add("hidden"); return; }
  section.classList.remove("hidden");
  const meta = document.getElementById("recMeta");
  if (meta) meta.textContent = "Similar listings found during verification.";
  list.innerHTML = recs.map(r => `
    <article class="rec-card">
      <div class="rec-head">
        <span class="badge badge-${r.confidence_band === "HIGH" ? "high" : "medium"}">${r.confidence_band === "HIGH" ? "Strong match" : "Partial match"}</span>
        <span class="muted">${r.verdict}</span>
      </div>
      <a class="rec-url" href="${r.job_url}" target="_blank">${r.job_url.substring(0, 40)}...</a>
    </article>
  `).join("");
}

function renderIngestion(report) {
  const el = document.getElementById("ingestionNote");
  if (!el) return; // element not present in this layout
  const ing = report.ingestion;
  if (!ing) { el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  el.textContent = ing.status === "insufficient"
    ? "The screenshot was unreadable. Try pasting the URL or job description instead."
    : `Reading confidence: ${ing.extraction_confidence}`;
}

function getApiBase() {
  const host = window.location.hostname;
  return (host === "localhost" || host === "127.0.0.1") ? "http://localhost:8080" : "";
}

function activateTab(targetId) {
  document.querySelectorAll(".input-pane").forEach(p => p.classList.add("hidden"));
  $(targetId).classList.remove("hidden");
  document.querySelectorAll(".tab-chip").forEach(t => {
    const active = t.dataset.tabTarget === targetId;
    t.classList.toggle("is-active", active);
    t.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function applyPrefillState(kind) {
  const input = kind === "url" ? $("jobUrl") : $("jobText");
  const badge = kind === "url" ? $("urlClipboardBadge") : $("textClipboardBadge");
  input.classList.add("prefilled");
  badge.classList.remove("hidden");
}

function clearPrefillState(kind) {
  const input = kind === "url" ? $("jobUrl") : $("jobText");
  const badge = kind === "url" ? $("urlClipboardBadge") : $("textClipboardBadge");
  input.classList.remove("prefilled");
  badge.classList.add("hidden");
}

async function runBatchFlow(urls) {
  $("batchResult").classList.remove("hidden");
  const list = $("batchList");
  list.innerHTML = "";
  setPhase(PHASE.LOADING);
  for (const url of urls) {
    const item = document.createElement("div");
    item.className = "batch-item loading";
    item.innerHTML = `<span class="muted">${url}</span> <span class="spinner mini"></span>`;
    list.appendChild(item);
    try {
      const res = await fetch(`${getApiBase()}/v1/verify`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_url: url })
      });
      const report = await res.json();
      const style = verdictStyle(report.verdict);
      item.className = `batch-item ${report.verdict.toLowerCase()}`;
      item.innerHTML = `
        <span class="batch-verdict" style="color:${style.color}">${style.icon} ${report.verdict}</span>
        <span class="batch-url">${url}</span>
        <span class="muted">${report.confidence}</span>
      `;
    } catch {
      item.className = "batch-item error";
      item.innerHTML = `<span class="error-text">ERR</span> <span class="batch-url">${url}</span>`;
    }
  }
  setPhase(PHASE.IDLE);
}

async function runFlow() {
  $("errorPanel").classList.add("hidden");
  $("result").classList.add("hidden");
  $("batchResult").classList.add("hidden");
  
  if (!$("batchPane").classList.contains("hidden")) {
    const urls = $("batchUrls").value.split("\n").map(u => u.trim()).filter(u => u.startsWith("http"));
    if (urls.length) { await runBatchFlow(urls); return; }
  }

  const { url, text, file, recommendations } = readInputs();
  const validation = validateClientInputs(url, text, file);
  if (!validation.ok) {
    setPhase(PHASE.ERROR);
    $("errorText").textContent = validation.message;
    $("errorPanel").classList.remove("hidden");
    return;
  }

  setPhase(PHASE.LOADING);
  try {
    let res;
    if (file) {
      const fd = new FormData();
      if (url) fd.append("job_url", url);
      if (text) fd.append("job_description", text);
      fd.append("job_image", file);
      fd.append("recommendations_enabled", recommendations ? "true" : "false");
      res = await fetch(`${getApiBase()}/v1/verify`, { method: "POST", body: fd });
    } else {
      res = await fetch(`${getApiBase()}/v1/verify`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_url: url || null, job_description: text || null, recommendations_enabled: recommendations })
      });
    }
    if (!res.ok) throw new Error(await res.text());
    const report = await res.json();
    renderReport(report);
    renderIngestion(report);
    renderRecommendations(report);
    setPhase(report.verdict === "APPLY" && report.confidence === "high" ? PHASE.SUCCESS : PHASE.WARNING);
    setCacheOverlay(report.cache?.hit);
    $("result").classList.remove("hidden");
  } catch (e) {
    setPhase(PHASE.ERROR);
    $("errorText").textContent = e.message;
    $("errorPanel").classList.remove("hidden");
  } finally {
    $("btnRun").disabled = false;
  }
}

// Event Listeners
$("btnRun").addEventListener("click", runFlow);
$("btnRetry").addEventListener("click", runFlow);
$("btnBatchReset").addEventListener("click", () => { $("batchUrls").value = ""; $("batchList").innerHTML = ""; $("batchResult").classList.add("hidden"); });

document.querySelectorAll(".tab-chip").forEach(tab => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tabTarget));
});

$("jobUrl").addEventListener("input", () => clearPrefillState("url"));
$("jobText").addEventListener("input", () => clearPrefillState("text"));

// Clipboard & UI init
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => e.preventDefault());
document.querySelector(".hero").addEventListener("drop", e => {
  e.preventDefault();
  const data = e.dataTransfer.getData("text/plain");
  if (data && /^https?:\/\//i.test(data)) { $("jobUrl").value = data; activateTab("urlPane"); }
});

document.querySelector(".how-it-works-link").addEventListener("click", e => { e.preventDefault(); $("howItWorks").classList.toggle("hidden"); });

async function handleUrlParams() {
  const p = new URLSearchParams(window.location.search);
  if (p.get("job_url")) { $("jobUrl").value = p.get("job_url"); activateTab("urlPane"); await runFlow(); }
}
handleUrlParams();
