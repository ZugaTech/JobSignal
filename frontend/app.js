/**
 * JobSignal minimal UI (Sprint 3).
 * Phases: idle, loading, success, warning, error. cache_hit is an overlay on success/warning.
 * Replace mockVerify with fetch("/v1/verify") when the API is available.
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

function readInputs() {
  return { url: $("jobUrl").value, text: $("jobText").value };
}

function validateClientInputs(urlRaw, textRaw) {
  const url = String(urlRaw ?? "").trim();
  const text = String(textRaw ?? "").trim();
  if (!url && !text) {
    return { ok: false, message: "Enter a job URL and/or pasted description." };
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
  const note = $("phaseNote");
  if (phase === PHASE.LOADING) {
    note.textContent = "Checking sources…";
  } else if (phase === PHASE.IDLE) {
    note.textContent = "";
  } else {
    note.textContent = "";
  }
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

function mapUiPhaseFromReport(report) {
  const v = report.verdict;
  const c = report.confidence;
  const warns = report.warnings?.length ?? 0;
  if (v === "APPLY" && c === "high" && warns === 0) return PHASE.SUCCESS;
  return PHASE.WARNING; // VERIFY, SKIP, or APPLY with uncertainty
}

function renderReport(report) {
  $("verdict").textContent = report.verdict;
  $("confidence").textContent = report.confidence;

  const tbody = $("signalTable").querySelector("tbody");
  tbody.innerHTML = "";
  for (const s of report.signals ?? []) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(s.id)}</td><td>${escapeHtml(s.tier)}</td><td>${escapeHtml(
      s.strength,
    )}</td><td>${escapeHtml(s.details ?? "")}</td>`;
    tbody.appendChild(tr);
  }

  const rl = $("reasonList");
  rl.innerHTML = "";
  for (const r of report.reasons ?? []) {
    const li = document.createElement("li");
    li.textContent = `${r.code}: ${r.message}`;
    rl.appendChild(li);
  }

  const wl = $("warnList");
  wl.innerHTML = "";
  for (const w of report.warnings ?? []) {
    const li = document.createElement("li");
    li.textContent = `${w.code}: ${w.message}`;
    wl.appendChild(li);
  }

  const strip = $("uncertaintyStrip");
  const uncertain = report.verdict === "VERIFY" || report.confidence !== "high" || (report.warnings?.length ?? 0) > 0;
  if (uncertain) {
    strip.classList.remove("hidden");
  } else {
    strip.classList.add("hidden");
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Demo-only mock: swap for real API response shape (`build_public_report`). */
function mockVerify() {
  return {
    report_schema_version: "1.0.0",
    verdict: "VERIFY",
    confidence: "medium",
    reasons: [
      { code: "DEMO", message: "Mock response — wire backend for live evidence." },
      { code: "COVERAGE", message: "UI shows uncertainty whenever confidence is not high." },
    ],
    warnings: [{ code: "DEMO", message: "This is a static demo." }],
    signals: [
      { id: "fetch_ok", label: "fetch_ok", tier: "T1", strength: "medium", details: "mock" },
      { id: "domain_align", label: "domain_align", tier: "T1", strength: "medium", details: "mock" },
    ],
    cache: { hit: true, ttl_expires_at: null, key_fingerprint: "demo" },
    meta: { pipeline_version: "1", scorer_version: "3.0.0" },
  };
}

async function runFlow() {
  $("errorPanel").classList.add("hidden");
  $("result").classList.add("hidden");
  const { url, text } = readInputs();
  const validation = validateClientInputs(url, text);
  if (!validation.ok) {
    setPhase(PHASE.ERROR);
    $("errorText").textContent = validation.message;
    $("errorPanel").classList.remove("hidden");
    return;
  }

  setPhase(PHASE.LOADING);
  $("btnRun").disabled = true;

  try {
    // Simulate latency; replace with fetch() to API.
    await new Promise((r) => setTimeout(r, 350));
    const report = mockVerify();
    renderReport(report);

    const uiPhase = mapUiPhaseFromReport(report);
    setPhase(uiPhase);
    setCacheOverlay(Boolean(report.cache?.hit));

    $("result").classList.remove("hidden");
  } catch (e) {
    setPhase(PHASE.ERROR);
    const msg = e && e.message ? String(e.message) : "Unknown error";
    $("errorText").textContent = `Network or server error — no verdict fabricated. (${msg})`;
    $("errorPanel").classList.remove("hidden");
  } finally {
    $("btnRun").disabled = false;
  }
}

$("btnRun").addEventListener("click", () => {
  setPhase(PHASE.IDLE);
  runFlow();
});
