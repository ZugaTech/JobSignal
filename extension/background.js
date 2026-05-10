chrome.runtime.onInstalled.addListener(() => {
  // Set default backend URL, user can override in settings
  chrome.storage.local.set({ backendUrl: "https://jobsignal.up.railway.app" });
});

const STANDALONE_HANDOFF_KEY = "standaloneHandoff";

function openStandaloneWindow() {
  chrome.windows.create({
    url: chrome.runtime.getURL("popup.html?standalone=true"),
    type: "popup",
    width: 420,
    height: 600,
  });
}

function saveHandoffAndOpen(tabUrl, jobData) {
  chrome.storage.session.set(
    {
      [STANDALONE_HANDOFF_KEY]: {
        tabUrl,
        jobData,
      },
    },
    openStandaloneWindow
  );
}

function getJobDataFromTab(tab) {
  if (!tab?.id || !tab.url?.startsWith("http")) {
    openStandaloneWindow();
    return;
  }

  chrome.tabs.sendMessage(tab.id, { action: "GET_JOB_DATA" }, (response) => {
    if (!chrome.runtime.lastError) {
      saveHandoffAndOpen(tab.url, response ?? null);
      return;
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id },
        files: ["content.js"],
      },
      () => {
        if (chrome.runtime.lastError) {
          saveHandoffAndOpen(tab.url, null);
          return;
        }

        chrome.tabs.sendMessage(
          tab.id,
          { action: "GET_JOB_DATA" },
          (retryResponse) => {
            saveHandoffAndOpen(
              tab.url,
              chrome.runtime.lastError ? null : retryResponse ?? null
            );
          }
        );
      }
    );
  });
}

chrome.action.onClicked.addListener((tab) => {
  getJobDataFromTab(tab);
});
