/** Default to deployed Railway-style host; users can override in settings for local dev. */
let backendUrl = "https://jobsignal.up.railway.app";
/** Optional full web app URL (settings); otherwise same origin as backendUrl is used. */
let webAppUrlOverride = null;
let currentJobData = null;
let currentTabUrl = "";
let lastVerifyResult = null;

const STANDALONE_HANDOFF_KEY = "standaloneHandoff";
const isStandalone =
  new URLSearchParams(window.location.search).get("standalone") === "true";

const btnOpenInWindow = document.getElementById("btnOpenInWindow");
const btnCloseStandalone = document.getElementById("btnCloseStandalone");
if (isStandalone) {
  btnOpenInWindow.classList.add("hidden");
  btnCloseStandalone.classList.remove("hidden");
} else {
  btnOpenInWindow.classList.remove("hidden");
  btnCloseStandalone.classList.add("hidden");
}

const stateIdle = document.getElementById("stateIdle");
const stateLoading = document.getElementById("stateLoading");
const stateResult = document.getElementById("stateResult");
const stateError = document.getElementById("stateError");
const stateNotJob = document.getElementById("stateNotJob");
const settingsPanel = document.getElementById("settingsPanel");

function normalizeApiOrigin(value) {
  return (value || "").trim().replace(/\/+$/, "");
}

function showState(stateEl) {
  [stateIdle, stateLoading, stateResult, stateError, stateNotJob].forEach((el) => {
    if (el) el.classList.add("hidden");
  });
  if (stateEl) stateEl.classList.remove("hidden");
}

chrome.storage.local.get(["backendUrl", "webAppUrl"], (res) => {
  const input = document.getElementById("backendUrlInput");
  if (res.backendUrl) {
    backendUrl = normalizeApiOrigin(res.backendUrl);
    if (input) input.value = backendUrl;
  } else if (input && !input.value) {
    input.placeholder = "https://your-app.up.railway.app";
  }
  if (res.webAppUrl) {
    webAppUrlOverride = res.webAppUrl;
  }
});

btnOpenInWindow.addEventListener("click", () => {
  chrome.storage.session.set(
    {
      [STANDALONE_HANDOFF_KEY]: {
        tabUrl: currentTabUrl,
        jobData: currentJobData,
      },
    },
    () => {
      chrome.windows.create({
        url: chrome.runtime.getURL("popup.html?standalone=true"),
        type: "popup",
        width: 420,
        height: 600,
      });
    }
  );
});

btnCloseStandalone.addEventListener("click", () => window.close());

document.getElementById("btnSettings").addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

document.getElementById("btnSaveSettings").addEventListener("click", () => {
  backendUrl = normalizeApiOrigin(document.getElementById("backendUrlInput").value);
  document.getElementById("backendUrlInput").value = backendUrl;
  chrome.storage.local.set({ backendUrl });
  settingsPanel.classList.add("hidden");
});

document.getElementById("btnClearCache").addEventListener("click", () => {
  chrome.storage.session.clear();
  alert("Cache cleared");
});

function encodeUtf8Base64(value) {
  return btoa(unescape(encodeURIComponent(value)));
}

function openWebApp(jobUrl, jobDescription, existingResult) {
  let baseForOrigin = webAppUrlOverride || backendUrl;
  let origin = "https://jobsignal.up.railway.app";
  try {
    origin = new URL(baseForOrigin.replace(/\/v1.*$/, "").replace(/\/api.*$/, "")).origin;
  } catch {
    /* keep default */
  }

  const params = new URLSearchParams();
  if (jobUrl) params.set("url", encodeURIComponent(jobUrl));

  if (existingResult) {
    try {
      const encoded = encodeUtf8Base64(JSON.stringify(existingResult));
      if (encoded.length <= 50 * 1024) {
        params.set("cached_result", encoded);
      } else {
        console.warn("Result handoff too large; opening web app with URL only");
      }
    } catch (e) {
      console.warn("Could not encode result for handoff", e);
    }
  } else if (jobDescription && jobDescription.trim().length > 0) {
    const encoded = encodeUtf8Base64(jobDescription);
    if (encoded.length <= 50 * 1024) {
      params.set("job_description", encoded);
    }
  }

  const qs = params.toString();
  chrome.tabs.create({ url: qs ? `${origin}/?${qs}` : `${origin}/` });
}

document.getElementById("btnSeeFull").addEventListener("click", () => openWebApp(currentJobData?.url, currentJobData?.description, lastVerifyResult));
document.getElementById("btnOpenApp").addEventListener("click", () => openWebApp(currentTabUrl, null));
document.getElementById("btnOpenAppFallback").addEventListener("click", () => openWebApp(currentTabUrl, null));

document.getElementById("btnVerify").addEventListener("click", () => {
  if (currentJobData) {
    verifyJob(currentJobData);
  } else {
    // If somehow clicked without data, just use URL
    verifyJob({ url: currentTabUrl });
  }
});

function applyResult(report) {
  lastVerifyResult = report;
  showState(stateResult);
  
  const vBand = document.getElementById("verdictBand");
  const vChip = document.getElementById("verdictChip");
  const vLabel = document.getElementById("verdictLabel");
  const vIcon = document.getElementById("verdictIcon");
  
  vLabel.textContent = report.verdict || "UNKNOWN";
  
  let color = "#ef4444";
  if (report.verdict === "APPLY") { color = "#22c55e"; vIcon.textContent = "✓"; vBand.style.borderTopColor = color; }
  else if (report.verdict === "VERIFY") { color = "#f59e0b"; vIcon.textContent = "!"; vBand.style.borderTopColor = color; }
  else { vIcon.textContent = "×"; vBand.style.borderTopColor = color; }
  
  vChip.style.color = color;
  vChip.style.borderColor = color;

  let conf = Number.isFinite(Number(report.confidence_score))
    ? Math.max(0, Math.min(100, Number(report.confidence_score)))
    : 0;
  document.getElementById("confidencePct").textContent = conf + "%";
  document.getElementById("confidenceFill").style.width = conf + "%";
  document.getElementById("confidenceFill").style.backgroundColor = color;

  const ul = document.getElementById("signalList");
  ul.innerHTML = "";
  (report.signals || []).slice(0, 3).forEach(s => {
    const li = document.createElement("li");
    li.className = "signal-item";
    
    let sColor = "#a3a3a3";
    if (s.strength === "high") sColor = "#22c55e";
    if (s.strength === "warning") sColor = "#f59e0b";
    if (s.strength === "danger") sColor = "#ef4444";

    li.innerHTML = `
      <div><span class="signal-dot" style="background:${sColor}"></span>${s.label || s.id}</div>
      <span style="font-size:0.7rem; color:${sColor}">${s.strength}</span>
    `;
    ul.appendChild(li);
  });
}

async function verifyJob(data) {
  showState(stateLoading);
  
  const cacheKey = "verify_" + btoa(data.url || currentTabUrl).substring(0, 50);
  const cached = await chrome.storage.session.get(cacheKey);
  if (cached[cacheKey]) {
    applyResult(cached[cacheKey]);
    return;
  }

  try {
    const res = await fetch(`${normalizeApiOrigin(backendUrl)}/v1/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_url: data.url,
        job_description: data.description
      })
    });
    
    if (!res.ok) throw new Error("Verification failed: " + res.status);
    
    const report = await res.json();
    await chrome.storage.session.set({ [cacheKey]: report });
    applyResult(report);
  } catch (err) {
    console.error(err);
    const msg =
      err instanceof TypeError
        ? "JobSignal is temporarily unavailable. Please try again in a moment."
        : (err?.message || "Failed to connect to backend.");
    document.getElementById("errorText").textContent = msg;
    showState(stateError);
  }
}

function applyJobPageContext(tabUrl, response) {
  currentTabUrl = tabUrl;

  if (!tabUrl.startsWith("http")) {
    showState(stateNotJob);
    return;
  }

  if (!response) {
    showState(stateNotJob);
    return;
  }

  currentJobData = response;
  if (response.low_confidence) {
    showState(stateNotJob);
    return;
  }

  document.getElementById("previewTitle").textContent =
    response.title || "Unknown Title";
  document.getElementById("previewCompany").textContent =
    response.company || "Unknown Company";
  document.getElementById("jobPreview").classList.remove("hidden");

  if (response.url && response.description) {
    verifyJob(response);
  } else {
    showState(stateIdle);
  }
}

function loadFromActiveTab() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    const tab = tabs[0];

    if (!tab.url.startsWith("http")) {
      currentTabUrl = tab.url;
      showState(stateNotJob);
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: "GET_JOB_DATA" }, (response) => {
      if (chrome.runtime.lastError) {
        chrome.scripting.executeScript(
          {
            target: { tabId: tab.id },
            files: ["content.js"],
          },
          () => {
            if (chrome.runtime.lastError) {
              currentTabUrl = tab.url;
              showState(stateNotJob);
              return;
            }

            chrome.tabs.sendMessage(
              tab.id,
              { action: "GET_JOB_DATA" },
              (retryResponse) => {
                if (chrome.runtime.lastError) {
                  currentTabUrl = tab.url;
                  showState(stateNotJob);
                  return;
                }
                applyJobPageContext(tab.url, retryResponse);
              }
            );
          }
        );
        return;
      }
      applyJobPageContext(tab.url, response);
    });
  });
}

if (isStandalone) {
  chrome.storage.session.get(STANDALONE_HANDOFF_KEY, (res) => {
    const handoff = res[STANDALONE_HANDOFF_KEY];
    if (handoff && typeof handoff.tabUrl === "string") {
      chrome.storage.session.remove(STANDALONE_HANDOFF_KEY);
      applyJobPageContext(handoff.tabUrl, handoff.jobData ?? null);
    } else {
      loadFromActiveTab();
    }
  });
} else {
  loadFromActiveTab();
}
