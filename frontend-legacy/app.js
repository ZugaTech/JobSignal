const $ = (id) => document.getElementById(id);

const PHASE = {
  IDLE: "idle",
  LOADING: "loading",
  ERROR: "error",
};

const MAX_IMAGE_BYTES =
  typeof window.JOBSIGNAL_MAX_UPLOAD_BYTES === "number" && window.JOBSIGNAL_MAX_UPLOAD_BYTES > 0
    ? window.JOBSIGNAL_MAX_UPLOAD_BYTES
    : 5 * 1024 * 1024;
const BATCH_VERIFY_CONCURRENCY = 3;
const ACCEPT_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

/** API origin for /v1/*. Same-origin when UI is served from FastAPI on :8080; fixed host when UI is file:// or another port. */
/** Fetch wrapper: network-level failures get a clean user message (no silent console-only errors). */
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    return { ok: true, res };
  } catch {
    return { ok: false, res: null };
  }
}

function resolveApiBase() {
  if (typeof window.JOBSIGNAL_API_BASE === "string" && window.JOBSIGNAL_API_BASE.trim()) {
    return window.JOBSIGNAL_API_BASE.replace(/\/$/, "");
  }
  const h = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  if (protocol === "file:" || h === "") {
    return "http://127.0.0.1:8080";
  }
  if ((h === "localhost" || h === "127.0.0.1") && port === "8080") {
    return "";
  }
  if (h === "localhost" || h === "127.0.0.1") {
    return "http://127.0.0.1:8080";
  }
  return "";
}

function getActivePaneId() {
  const active = Array.from(document.querySelectorAll(".input-pane")).find((pane) => !pane.classList.contains("hidden"));
  return active?.id || "urlPane";
}

function readInputs() {
  const activePane = getActivePaneId();
  const urlVal = $("jobUrl")?.value.trim() || "";
  const textVal = $("jobText")?.value.trim() || "";

  if (activePane === "batchPane") {
    return {
      url: "",
      text: "",
      file: null,
      activePane,
      includeSimilarJobs: $("includeSimilarJobs").checked,
    };
  }

  const file = activePane === "imagePane" ? $("jobImage")?.files?.[0] ?? null : null;

  return {
    url: urlVal,
    text: textVal,
    file,
    activePane,
    includeSimilarJobs: $("includeSimilarJobs").checked,
  };
}

function normalizeJobUrlInput(raw) {
  let u = String(raw ?? "").trim().replace(/[\r\n]+/g, "").trim();
  if (!u) return "";
  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
  return u;
}

function looksLikeJobUrl(text) {
  const s = String(text ?? "").trim();
  if (!s || s.includes("\n")) return false;
  if (/^https?:\/\//i.test(s)) return true;
  return /^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\/.+/i.test(s);
}

function formatCachedAgo(iso) {
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

function validateClientInputs(urlRaw, textRaw, file) {
  const url = String(urlRaw ?? "").trim();
  const text = String(textRaw ?? "").trim();
  if (!url && !text && !file) return { ok: false, message: "Add a link, description, or screenshot." };
  if (file && file.size > MAX_IMAGE_BYTES)
    return { ok: false, message: "Image too large. Please use an image under 5MB." };
  return { ok: true };
}

/* --- Clipboard detection & extension query params --- */
const JOB_URL_PATTERN =
  /^https?:\/\/.*(linkedin\.com\/jobs|indeed\.com|glassdoor\.com\/job|greenhouse\.io|lever\.co|workday|wellfound\.com|jobvite|smartrecruiters|ashbyhq|bamboohr)/i;
const JOB_DESCRIPTION_KEYWORDS = [
  "responsibilities",
  "requirements",
  "qualifications",
  "experience",
  "salary",
  "compensation",
  "apply",
  "hiring",
  "position",
  "role",
  "full-time",
  "part-time",
  "remote",
  "on-site",
  "hybrid",
  "benefits",
];

let pendingClipboard = { content: "", type: "" };
let fabHideTimer = null;

function countJobKeywords(text) {
  const lower = String(text || "").toLowerCase();
  return JOB_DESCRIPTION_KEYWORDS.filter((k) => lower.includes(k)).length;
}

function classifyClipboardContent(text) {
  if (/^https?:\/\//i.test(text)) {
    if (JOB_URL_PATTERN.test(text)) return "JOB_URL";
    return "OTHER_URL";
  }
  if (text.length > 100) {
    const matches = countJobKeywords(text);
    if (matches >= 3) return "JOB_DESCRIPTION";
  }
  return "UNKNOWN";
}

function shouldShowClipboardFab(type, text) {
  if (type === "JOB_URL") return true;
  if (type === "JOB_DESCRIPTION" && countJobKeywords(text) >= 5) return true;
  return false;
}

function switchTab(name) {
  const map = { url: "urlPane", description: "textPane", batch: "batchPane", image: "imagePane" };
  const paneId = map[name] || "urlPane";
  document.querySelectorAll(".input-pane").forEach((p) => p.classList.add("hidden"));
  const pane = $(paneId);
  if (pane) pane.classList.remove("hidden");
  document.querySelectorAll(".tab-chip").forEach((t) => {
    const active = t.dataset.tabTarget === paneId;
    t.classList.toggle("is-active", active);
    if (t.hasAttribute("aria-pressed")) t.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function readDismissedClipboardSet() {
  try {
    const raw = sessionStorage.getItem("clipboard_dismissed_list");
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function writeDismissedClipboardSet(arr) {
  try {
    sessionStorage.setItem("clipboard_dismissed_list", JSON.stringify(arr.slice(-50)));
  } catch {
    /* ignore quota */
  }
}

function isClipboardDismissed(trimmed) {
  return readDismissedClipboardSet().includes(trimmed);
}

function hideClipboardToast() {
  const toast = $("clipboardToast");
  if (toast) toast.classList.add("hidden");
}

function hideClipboardFabAndTimers() {
  if (fabHideTimer) {
    clearTimeout(fabHideTimer);
    fabHideTimer = null;
  }
  const fab = $("quickAnalyzeFab");
  if (fab) fab.classList.add("hidden");
}

function showClipboardFabForPending() {
  const fab = $("quickAnalyzeFab");
  if (!fab || !shouldShowClipboardFab(pendingClipboard.type, pendingClipboard.content)) return;
  fab.classList.remove("hidden");
  if (fabHideTimer) clearTimeout(fabHideTimer);
  fabHideTimer = setTimeout(() => {
    fab.classList.add("hidden");
    fabHideTimer = null;
  }, 30000);
}

function showClipboardToast(content, type) {
  pendingClipboard = { content, type };
  const toast = $("clipboardToast");
  const msg = $("clipboardToastText");
  if (!toast || !msg) return;
  msg.textContent =
    type === "url"
      ? "Job link detected in clipboard — analyze it?"
      : "Job description detected in clipboard — analyze it?";
  toast.classList.remove("hidden");
  showClipboardFabForPending();
}

function showUrlClipboardBadge() {
  const b = $("urlClipboardBadge");
  const w = document.querySelector("#urlPane .input-wrapper");
  if (b) b.classList.remove("hidden");
  if (w) w.classList.add("from-clipboard");
}

function showTextClipboardBadge() {
  const b = $("textClipboardBadge");
  const w = document.querySelector("#textPane .input-wrapper");
  if (b) b.classList.remove("hidden");
  if (w) w.classList.add("from-clipboard");
}

function showManualClipboardButton() {
  const hint = $("clipboardHint");
  if (hint) hint.classList.remove("hidden");
}

function clipboardHttpsOk() {
  if (location.protocol === "https:") return true;
  const h = location.hostname;
  return h === "localhost" || h === "127.0.0.1";
}

async function detectClipboard() {
  if (!clipboardHttpsOk()) {
    showManualClipboardButton();
    return;
  }
  try {
    let permissionState = "prompt";
    try {
      const permission = await navigator.permissions.query({ name: "clipboard-read" });
      permissionState = permission.state;
    } catch {
      /* Permissions API unsupported — still try readText */
    }
    if (permissionState === "denied") {
      showManualClipboardButton();
      return;
    }

    const text = await navigator.clipboard.readText();
    if (!text || text.trim().length === 0) return;

    const trimmed = text.trim();
    if (isClipboardDismissed(trimmed)) return;
    if (trimmed === sessionStorage.getItem("last_seen_clipboard")) return;
    if (trimmed === sessionStorage.getItem("clipboard_analyzed")) return;

    sessionStorage.setItem("last_seen_clipboard", trimmed);

    const type = classifyClipboardContent(trimmed);
    if (type === "JOB_URL") {
      showClipboardToast(trimmed, "url");
    } else if (type === "JOB_DESCRIPTION") {
      showClipboardToast(trimmed, "description");
    }
  } catch {
    showManualClipboardButton();
  }
}

function decodeJobDescriptionParam(b64) {
  if (!b64) return null;
  try {
    return decodeURIComponent(atob(b64));
  } catch {
    try {
      return decodeURIComponent(escape(atob(b64)));
    } catch {
      return null;
    }
  }
}

function handleQueryParams() {
  const params = new URLSearchParams(window.location.search);
  const cachedResultB64 = params.get("cached_result");
  const jobUrl = params.get("url");
  const jobDescriptionB64 = params.get("job_description");
  const batchUrlsParam = params.get("batch_urls");

  if (cachedResultB64) {
    try {
      const decoded = JSON.parse(decodeURIComponent(escape(atob(cachedResultB64))));
      if (jobUrl) {
        const urlInput = $("jobUrl");
        if (urlInput) urlInput.value = decodeURIComponent(jobUrl);
        switchTab("url");
      }
      openModal();
      populateModal(sanitizeApiResponse(decoded));
      $("modalSkeleton").classList.add("hidden");
      $("modalContent").classList.remove("hidden");
      window.history.replaceState({}, "", window.location.pathname);
      return;
    } catch (e) {
      console.warn("Failed to decode cached_result from extension, fetching fresh", e);
    }
  }

  if (jobUrl) {
    const urlInput = $("jobUrl");
    if (urlInput) urlInput.value = decodeURIComponent(jobUrl);
    switchTab("url");
    showUrlClipboardBadge();
  }

  if (jobDescriptionB64) {
    try {
      const decoded = decodeJobDescriptionParam(jobDescriptionB64);
      const descInput = $("jobText");
      if (decoded != null && decoded !== "" && descInput) {
        descInput.value = decoded;
        const wrap = document.querySelector("#textPane .input-wrapper");
        if (wrap) wrap.classList.add("from-clipboard");
        showTextClipboardBadge();
      }
      if (!jobUrl) switchTab("description");
    } catch (e) {
      console.warn("Failed to decode job_description param", e);
    }
  }

  if (batchUrlsParam) {
    try {
      const raw = decodeURIComponent(atob(batchUrlsParam));
      const urls = JSON.parse(raw);
      if (Array.isArray(urls) && urls.length > 0) {
        const batchInput = $("batchUrls");
        if (batchInput) batchInput.value = urls.join("\n");
        switchTab("batch");
      }
    } catch (e) {
      console.warn("Failed to decode batch_urls param", e);
    }
  }

  if (jobUrl || jobDescriptionB64) {
    runFlow();
  }
}

function wireClipboardUi() {
  const analyzeBtn = $("clipboardAnalyzeNow");
  const dismissBtn = $("clipboardDismiss");
  const fab = $("quickAnalyzeFab");
  const pasteBtn = $("btnClipboardPaste");
  const jobUrlEl = $("jobUrl");
  const jobTextEl = $("jobText");

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", () => {
      const { content, type } = pendingClipboard;
      const trimmed = (content || "").trim();
      sessionStorage.setItem("clipboard_analyzed", trimmed);
      hideClipboardToast();
      hideClipboardFabAndTimers();

      if (type === "url") {
        if (jobUrlEl) jobUrlEl.value = content;
        switchTab("url");
        showUrlClipboardBadge();
      } else if (type === "description") {
        if (jobTextEl) jobTextEl.value = content;
        switchTab("description");
        showTextClipboardBadge();
      }
      runFlow();
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => {
      const trimmed = (pendingClipboard.content || "").trim();
      if (trimmed) {
        const list = readDismissedClipboardSet();
        if (!list.includes(trimmed)) list.push(trimmed);
        writeDismissedClipboardSet(list);
      }
      hideClipboardToast();
      hideClipboardFabAndTimers();
    });
  }

  if (fab) {
    fab.addEventListener("click", () => {
      const { content, type } = pendingClipboard;
      const trimmed = (content || "").trim();
      sessionStorage.setItem("clipboard_analyzed", trimmed);
      hideClipboardToast();
      hideClipboardFabAndTimers();

      if (type === "url") {
        if (jobUrlEl) jobUrlEl.value = content;
        switchTab("url");
        showUrlClipboardBadge();
      } else if (type === "description") {
        if (jobTextEl) jobTextEl.value = content;
        switchTab("description");
        showTextClipboardBadge();
      }
      runFlow();
    });
  }

  if (pasteBtn) {
    pasteBtn.addEventListener("click", async () => {
      const hint = $("clipboardHint");
      try {
        const text = await navigator.clipboard.readText();
        if (!text || !text.trim()) {
          if (hint) {
            hint.textContent = "Please paste your job link or description directly into the field below.";
            hint.classList.remove("hidden");
          }
          return;
        }
        const trimmed = text.trim();
        const type = classifyClipboardContent(trimmed);
        if (type === "JOB_URL") {
          if (jobUrlEl) jobUrlEl.value = trimmed;
          switchTab("url");
          showUrlClipboardBadge();
        } else if (type === "JOB_DESCRIPTION") {
          if (jobTextEl) jobTextEl.value = trimmed;
          switchTab("description");
          showTextClipboardBadge();
        } else if (looksLikeJobUrl(trimmed)) {
          if (jobUrlEl) jobUrlEl.value = normalizeJobUrlInput(trimmed);
          switchTab("url");
          showUrlClipboardBadge();
        } else {
          if (jobTextEl) jobTextEl.value = trimmed;
          switchTab("description");
          showTextClipboardBadge();
        }
        if (hint) hint.classList.add("hidden");
      } catch {
        if (hint) {
          hint.textContent = "Please paste your job link or description directly into the field below.";
          hint.classList.remove("hidden");
        }
      }
    });
  }

  if (jobUrlEl)
    jobUrlEl.addEventListener("input", () => {
      $("urlClipboardBadge")?.classList.add("hidden");
      document.querySelector("#urlPane .input-wrapper")?.classList.remove("from-clipboard");
    });
  if (jobTextEl)
    jobTextEl.addEventListener("input", () => {
      $("textClipboardBadge")?.classList.add("hidden");
      document.querySelector("#textPane .input-wrapper")?.classList.remove("from-clipboard");
    });

  const du = $("dismissUrlBadge");
  const dt = $("dismissTextBadge");
  if (du)
    du.addEventListener("click", () => {
      $("urlClipboardBadge")?.classList.add("hidden");
      document.querySelector("#urlPane .input-wrapper")?.classList.remove("from-clipboard");
    });
  if (dt)
    dt.addEventListener("click", () => {
      $("textClipboardBadge")?.classList.add("hidden");
      document.querySelector("#textPane .input-wrapper")?.classList.remove("from-clipboard");
    });
}

function initClipboardAndDeepLink() {
  wireClipboardUi();
  handleQueryParams();
  detectClipboard();
}

document.addEventListener("DOMContentLoaded", initClipboardAndDeepLink);
window.addEventListener("focus", () => {
  detectClipboard();
});

function setPhase(phase) {
  const root = document.querySelector(".shell");
  if (root) root.dataset.uiPhase = phase;
  const loading = phase === PHASE.LOADING;
  if ($("btnSpinner")) $("btnSpinner").classList.toggle("hidden", !loading);
  if ($("btnLabel")) $("btnLabel").textContent = loading ? "Verifying..." : "Check posting";
  if ($("btnRun")) $("btnRun").disabled = loading;
}

const COPY_REWRITE_MAP = {
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

function rewriteMicrocopy(text) {
  if (!text) return "";
  let out = text;
  for (const [old, replacement] of Object.entries(COPY_REWRITE_MAP)) {
    out = out.replace(old, replacement);
  }
  return out;
}

function getConfidenceLevel(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "Unavailable";
  if (n <= 0) return "No rating";
  if (n < 34) return "Low";
  if (n < 67) return "Moderate";
  return "High";
}

function formatConfidenceBand(sanitized) {
  const lbl = sanitizeField(sanitized.confidence_label, "");
  if (lbl.toLowerCase() === "none") return "No rating";
  if (lbl) return lbl;
  if (sanitized.confidence_score === null || sanitized.confidence_score === undefined) return "Unavailable";
  return getConfidenceLevel(sanitized.confidence_score);
}

function renderExpandedSignals(signals) {
  const list = $("modalSignalList");
  if (!list || !Array.isArray(signals)) return;
  const checked = [];
  const unchecked = [];
  for (const s of signals) {
    if (isUncheckedSignalStrength(s.strength)) unchecked.push(s);
    else checked.push(s);
  }
  const rowHtml = (s, isUncheckedRow) => {
    const label = getSignalLabel(s.id);
    if (isUncheckedRow) {
      return `<div class="signal-list-item signal-unchecked"><span>${label}</span></div>`;
    }
    return `<div class="signal-list-item"><span>${label}</span><span class="muted small">${getStatusLabel(s.strength)}</span></div>`;
  };
  let html = checked.map((s) => rowHtml(s, false)).join("");
  if (unchecked.length) {
    html += `<div class="signal-unchecked-section"><div class="signal-unchecked-label">Not verified in this check</div>${unchecked.map((s) => rowHtml(s, true)).join("")}</div>`;
  }
  list.innerHTML = html || `<p class="muted small">No signals to list.</p>`;
}

let loadingInterval = null;
let loadingReassuranceTimeout = null;
let loadingElapsedInterval = null;
let loadingStartedAt = null;
let loadingSeqGen = 0;

function startLoadingSequence() {
  loadingSeqGen += 1;
  const gen = loadingSeqGen;
  const steps = [
    "Checking the job listing...",
    "Verifying company signals...",
    "Scanning public sources...",
    "Comparing cross-platform data...",
    "Reviewing company reputation...",
    "Building your report...",
  ];
  let currentStep = 0;
  const textEl = $("loadingStepText");
  const reassEl = $("loadingReassurance");
  const barEl = $("modalLoadingBar");
  const elapsedEl = $("loadingElapsed");
  if (!textEl || !reassEl || !barEl) return;

  barEl.classList.remove("hidden");
  reassEl.classList.add("hidden");
  textEl.style.opacity = "1";
  textEl.textContent = steps[0];
  loadingStartedAt = performance.now();
  if (elapsedEl) elapsedEl.textContent = "";

  if (loadingElapsedInterval) clearInterval(loadingElapsedInterval);
  loadingElapsedInterval = setInterval(() => {
    if (gen !== loadingSeqGen || loadingStartedAt == null) return;
    const s = Math.floor((performance.now() - loadingStartedAt) / 1000);
    if (elapsedEl) elapsedEl.textContent = `${s}s`;
  }, 400);

  loadingInterval = setInterval(() => {
    if (gen !== loadingSeqGen) return;
    currentStep = (currentStep + 1) % steps.length;
    textEl.style.opacity = "0";
    setTimeout(() => {
      if (gen !== loadingSeqGen) return;
      textEl.textContent = steps[currentStep];
      textEl.style.opacity = "1";
    }, 400);
  }, 3000);

  loadingReassuranceTimeout = setTimeout(() => {
    if (gen !== loadingSeqGen) return;
    reassEl.classList.remove("hidden");
    reassEl.style.opacity = "1";
  }, 15000);
}

function stopLoadingSequence() {
  loadingSeqGen += 1;
  loadingStartedAt = null;
  if (loadingInterval) clearInterval(loadingInterval);
  loadingInterval = null;
  if (loadingElapsedInterval) clearInterval(loadingElapsedInterval);
  loadingElapsedInterval = null;
  if ($("loadingElapsed")) $("loadingElapsed").textContent = "";
  if (loadingReassuranceTimeout) clearTimeout(loadingReassuranceTimeout);
  loadingReassuranceTimeout = null;
  if ($("modalLoadingBar")) $("modalLoadingBar").classList.add("hidden");
}

/* Modal Management */
function openModal() {
  $("resultModalOverlay").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  // Reset modal state
  $("modalSkeleton").classList.remove("hidden");
  $("modalContent").classList.add("hidden");
  $("similarJobsSection").classList.add("hidden");
  $("modalVerdictBadge").classList.add("hidden");
  if ($("modalCacheChip")) {
    $("modalCacheChip").classList.add("hidden");
    $("modalCacheChip").textContent = "";
  }
  if ($("modalContent")) $("modalContent").classList.remove("modal-grid--single");
  if ($("signalDataUnavailable")) $("signalDataUnavailable").classList.add("hidden");
  if ($("signalVerificationSection")) $("signalVerificationSection").classList.remove("hidden");
  if ($("modalSignalList")) {
    $("modalSignalList").innerHTML = "";
    $("modalSignalList").classList.remove("signal-list-reveal");
  }
  if ($("toggleSignalsLabel")) $("toggleSignalsLabel").textContent = "View verification details ↓";
  const chevron = document.querySelector(".sig-chevron");
  if (chevron) chevron.style.transform = "";
  window.__sanitizedSignals = [];
  startLoadingSequence();
}

function closeModal() {
  $("resultModalOverlay").classList.add("hidden");
  document.body.style.overflow = "";
  stopLoadingSequence();
}

if ($("btnCloseModal")) {
  $("btnCloseModal").addEventListener("click", closeModal);
}
if ($("resultModalOverlay")) {
  $("resultModalOverlay").addEventListener("click", (e) => {
    if (e.target === $("resultModalOverlay")) closeModal();
  });
}
// Drag handle close logic for mobile sheet feel
if (document.querySelector(".modal-drag-handle")) {
    document.querySelector(".modal-drag-handle").addEventListener("click", closeModal);
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

/** Render adaptive input_meta banners in the modal */
function renderInputMetaBanner(report) {
  const banner = $("inputMetaBanner");
  if (!banner) return;
  banner.innerHTML = "";
  banner.classList.add("hidden");

  const meta = report.input_meta;
  if (!meta) return;

  const { input_method, company_identified, auto_url_extracted, low_quality_image } = meta || {};

  let html = "";

  // Auto URL extracted from description — green/positive
  if (auto_url_extracted) {
    html = `
      <div class="input-meta-chip input-meta-chip--positive">
        <span>✓ We found a link in your input and verified it directly.</span>
      </div>`;
  }

  // No company identified — amber partial banner
  if (!company_identified && !auto_url_extracted && input_method && input_method !== "url") {
    const ctaId = "metaBannerAddUrl";
    html += `
      <div class="input-meta-chip input-meta-chip--warn">
        <div class="input-meta-chip-title">Partial verification — no company identified</div>
        <p class="input-meta-chip-body">We could not find a company name in this ${input_method === "screenshot" ? "screenshot" : "description"}. Without knowing who posted this role, we cannot verify the employer or check this listing against public records. Here is what we found from the ${input_method === "screenshot" ? "image" : "description"} alone.</p>
        <button id="${ctaId}" class="input-meta-cta-btn" type="button">Add the job URL for full verification →</button>
      </div>`;
  }

  // Low quality image
  if (meta.low_quality_image) {
    html += `
      <div class="input-meta-chip input-meta-chip--warn">
        <div class="input-meta-chip-title">Image quality was too low</div>
        <p class="input-meta-chip-body">The screenshot was too unclear for reliable extraction. Try a clearer screenshot or paste the job text instead.</p>
      </div>`;
  }

  if (!html) return;

  banner.innerHTML = html;
  banner.classList.remove("hidden");

  // Wire CTA: close modal, switch to URL tab, keep description in memory
  const ctaBtn = $("metaBannerAddUrl");
  if (ctaBtn) {
    ctaBtn.addEventListener("click", () => {
      const savedText = $("jobText")?.value || "";
      closeModal();
      // Switch to URL tab
      document.querySelectorAll(".tab-chip").forEach((t) => {
        if (t.dataset.tabTarget === "urlPane") {
          t.click();
        }
      });
      // Preserve description in text pane
      if (savedText && $("jobText")) $("jobText").value = savedText;
    });
  }
}

/** Render image extraction transparency panel */
function renderImageExtractionPanel(report) {
  const section = $("imageExtractionSection");
  const content = $("imageExtractionContent");
  if (!section || !content) return;
  section.classList.add("hidden");
  content.innerHTML = "";

  const meta = report.input_meta;
  if (!meta || meta.input_method !== "screenshot") return;
  const fields = meta.extracted_fields;
  if (!fields) return;

  const fieldRow = (label, value) => {
    const hasValue = value && String(value).trim();
    return `<div class="extraction-row ${hasValue ? "" : "extraction-row--missing"}">
      <span class="extraction-label">${label}</span>
      <span class="extraction-value">${hasValue ? sanitizeField(String(value), "") : '<span class="extraction-not-found">Not found</span>'}</span>
    </div>`;
  };

  content.innerHTML = [
    fieldRow("Job Title", fields.job_title),
    fieldRow("Company", fields.company_name),
    fieldRow("URL", fields.url_hint),
  ].join("");

  section.classList.remove("hidden");
}

/* Rendering */
function renderReputation(summary) {
  const container = $("modalRepContent");
  if (!container) return;
  container.innerHTML = "";

  if (!summary || summary.status === "unavailable") {
    container.innerHTML = `<p class="rep-summary italic">Employer reputation data unavailable for this posting.</p>`;
    return;
  }

  const rawScore = summary.review_confidence_score;
  const hasNumScore = typeof rawScore === "number" && !Number.isNaN(rawScore);
  const scoreDisp = hasNumScore ? String(rawScore) : "Unavailable";
  const scoreColor = !hasNumScore ? "#737373" : rawScore >= 70 ? "#22c55e" : rawScore >= 40 ? "#f59e0b" : "#ef4444";

  const overallSentiment = rewriteMicrocopy(sanitizeField(summary.overall_sentiment, "Neutral")).replace(/_/g, " ");

  const barPct = hasNumScore ? rawScore : 0;

  container.innerHTML = `
    <p class="muted small" style="margin-bottom: 12px;">Employer reputation score — reflects public mentions of the company, separate from this posting.</p>
    <div class="rep-score-card">
      <div class="rep-circle" style="border-color: ${scoreColor}; color: ${scoreColor}">
        <span class="rep-num">${scoreDisp}</span>
        <span class="rep-label">Trust</span>
      </div>
      <div class="sentiment-pill" style="background: ${scoreColor}15; color: ${scoreColor}">
        ${overallSentiment}
      </div>
    </div>
    <div class="rep-tags">
      ${(summary.green_flags || []).map(f => `<span class="pill-tag positive">✓ ${sanitizeField(f, "")}</span>`).join("")}
      ${(summary.red_flags || []).map(f => `<span class="pill-tag negative">⚠ ${sanitizeField(f, "")}</span>`).join("")}
    </div>
    <div class="rep-ratio-bar">
      <div class="ratio-green" style="width: ${barPct}%"></div>
      <div class="ratio-red" style="width: ${hasNumScore ? 100 - barPct : 0}%"></div>
    </div>
    <p class="rep-summary">${rewriteMicrocopy(sanitizeField(summary.plain_summary, "No summary available for this result."))}</p>
    <div class="muted small mt-4" style="border-top: 1px solid rgba(255,255,255,0.04); padding-top: 12px;">
      Sources reflect public web results where available.
    </div>
  `;
}

function populateModal(report) {
  stopLoadingSequence();
  const sanitized = sanitizeApiResponse(report);
  window.__lastRawReport = report;
  window.__lastSanitizedReport = sanitized;
  window.__sanitizedSignals = sanitized.signals;

  $("modalSkeleton").classList.add("hidden");
  $("modalContent").classList.remove("hidden");

  // Adaptive banners and image extraction panel
  renderInputMetaBanner(report);
  renderImageExtractionPanel(report);

  const modalContent = $("modalContent");

  // Verdict
  const v = sanitized.verdict || "VERIFY";
  const vBadge = $("modalVerdictBadge");
  if (vBadge) {
    vBadge.textContent = v;
    vBadge.className = `verdict-chip-mini ${v.toLowerCase()}`;
    vBadge.classList.remove("hidden");
  }

  const cacheChip = $("modalCacheChip");
  if (cacheChip) {
    if (report.cached === true && report.cache_complete === false) {
      cacheChip.classList.remove("hidden");
      cacheChip.textContent = "Partial cached result — reanalysing for full report...";
    } else if (report.cached === true && report.cached_at) {
      cacheChip.classList.remove("hidden");
      cacheChip.textContent = `${formatCachedAgo(report.cached_at)} · Cached result`;
    } else {
      cacheChip.classList.add("hidden");
      cacheChip.textContent = "";
    }
  }

  if ($("modalVerdictLarge")) {
    $("modalVerdictLarge").innerHTML = `<div class="verdict-chip-large ${v.toLowerCase()}">${v}</div>`;
  }

  // Confidence
  const score = sanitized.confidence_score;
  const fill = $("modalConfidenceFill");
  if ($("modalConfidencePct")) {
    if (score === null || score === undefined) {
      $("modalConfidencePct").textContent = "Unavailable";
      if (fill) fill.style.width = "0%";
    } else {
      $("modalConfidencePct").textContent = `${score}%`;
      if (fill) {
        fill.style.width = "0%";
        requestAnimationFrame(() => {
          fill.style.width = `${score}%`;
        });
      }
    }
  }
  const confLine = document.querySelector(".confidence-line span:first-child");
  if (confLine) confLine.textContent = `Confidence: ${formatConfidenceBand(sanitized)}`;

  if ($("modalContent")) modalContent.className = `modal-grid ${v.toLowerCase()}${sanitized.hideReputationPanel ? " modal-grid--single" : ""}`;

  const signals = sanitized.signals || [];
  const sigAvail = $("signalDataUnavailable");
  const sigSection = $("signalVerificationSection");
  const btnSig = $("btnToggleSignals");

  if (sanitized.hideSignalsSection) {
    if (sigAvail) sigAvail.classList.remove("hidden");
    if (sigSection) sigSection.classList.add("hidden");
    if (btnSig) btnSig.classList.add("hidden");
  } else {
    if (sigAvail) sigAvail.classList.add("hidden");
    if (sigSection) sigSection.classList.remove("hidden");
    if (btnSig) btnSig.classList.remove("hidden");

    let passed = 0;
    let flagged = 0;
    let inconclusive = 0;
    signals.forEach((s) => {
      if (s.strength === "high" || s.strength === "medium") passed++;
      else if (s.strength === "low") flagged++;
      else inconclusive++;
    });

    if ($("modalSignalSummaryText")) {
      $("modalSignalSummaryText").innerHTML = `We checked <strong>${signals.length}</strong> signals — <span style="color:#4ade80">${passed} confirmed</span>, <span style="color:#f87171">${flagged} flagged</span>, <span style="color:#525252">${inconclusive} inconclusive</span>.`;
    }

    const dots = $("modalSignalDots");
    if (dots) {
      dots.innerHTML = signals
        .map((s) => {
          const type =
            s.strength === "high" || s.strength === "medium"
              ? "pass"
              : s.strength === "low"
                ? "fail"
                : "warn";
          return `<span class="signal-dot ${type}" title="${getSignalLabel(s.id)}: ${getStatusLabel(s.strength)}"></span>`;
        })
        .join("");
    }
  }

  const sigList = $("modalSignalList");
  if (sigList) {
    sigList.innerHTML = "";
    sigList.classList.remove("signal-list-reveal");
  }
  if ($("toggleSignalsLabel")) $("toggleSignalsLabel").textContent = "View verification details ↓";
  const chevronReset = document.querySelector(".sig-chevron");
  if (chevronReset) chevronReset.style.transform = "";

  // Reasons
  if ($("modalReasonList")) {
    $("modalReasonList").innerHTML = sanitized.reasons.map((r) => `<li>${rewriteMicrocopy(r)}</li>`).join("");
  }

  // Warnings
  const warns = report.warnings || [];
  if ($("modalKeepInMind")) {
    if (warns.length > 0) {
      $("modalKeepInMind").classList.remove("hidden");
      if ($("modalWarningList")) {
        $("modalWarningList").innerHTML = warns
          .map((w) => `<li>${rewriteMicrocopy(formatReasonForDisplay(w.code || w.message || w))}</li>`)
          .join("");
      }
    } else {
      $("modalKeepInMind").classList.add("hidden");
    }
  }

  // Reputation (panel hidden when no usable summary)
  if ($("modalRepContent")) $("modalRepContent").innerHTML = "";
  if (!sanitized.hideReputationPanel) {
    renderReputation(sanitized.review_summary);
  }

  // Footer & Summary
  if ($("modalLlmSummary")) {
    $("modalLlmSummary").textContent = rewriteMicrocopy(sanitizeField(sanitized.llm_summary, "No summary available for this result."));
  }
  if ($("modalRequestId")) $("modalRequestId").textContent = sanitized.request_id || "";

  // Similar Jobs
  if ($("similarJobsSection")) {
    if (!sanitized.hideSimilarJobs) {
      $("similarJobsSection").classList.remove("hidden");
      const sj = sanitized.similar_jobs;
      if (sanitized.similarJobsEmptyMessage) {
        $("similarJobsList").innerHTML = `<p class="muted small similar-jobs-empty">${sanitized.similarJobsEmptyMessage}</p>`;
      } else if (Array.isArray(sj) && sj.length > 0) {
        $("similarJobsList").innerHTML = sj
          .map((j) => {
            const ver = sanitizeField(j.verdict, "").toLowerCase();
            const vClass = ["apply", "verify", "skip"].includes(ver) ? ver : "verify";
            const pct =
              j.confidence_score !== undefined && j.confidence_score !== null
                ? `${j.confidence_score}%`
                : "—";
            const hrefRaw = sanitizeField(j.url, "");
            let safeUrl = false;
            try {
              const u = new URL(hrefRaw);
              safeUrl = u.protocol === "http:" || u.protocol === "https:";
            } catch {
              safeUrl = false;
            }
            const inner = `
          <span class="job-title">${sanitizeField(j.title, "Job listing")}</span>
          <span class="job-company">${sanitizeField(j.company, "Employer")}</span>
          <div class="job-card-meta">
            <span class="job-card-verdict ${vClass}">${sanitizeField(j.verdict, "VERIFY")}</span>
            <span>Confidence ${pct}</span>
          </div>
          <div class="job-platform">${sanitizeField(j.platform, "")}</div>
          ${safeUrl ? "" : `<p class="muted small" style="margin-top:8px;">Link unavailable</p>`}`;
            return safeUrl
              ? `<a href="${hrefRaw}" target="_blank" rel="noopener noreferrer" class="job-card">${inner}</a>`
              : `<div class="job-card job-card--disabled">${inner}</div>`;
          })
          .join("");
      } else {
        $("similarJobsList").innerHTML = "";
      }
    } else {
      $("similarJobsSection").classList.add("hidden");
    }
  }
}

function buildHumanReadableReport(s) {
  const lines = [];
  lines.push(`Verdict: ${sanitizeField(s.verdict, "VERIFY")}`);
  if (s.confidence_score != null) lines.push(`Job posting confidence: ${s.confidence_score}% (${sanitizeField(s.confidence_label, "")})`);
  lines.push("");
  lines.push("Summary:");
  lines.push(rewriteMicrocopy(sanitizeField(s.llm_summary, "")));
  if (s.reasons && s.reasons.length) {
    lines.push("");
    lines.push("Why:");
    s.reasons.forEach((r) => lines.push(`- ${rewriteMicrocopy(r)}`));
  }
  if (s.review_summary && s.review_summary.plain_summary) {
    lines.push("");
    lines.push("Employer reputation:");
    lines.push(rewriteMicrocopy(sanitizeField(s.review_summary.plain_summary, "")));
  }
  if (s.cached === true) {
    lines.push("");
    lines.push("Cached result:");
    if (s.cached_at) lines.push(`Originally analyzed: ${sanitizeField(s.cached_at, "")}`);
    if (s.cache_expires_in) lines.push(`Cache expires in: ${sanitizeField(s.cache_expires_in, "")}`);
  }
  return lines.join("\n");
}

async function mapWithConcurrency(items, worker, limit = BATCH_VERIFY_CONCURRENCY) {
  const safeLimit = Math.max(1, Number(limit) || 1);
  const queue = [...items];
  const runners = Array.from({ length: Math.min(safeLimit, queue.length) }, async () => {
    while (queue.length) {
      const next = queue.shift();
      if (!next) return;
      await worker(next);
    }
  });
  await Promise.all(runners);
}

/* Batch Flow */
async function runBatchFlow() {
    const rawLines = $("batchUrls").value.split("\n").map((u) => u.trim()).filter(Boolean);
    if (!rawLines.length) {
      $("errorPanel").classList.remove("hidden");
      $("errorText").textContent = "Add at least one URL for batch verification.";
      return;
    }

    const includeSimilarJobs = $("includeSimilarJobs")?.checked ?? false;

    $("batchResult").classList.remove("hidden");
    const list = $("batchList");
    list.innerHTML = "";
    setPhase(PHASE.LOADING);

    const base = resolveApiBase();
    const vr = await apiFetch(`${base}/v1/validate-urls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: rawLines }),
    });
    if (!vr.ok) {
      setPhase(PHASE.IDLE);
      $("errorPanel").classList.remove("hidden");
      $("errorText").textContent = "JobSignal is temporarily unavailable. Please try again in a moment.";
      return;
    }
    const validation = await vr.res.json();
    const rows = Array.isArray(validation.results) ? validation.results : [];

    const rowEntries = rows.map((row) => {
        const url = row.url || "";
        const item = document.createElement("div");
        item.className = "batch-item";
        item.innerHTML = `<span class="muted small">${url || "(empty line)"}</span> <span class="btn-spinner"></span>`;
        list.appendChild(item);
        return { row, url, item };
    });

    await mapWithConcurrency(rowEntries, async ({ row, url, item }) => {
        if (!row.ok) {
            item.innerHTML = `
                <span style="color:#ef4444;">SKIP</span>
                <span class="muted small truncate" style="max-width:220px;">${url}</span>
                <span class="muted small">${sanitizeField(row.reason, "Invalid URL.")}</span>`;
            return;
        }

        try {
            const fr = await apiFetch(`${base}/v1/verify`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ job_url: url, include_similar_jobs: includeSimilarJobs }),
            });
            if (!fr.ok) {
              item.innerHTML = `<span style="color:#ef4444;">ERROR</span> <span class="muted small">${url}</span> <span class="muted small">JobSignal is temporarily unavailable.</span>`;
              return;
            }
            const res = fr.res;
            const report = await res.json();
            const color = report.verdict === "APPLY" ? "#22c55e" : (report.verdict === "SKIP" ? "#ef4444" : "#f59e0b");
            const pct =
              report.confidence_score !== undefined && report.confidence_score !== null
                ? `${report.confidence_score}%`
                : "—";
            item.innerHTML = `
                <span style="color:${color}; font-weight:700;">${sanitizeField(report.verdict, "VERIFY")}</span>
                <span class="muted small truncate" style="max-width: 200px;">${url}</span>
                <span class="muted small">${pct}</span>
            `;
        } catch {
            item.innerHTML = `<span style="color:#ef4444;">ERROR</span> <span class="muted small">${url}</span>`;
        }
    });
    setPhase(PHASE.IDLE);
}

async function parseVerifyHttpError(res) {
  let msg = "Verification service is temporarily busy.";
  try {
    const j = await res.json();
    if (j && j.message) msg = String(j.message);
  } catch {
    if (res.status === 413) msg = "Image too large. Please use an image under 5MB.";
  }
  return msg;
}

/* Event Handlers */
async function runFlow() {
  let { url, text, file, activePane, includeSimilarJobs } = readInputs();

  // If in batch tab, run batch instead
  if (activePane === "batchPane") {
    await runBatchFlow();
    return;
  }

  if (activePane === "textPane" && text && !url && looksLikeJobUrl(text)) {
    const normalized = normalizeJobUrlInput(text);
    document.querySelectorAll(".tab-chip").forEach((t) => {
      if (t.dataset.tabTarget === "urlPane") t.click();
    });
    if ($("jobUrl")) $("jobUrl").value = normalized;
    if ($("jobText")) $("jobText").value = "";
    alert("Looks like a URL — switching to link mode.");
    url = normalized;
    text = "";
    activePane = "urlPane";
  }

  let urlSend = url;
  let textSend = text;
  if ((activePane === "urlPane" || activePane === "imagePane") && urlSend) {
    urlSend = normalizeJobUrlInput(urlSend);
  }

  const validation = validateClientInputs(urlSend, textSend, file);

  if (!validation.ok) {
    $("errorPanel").classList.remove("hidden");
    $("errorText").textContent = validation.message;
    return;
  }

  $("errorPanel").classList.add("hidden");
  setPhase(PHASE.LOADING);
  hideClipboardFabAndTimers();
  openModal();

  try {
    let res;
    const base = resolveApiBase();

    if (file) {
      const fd = new FormData();
      if (urlSend) fd.append("job_url", urlSend);
      if (textSend) fd.append("job_description", textSend);
      fd.append("job_image", file);
      fd.append("include_similar_jobs", includeSimilarJobs ? "true" : "false");
      const fr = await apiFetch(`${base}/v1/verify`, { method: "POST", body: fd });
      if (!fr.ok) throw new Error("UNAVAILABLE");
      res = fr.res;
    } else {
      const fr = await apiFetch(`${base}/v1/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_url: urlSend || null,
          job_description: textSend || null,
          include_similar_jobs: includeSimilarJobs,
        }),
      });
      if (!fr.ok) throw new Error("UNAVAILABLE");
      res = fr.res;
    }

    if (!res.ok) throw new Error(await parseVerifyHttpError(res));
    let report = await res.json();

    if (report.cached === true && report.cache_complete === false) {
      populateModal(report);
      try {
        let res2;
        if (file) {
          const fd = new FormData();
          if (urlSend) fd.append("job_url", urlSend);
          if (textSend) fd.append("job_description", textSend);
          fd.append("job_image", file);
          fd.append("include_similar_jobs", includeSimilarJobs ? "true" : "false");
          fd.append("force_refresh", "true");
          const fr2 = await apiFetch(`${base}/v1/verify`, { method: "POST", body: fd });
          if (fr2.ok) res2 = fr2.res;
        } else {
          const fr2 = await apiFetch(`${base}/v1/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              job_url: urlSend || null,
              job_description: textSend || null,
              include_similar_jobs: includeSimilarJobs,
              force_refresh: true,
            }),
          });
          if (fr2.ok) res2 = fr2.res;
        }
        if (res2 && res2.ok) {
          report = await res2.json();
        }
      } catch {
        /* keep partial cached report */
      }
    }

    populateModal(report);
    setPhase(PHASE.IDLE);
  } catch (e) {
    closeModal();
    setPhase(PHASE.ERROR);
    $("errorPanel").classList.remove("hidden");
    const msg =
      e && e.message === "UNAVAILABLE"
        ? "JobSignal is temporarily unavailable. Please try again in a moment."
        : (e && e.message) || "Something went wrong. Please try again.";
    $("errorText").textContent = msg;
  }
}

/* Initialization */
if ($("btnRun")) $("btnRun").addEventListener("click", runFlow);
if ($("btnRetry")) $("btnRetry").addEventListener("click", runFlow);
if ($("btnBatchReset")) {
    $("btnBatchReset").addEventListener("click", () => {
        $("batchUrls").value = "";
        $("batchList").innerHTML = "";
        $("batchResult").classList.add("hidden");
    });
}

/* Tabs */
document.querySelectorAll(".tab-chip").forEach(tab => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tabTarget;
    document.querySelectorAll(".input-pane").forEach(p => p.classList.add("hidden"));
    $(target).classList.remove("hidden");
    document.querySelectorAll(".tab-chip").forEach(t => t.classList.remove("is-active"));
    tab.classList.add("is-active");
  });
});

/* Drag & Drop */
const dropZone = $("dropZone");
const fileInput = $("jobImage");

if (dropZone && fileInput) {
  dropZone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file && ACCEPT_IMAGE_TYPES.includes(file.type)) {
      fileInput.files = e.dataTransfer.files;
      handleFile(file);
    }
  });
}

function handleFile(file) {
  if (!ACCEPT_IMAGE_TYPES.includes(file.type)) {
    $("errorPanel").classList.remove("hidden");
    $("errorText").textContent = "Please use a JPEG, PNG, WebP, or GIF image.";
    return;
  }
  if ($("dropZoneContent")) $("dropZoneContent").classList.add("hidden");
  if ($("fileInfo")) $("fileInfo").classList.remove("hidden");
  if ($("fileName")) $("fileName").textContent = file.name;
  if ($("fileSize")) $("fileSize").textContent = `(${(file.size / 1024).toFixed(1)} KB)`;
  
  const reader = new FileReader();
  reader.onload = (e) => {
    if ($("imagePreview")) $("imagePreview").src = e.target.result;
    if ($("imagePreviewWrap")) $("imagePreviewWrap").classList.remove("hidden");
  };
  reader.readAsDataURL(file);
}

if ($("btnRemoveFile")) {
  $("btnRemoveFile").addEventListener("click", (e) => {
    e.stopPropagation();
    if (fileInput) fileInput.value = "";
    if ($("dropZoneContent")) $("dropZoneContent").classList.remove("hidden");
    if ($("fileInfo")) $("fileInfo").classList.add("hidden");
    if ($("imagePreviewWrap")) $("imagePreviewWrap").classList.add("hidden");
  });
}

/* Toggle Signals */
if ($("btnToggleSignals")) {
  $("btnToggleSignals").addEventListener("click", () => {
    const list = $("modalSignalList");
    const isRevealed = list.classList.toggle("signal-list-reveal");
    if ($("toggleSignalsLabel")) $("toggleSignalsLabel").textContent = isRevealed ? "Hide details ↑" : "View verification details ↓";
    const chevron = document.querySelector(".sig-chevron");
    if (chevron) chevron.style.transform = isRevealed ? "rotate(180deg)" : "";
    if (isRevealed) {
      renderExpandedSignals(window.__sanitizedSignals || []);
    } else {
      list.innerHTML = "";
    }
  });
}

/* Copy report: human-readable by default; Shift+click copies technical JSON */
if ($("btnModalCopyJson")) {
  $("btnModalCopyJson").addEventListener("click", async (ev) => {
    const wantJson = ev.shiftKey === true;
    const payload = wantJson
      ? JSON.stringify(window.__lastRawReport || {}, null, 2)
      : buildHumanReadableReport(window.__lastSanitizedReport || {});
    try {
      await navigator.clipboard.writeText(payload);
      alert(wantJson ? "Technical JSON copied to clipboard." : "Summary report copied to clipboard. (Shift+click button for JSON.)");
    } catch {
      alert("Could not copy to clipboard.");
    }
  });
}
