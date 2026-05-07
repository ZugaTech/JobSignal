function extractJobData() {
  const url = window.location.href;
  
  let titleElement = document.querySelector('h1') || document.querySelector('[class*="job-title"]') || document.querySelector('[data-test*="title"]');
  const title = titleElement ? titleElement.innerText.trim() : null;

  let company = null;
  if (url.includes('linkedin.com')) {
    const el = document.querySelector('.topcard__org-name');
    if (el) company = el.innerText.trim();
  } else if (url.includes('indeed.com')) {
    const el = document.querySelector('.jobsearch-CompanyInfoContainer');
    if (el) company = el.innerText.trim();
  }
  
  let descElement = document.querySelector('[class*="description"]') || document.querySelector('[id*="description"]') || document.body;
  const description = descElement ? descElement.innerText.trim().substring(0, 50000) : null;

  return { url, title, company, description, low_confidence: !title || !description };
}

chrome.runtime.sendMessage({
  type: "JOB_DATA",
  payload: extractJobData()
}).catch(() => {});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "GET_JOB_DATA") {
    sendResponse(extractJobData());
  }
});
