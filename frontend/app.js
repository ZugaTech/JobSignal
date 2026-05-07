/**
 * JobSignal UI — calls POST /v1/verify (see window.JOBSIGNAL_API_BASE).
 * Phases: idle, loading, success, warning, error; cache hit badge on result when report.cache.hit.
 */

const $ = (id) => document.getElementById(id);

const PHASE = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  WARNING: "warning",
  ERROR: "error",
};

// Mirrors backend/core/inputs.py limits for early client-side rejection.
const MAX_URL_CHARS = 2048;
const MAX_TEXT_CHARS = 100000;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

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
  if (url.includes("\u0000") || text.includes("\u0000")) {
    return { ok: false, message: "Input contains disallowed NUL bytes." };
  }
  if (url.length > MAX_URL_CHARS) {
    return { ok: false, message: `URL exceeds ${MAX_URL_CHARS} characters.` };
  }
  if (text.length > MAX_TEXT_CHARS) {
    return { ok: false, message: `Description exceeds ${MAX_TEXT_CHARS} characters.` };
  }
  if (url && !/^https?:\/\//i.test(url)) {
    return { ok: false, message: "Only http(s) URLs are supported." };
  }
  try {
    // Basic host presence check (matches server-side intent).
    if (url) {
      const u = new URL(url);
      if (!u.hostname) return { ok: false, message: "URL must include a host." };
    }
  } catch {
    return { ok: false, message: "URL is not valid." };
  }
  return { ok: true, message: "" };
}

function setPhase(phase) {
  const root = document.querySelector(".shell");
  root.dataset.uiPhase = phase;
  $("phaseNote").textContent = phase === PHASE.LOADING ? "Verifying with trusted sources..." : "";
  const loading = phase === PHASE.LOADING;
  $("skeletonPanel").classList.toggle("hidden", !loading);
  $("btnSpinner").classList.toggle("hidden", !loading);
  $("btnLabel").textContent = loading ? "Checking..." : "Check posting";
  $("btnRun").setAttribute("aria-busy", loading ? "true" : "false");
}

function setCacheOverlay(hit) {
  const root = document.querySelector(".shell");
  root.dataset.cache = hit ? "hit" : "miss";
  const badge = $("cacheBadge");
  if (hit) {
    badge.classList.remove("hidden");
    badge.textContent = "Recent shared check (cache hit)";
  } else {
    badge.classList.add("hidden");
  }
}

function confidenceToPercent(confidence) {
  if (String(confidence).toLowerCase() === "high") return 88;
  if (String(confidence).toLowerCase() === "medium") return 62;
  return 34;
}

function mapUiPhaseFromReport(report) {
  const v = report.verdict;
  const c = report.confidence;
  const warns = report.warnings?.length ?? 0;
  if (v === "APPLY" && c === "high" && warns === 0) return PHASE.SUCCESS;
  return PHASE.WARNING; // VERIFY, SKIP, or APPLY with uncertainty
}

function verdictStyle(verdict) {
  if (verdict === "APPLY") return { color: "#22c55e", icon: "✓" };
  if (verdict === "SKIP") return { color: "#ef4444", icon: "✕" };
  return { color: "#f59e0b", icon: "?" };
}

function classifySignal(signal) {
  const st = String(signal?.strength || "").toLowerCase();
  if (st === "high") return { icon: "✓", color: "#22c55e" };
  if (st === "medium") return { icon: "?", color: "#f59e0b" };
  return { icon: "✕", color: "#ef4444" };
}

function summarizeForUser(report) {
  const verdict = String(report.verdict || "VERIFY");
  if (verdict === "APPLY") return "Signals look strong, but still verify details before applying.";
  if (verdict === "SKIP") return "This posting shows enough risk patterns to skip unless independently verified.";
  return "Treat this as uncertain and verify on official employer channels first.";
}

function renderReport(report) {
  $("verdict").textContent = report.verdict;
  $("confidence").textContent = report.confidence;
  const style = verdictStyle(report.verdict);
  $("verdictChip").style.color = style.color;
  $("verdictChip").style.borderColor = `${style.color}66`;
  $("verdictIcon").textContent = style.icon;

  const pct = confidenceToPercent(report.confidence);
  $("confidencePct").textContent = `${pct}%`;
  $("confidenceFill").style.width = `${pct}%`;

  const checklist = $("signalChecklist");
  checklist.innerHTML = "";
  for (const s of report.signals || []) {
    const state = classifySignal(s);
    const li = document.createElement("li");
    li.className = "signal-item";
    li.innerHTML = `
      <span class="signal-icon" style="color:${state.color}">${state.icon}</span>
      <div>
        <div class="signal-name">${escapeHtml(s.label || s.id || "Signal")}</div>
        <div class="signal-detail">${escapeHtml(s.details || "")}</div>
      </div>
    `;
    checklist.appendChild(li);
  }

  const reasons = $("reasonList");
  reasons.innerHTML = "";
  for (const r of report.reasons || []) {
    const li = document.createElement("li");
    li.textContent = `${r.code}: ${r.message}`;
    reasons.appendChild(li);
  }

  const warns = $("warnList");
  warns.innerHTML = "";
  for (const w of report.warnings || []) {
    const li = document.createElement("li");
    li.textContent = `${w.code}: ${w.message}`;
    warns.appendChild(li);
  }

  $("meaningBox").textContent = `What this means for you: ${summarizeForUser(report)}`;

  const strip = $("uncertaintyStrip");
  const uncertain = report.verdict === "VERIFY" || report.confidence !== "high" || (report.warnings?.length ?? 0) > 0;
  if (uncertain) {
    strip.textContent = "Limited certainty — verify on the employer's official careers page.";
    strip.classList.remove("hidden");
  } else {
    strip.classList.add("hidden");
  }
}


function renderRecommendations(report) {
  const section = $("recSection");
  const meta = $("recMeta");
  const list = $("recList");
  const recs = report.recommendations;
  const st = report.meta?.recommendations_status;
  if (st == null && (!recs || recs.length === 0)) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  if (st === "unavailable") {
    meta.textContent =
      report.meta?.recommendations_message ||
      "Similar jobs need search configuration on the server (see API docs).";
    list.innerHTML = "";
    return;
  }
  if (!recs?.length) {
    meta.textContent = "No similar postings returned for this query (limits, search results, or verify filters).";
    list.innerHTML = "";
    return;
  }
  meta.textContent = "Advisory matches only — not endorsements. Confirm each posting yourself.";
  list.innerHTML = "";
  for (const r of recs) {
    const li = document.createElement("article");
    li.className = "rec-card";
    const band = r.confidence_band === "HIGH" ? "HIGH" : "MEDIUM";
    const badgeClass = band === "HIGH" ? "badge-high" : "badge-medium";
    const reasons = (r.similarity_reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>No reason supplied.</li>";
    li.innerHTML = `
      <div class="rec-head">
        <span class="badge ${badgeClass}">${escapeHtml(band)}</span>
        <span class="muted">Verdict: ${escapeHtml(r.verdict || "—")}</span>
      </div>
      <a class="rec-url" href="${escapeHtml(String(r.job_url || "#"))}" target="_blank" rel="noopener noreferrer">${escapeHtml(
      String(r.job_url || "View posting"),
    )}</a>
      <ul class="rec-reasons">${reasons}</ul>
    `;
    list.appendChild(li);
  }
}

function renderIngestion(report) {
  const el = $("ingestionNote");
  const ing = report.ingestion;
  if (!ing) {
    el.classList.add("hidden");
    el.textContent = "";
    el.classList.remove("warn");
    return;
  }
  el.classList.remove("hidden");
  if (ing.status === "insufficient") {
    el.textContent =
      ing.message ||
      "Screenshot alone was not readable enough — paste the job URL (preferred) or full job text.";
    el.classList.add("warn");
    return;
  }
  el.classList.remove("warn");
  const conf = ing.extraction_confidence ?? "n/a";
  const mime = ing.detected_mime ? ` • ${ing.detected_mime}` : "";
  el.textContent = `Screenshot extraction confidence: ${conf}${mime}`;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getApiBase() {
  if (window.location.protocol === "file:") {
    return "http://127.0.0.1:8080";
  }
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0") {
    return "http://127.0.0.1:8080";
  }
  return ""; // Relative path for production
}

let lastReport = null;

function syncHeroEmptyText(url, text, file) {
  const hasAny = Boolean((url || "").trim() || (text || "").trim() || file);
  $("emptyStateText").textContent = hasAny
    ? "Ready to verify. You can combine URL, description, and screenshot."
    : "Drop a job link or paste a description to begin.";
}

async function runFlow() {
  // Auto-reset UI state on new run
  $("errorPanel").classList.add("hidden");
  $("result").classList.add("hidden");
  
  const { url, text, file, recommendations } = readInputs();
  syncHeroEmptyText(url, text, file);
  const validation = validateClientInputs(url, text, file);
  if (!validation.ok) {
    setPhase(PHASE.ERROR);
    $("errorText").textContent = validation.message;
    $("errorPanel").classList.remove("hidden");
    return;
  }

  setPhase(PHASE.LOADING);
  $("btnRun").disabled = true;

  try {
    let res;
    const apiBase = getApiBase();
    if (file) {
      const fd = new FormData();
      if (url) fd.append("job_url", url);
      if (text) fd.append("job_description", text);
      fd.append("job_image", file, file.name || "screenshot.png");
      fd.append("recommendations_enabled", recommendations ? "true" : "false");
      res = await fetch(`${apiBase}/v1/verify`, { method: "POST", body: fd });
    } else {
      res = await fetch(`${apiBase}/v1/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_url: url || null,
          job_description: text || null,
          recommendations_enabled: recommendations,
        }),
      });
    }
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`);
    }
    const report = await res.json();
    lastReport = report;
    renderReport(report);
    renderIngestion(report);
    renderRecommendations(report);

    const uiPhase = mapUiPhaseFromReport(report);
    setPhase(uiPhase);
    setCacheOverlay(Boolean(report.cache?.hit));

    $("result").classList.remove("hidden");
  } catch (e) {
    setPhase(PHASE.ERROR);
    const msg = e && e.message ? String(e.message) : "Unknown error";
    $("errorText").textContent = `Network or server error (no verdict could be reached). Details: ${msg}`;
    $("errorPanel").classList.remove("hidden");
  } finally {
    $("btnRun").disabled = false;
    $("skeletonPanel").classList.add("hidden");
  }
}

$("btnCopyJson").addEventListener("click", () => {
  if (!lastReport) return;
  const json = JSON.stringify(lastReport, null, 2);
  navigator.clipboard.writeText(json).then(() => {
    const btn = $("btnCopyJson");
    const old = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => (btn.textContent = old), 2000);
  });
});

$("btnRun").addEventListener("click", () => {
  setPhase(PHASE.IDLE);
  runFlow();
});

$("btnRetry").addEventListener("click", () => {
  $("errorPanel").classList.add("hidden");
  runFlow();
});

$("jobImage").addEventListener("change", () => {
  const f = $("jobImage").files?.[0];
  const wrap = $("imagePreviewWrap");
  const img = $("imagePreview");
  if (!f) {
    wrap.classList.add("hidden");
    img.removeAttribute("src");
    return;
  }
  img.src = URL.createObjectURL(f);
  wrap.classList.remove("hidden");
  const { url, text, file } = readInputs();
  syncHeroEmptyText(url, text, file);
});

for (const tab of document.querySelectorAll(".tab-chip")) {
  tab.addEventListener("click", () => {
    const pane = $(tab.dataset.tabTarget);
    if (!pane) return;
    pane.classList.toggle("hidden");
    tab.classList.toggle("is-active", !pane.classList.contains("hidden"));
    tab.setAttribute("aria-pressed", tab.classList.contains("is-active") ? "true" : "false");
  });
}

$("jobUrl").addEventListener("input", () => {
  const { url, text, file } = readInputs();
  syncHeroEmptyText(url, text, file);
});

$("jobText").addEventListener("input", () => {
  const { url, text, file } = readInputs();
  syncHeroEmptyText(url, text, file);
});
