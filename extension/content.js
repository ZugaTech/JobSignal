function extractJobData() {
  const url = window.location.href;
  
  const titleElement =
    document.querySelector('h1[data-testid="jobsearch-JobInfoHeader-title"]') ||
    document.querySelector("h1") ||
    document.querySelector('[class*="job-title"]') ||
    document.querySelector('[data-test*="title"]');
  const rawTitle = titleElement ? titleElement.innerText.trim() : "";
  const title =
    rawTitle ||
    document.title
      .replace(/\s*-\s*.+$/, "")
      .replace(/\s*\|\s*.+$/, "")
      .trim() ||
    null;

  let company = null;
  if (url.includes('linkedin.com')) {
    const el = document.querySelector('.topcard__org-name');
    if (el) company = el.innerText.trim();
  } else if (url.includes('indeed.com')) {
    const el =
      document.querySelector('[data-testid="inlineHeader-companyName"]') ||
      document.querySelector('[data-company-name="true"]') ||
      document.querySelector('.jobsearch-CompanyInfoContainer');
    if (el) company = el.innerText.trim();
  }
  
  const descElement =
    document.querySelector("#jobDescriptionText") ||
    document.querySelector('[data-testid="jobDescriptionText"]') ||
    document.querySelector('[class*="description"]') ||
    document.querySelector('[id*="description"]') ||
    document.body;
  const description = descElement ? descElement.innerText.trim().substring(0, 50000) : null;

  return {
    url,
    title,
    company,
    description,
    low_confidence: !description || description.length < 80,
  };
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
