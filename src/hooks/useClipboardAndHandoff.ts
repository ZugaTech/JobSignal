import { useEffect, useState, useCallback } from 'react';

const JOB_URL_PATTERN = /^https?:\/\/.*(linkedin\.com\/jobs|indeed\.com|glassdoor\.com\/job|greenhouse\.io|lever\.co|workday|wellfound\.com|jobvite|smartrecruiters|ashbyhq|bamboohr)/i;
const JOB_DESCRIPTION_KEYWORDS = [
  "responsibilities", "requirements", "qualifications", "experience", "salary",
  "compensation", "apply", "hiring", "position", "role", "full-time", "part-time",
  "remote", "on-site", "hybrid", "benefits",
];

export function useClipboardAndHandoff(onDetect: (data: { url?: string; text?: string; batch?: string[] }) => void) {
  const [pendingClipboard, setPendingClipboard] = useState<{ content: string; type: 'url' | 'description' | 'unknown' } | null>(null);

  const classifyContent = (text: string) => {
    if (/^https?:\/\//i.test(text)) {
      if (JOB_URL_PATTERN.test(text)) return 'url';
      return 'unknown';
    }
    if (text.length > 100) {
      const matches = JOB_DESCRIPTION_KEYWORDS.filter(k => text.toLowerCase().includes(k)).length;
      if (matches >= 3) return 'description';
    }
    return 'unknown';
  };

  const detectClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text || !text.trim()) return;
      
      const trimmed = text.trim();
      if (trimmed === sessionStorage.getItem("last_seen_clipboard")) return;
      if (trimmed === sessionStorage.getItem("clipboard_analyzed")) return;
      
      sessionStorage.setItem("last_seen_clipboard", trimmed);
      const type = classifyContent(trimmed);
      
      if (type !== 'unknown') {
        setPendingClipboard({ content: trimmed, type });
      }
    } catch (e) {
      // Clipboard access denied or unsupported
    }
  }, []);

  useEffect(() => {
    // Handle query params for extension handoff
    const params = new URLSearchParams(window.location.search);
    const url = params.get("url");
    const job_description = params.get("job_description");
    const batch_urls = params.get("batch_urls");

    let detected = false;
    const result: { url?: string; text?: string; batch?: string[] } = {};

    if (url) {
      result.url = url;
      detected = true;
    }

    if (job_description) {
      try {
        result.text = decodeURIComponent(atob(job_description));
        detected = true;
      } catch (e) {}
    }

    if (batch_urls) {
      try {
        const raw = decodeURIComponent(atob(batch_urls));
        result.batch = JSON.parse(raw);
        detected = true;
      } catch (e) {}
    }

    if (detected) {
      onDetect(result);
      // Clean up URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    // Initial clipboard check
    detectClipboard();
    
    // Check on focus
    window.addEventListener('focus', detectClipboard);
    return () => window.removeEventListener('focus', detectClipboard);
  }, [detectClipboard, onDetect]);

  return {
    pendingClipboard,
    dismissClipboard: () => setPendingClipboard(null),
    confirmClipboard: () => {
      if (pendingClipboard) {
        onDetect(pendingClipboard.type === 'url' ? { url: pendingClipboard.content } : { text: pendingClipboard.content });
        sessionStorage.setItem("clipboard_analyzed", pendingClipboard.content);
        setPendingClipboard(null);
      }
    }
  };
}
