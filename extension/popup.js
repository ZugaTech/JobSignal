/** Default to deployed Railway-style host; users can override in settings for local dev. */
let backendUrl = "https://jobsignal.up.railway.app";
let currentJobData = null;
let currentTabUrl = "";

const stateIdle = document.getElementById("stateIdle");
const stateLoading = document.getElementById("stateLoading");
const stateResult = document.getElementById("stateResult");
const stateError = document.getElementById("stateError");
const stateNotJob = document.getElementById("stateNotJob");
const settingsPanel = document.getElementById("settingsPanel");

function showState(stateEl) {
  [stateIdle, stateLoading, stateResult, stateError, stateNotJob].forEach((el) => {
    if (el) el.classList.add("hidden");
  });
  if (stateEl) stateEl.classList.remove("hidden");
}

chrome.storage.local.get(["backendUrl"], (res) => {
  const input = document.getElementById("backendUrlInput");
  if (res.backendUrl) {
    backendUrl = res.backendUrl;
    if (input) input.value = backendUrl;
  } else if (input && !input.value) {
    input.placeholder = "https://your-app.up.railway.app";
  }
});

document.getElementById("btnSettings").addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

document.getElementById("btnSaveSettings").addEventListener("click", () => {
  backendUrl = document.getElementById("backendUrlInput").value;
  chrome.storage.local.set({ backendUrl });
  settingsPanel.classList.add("hidden");
});

document.getElementById("btnClearCache").addEventListener("click", () => {
  chrome.storage.session.clear();
  alert("Cache cleared");
});

function openWebApp(url, text) {
  let origin = "https://jobsignal.up.railway.app";
  try {
    origin = new URL(backendUrl).origin;
  } catch {
    /* keep default */
  }
  const appUrl = new URL(origin);
  if (url) appUrl.searchParams.set("url", url);
  if (text) appUrl.searchParams.set("job_description", btoa(unescape(encodeURIComponent(text))));
  chrome.tabs.create({ url: appUrl.toString() });
}

document.getElementById("btnSeeFull").addEventListener("click", () => openWebApp(currentJobData?.url, currentJobData?.description));
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

  let conf = report.confidence === "high" ? 90 : (report.confidence === "medium" ? 60 : 30);
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
    const res = await fetch(`${backendUrl}/v1/verify`, {
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

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (!tabs[0]) return;
  const tab = tabs[0];
  currentTabUrl = tab.url;

  if (!tab.url.startsWith("http")) {
    showState(stateNotJob);
    return;
  }

  chrome.tabs.sendMessage(tab.id, { action: "GET_JOB_DATA" }, (response) => {
    if (chrome.runtime.lastError) {
      showState(stateNotJob);
      return;
    }

    if (response) {
      currentJobData = response;
      if (response.low_confidence) {
        showState(stateNotJob);
      } else {
        document.getElementById("previewTitle").textContent = response.title || "Unknown Title";
        document.getElementById("previewCompany").textContent = response.company || "Unknown Company";
        document.getElementById("jobPreview").classList.remove("hidden");
        
        if (response.url && response.description) {
          verifyJob(response);
        } else {
          showState(stateIdle);
        }
      }
    } else {
      showState(stateNotJob);
    }
  });
});
