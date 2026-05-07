chrome.runtime.onInstalled.addListener(() => {
  // Set default backend URL, user can override in settings
  chrome.storage.local.set({ backendUrl: "https://jobsignal.up.railway.app" });
});
