/**
 * JobSignal UI — calls POST /v1/verify.
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

function classifySignal(signal) {
  const st = String(signal?.strength || "").toLowerCase();
  if (st === "high") return { color: "#22c55e" };
  if (st === "warning") return { color: "#f59e0b" };
  return { color: "#ef4444" };
}

function summarizeForUser(report) {
  const v = report.verdict;
  if (v === "APPLY") return "Signals look strong, but still verify details before applying.";
  if (v === "SKIP") return "This posting shows enough risk patterns to skip.";
  return "Treat this as uncertain and verify on official channels.";
}

function renderReport(report) {
  $("verdict").textContent = report.verdict;
  const style = verdictStyle(report.verdict);
  $("verdictChip").dataset.verdict = report.verdict;
  $("verdictIcon").textContent = style.icon;

  const pct = report.confidence === "high" ? 88 : (report.confidence === "medium" ? 62 : 34);
  $("confidencePct").textContent = `${pct}%`;
  $("confidenceFill").style.width = `${pct}%`;
  $("confidence").textContent = report.confidence;

  const checklist = $("signalChecklist");
  checklist.innerHTML = "";
  (report.signals || []).forEach(s => {
    const state = classifySignal(s);
    const li = document.createElement("li");
    li.className = "signal-item";
    li.innerHTML = `
      <div class="signal-left">
        <span class="signal-dot" style="background-color:${state.color}"></span>
        <span class="signal-name">${s.label || s.id}</span>
      </div>
      <span class="signal-badge" style="color:${state.color}; border-color:${state.color}66">${s.strength}</span>
    `;
    checklist.appendChild(li);
  });

  $("reasonList").innerHTML = (report.reasons || []).map(r => `<li>${r.code}: ${r.message}</li>`).join("");
  $("warnList").innerHTML = (report.warnings || []).map(w => `<li>${w.code}: ${w.message}</li>`).join("");
  $("meaningBox").textContent = `What this means for you: ${summarizeForUser(report)}`;
  $("requestIdLine").textContent = report.request_id ? `Request ID: ${report.request_id}` : "";
  
  const uncertain = report.verdict === "VERIFY" || report.confidence !== "high";
  $("uncertaintyStrip").classList.toggle("hidden", !uncertain);
}

function renderRecommendations(report) {
  const section = $("recSection");
  const list = $("recList");
  const recs = report.recommendations || [];
  if (!recs.length) { section.classList.add("hidden"); return; }
  section.classList.remove("hidden");
  $("recMeta").textContent = "Similar postings from our verified dataset.";
  list.innerHTML = recs.map(r => `
    <article class="rec-card">
      <div class="rec-head">
        <span class="badge badge-${r.confidence_band === "HIGH" ? "high" : "medium"}">${r.confidence_band}</span>
        <span class="muted">${r.verdict}</span>
      </div>
      <a class="rec-url" href="${r.job_url}" target="_blank">${r.job_url.substring(0, 40)}...</a>
    </article>
  `).join("");
}

function renderIngestion(report) {
  const el = $("ingestionNote");
  const ing = report.ingestion;
  if (!ing) { el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  el.textContent = ing.status === "insufficient" ? "Screenshot was unreadable." : `Extraction confidence: ${ing.extraction_confidence}`;
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
