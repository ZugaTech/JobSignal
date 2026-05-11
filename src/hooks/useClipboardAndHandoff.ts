import { useEffect, useState, useCallback } from 'react';

const JOB_URL_PATTERN = /^https?:\/\/.*(linkedin\.com\/jobs|indeed\.com|glassdoor\.com\/job|greenhouse\.io|lever\.co|workday|wellfound\.com|jobvite|smartrecruiters|ashbyhq|bamboohr)/i;
const JOB_DESCRIPTION_KEYWORDS = [
  "responsibilities", "requirements", "qualifications", "experience", "salary",
  "compensation", "apply", "hiring", "position", "role", "full-time", "part-time",
  "remote", "on-site", "hybrid", "benefits",
];

function decodeBase64JsonParam(value: string): unknown {
  return JSON.parse(decodeURIComponent(escape(atob(value))));
}

export function useClipboardAndHandoff(
  onDetect: (data: {
    url?: string;
    text?: string;
    batch?: string[];
    cachedResult?: unknown;
    verifyDepth?: 'quick' | 'full';
  }) => void,
) {
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
      const hostOk =
        typeof window !== 'undefined' &&
        (window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname));
      if (!hostOk || !navigator.clipboard?.readText) return;

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
      console.warn('clipboard read unavailable', e);
    }
  }, []);

  useEffect(() => {
    // Handle query params for extension handoff
    const params = new URLSearchParams(window.location.search);
    const cached_result = params.get("cached_result");
    const url = params.get("url");
    const job_description = params.get("job_description");
    const batch_urls = params.get("batch_urls");
    const verify_depth_raw = params.get('verify_depth') || params.get('depth');

    let detected = false;
    const result: {
      url?: string;
      text?: string;
      batch?: string[];
      cachedResult?: unknown;
      verifyDepth?: 'quick' | 'full';
    } = {};

    if (verify_depth_raw === 'quick' || verify_depth_raw === 'full') {
      result.verifyDepth = verify_depth_raw;
      detected = true;
    }

    if (url) {
      result.url = decodeURIComponent(url);
      detected = true;
    }

    if (cached_result) {
      try {
        result.cachedResult = decodeBase64JsonParam(cached_result);
        detected = true;
      } catch (e) {
        console.warn('failed to decode cached_result handoff', e);
      }
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
