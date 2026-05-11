import type { SanitizedVerifyReport } from '../types/verify';

const MAX_LINES = 8;

/**
 * User-safe lines for "what we tried" (cache, fetch policy, similar jobs).
 * Server warnings stay in the Heads up section to avoid duplicate lists.
 */
export function buildAttemptLogLines(report: SanitizedVerifyReport): string[] {
  const out: string[] = [];
  const seen = new Set<string>();

  const add = (s: string) => {
    const t = s.trim();
    if (!t) return;
    const k = t.toLowerCase();
    if (seen.has(k)) return;
    seen.add(k);
    out.push(t);
  };

  const meta =
    report.meta && typeof report.meta === 'object' && !Array.isArray(report.meta)
      ? (report.meta as Record<string, unknown>)
      : {};

  const hasUrl = typeof meta.canonical_job_url === 'string' && meta.canonical_job_url.trim().length > 4;
  const fp = meta.job_page_fetch_profile;
  const att = meta.job_page_fetch_attempted === true;

  if (report.cached) {
    add('This result was loaded from cache for the same normalized input, not a full live re-run.');
  }

  const vd =
    typeof meta.verify_depth === 'string' ? meta.verify_depth.trim().toLowerCase() : 'full';
  if (vd === 'quick') {
    add(
      'Quick depth: fewer public searches, no AI text signals on the posting, and no similar-job recommendations.',
    );
  }

  if (fp === 'off' && hasUrl) {
    add(
      'Live download of the posting page was turned off; we relied more on search and other public checks instead of HTML from the listing.',
    );
  } else if (fp === 'live' && att) {
    add(
      'We requested the listing page over HTTPS (with size limits) to capture title, meta tags, and readable text where the host allows it.',
    );
  } else if (fp === 'live' && hasUrl && !att) {
    add('Job-page fetch was enabled; a bounded download did not run or did not return a usable page body for this run.');
  }

  if (meta.similar_jobs_requested === true && meta.recommendations_status === 'empty') {
    add('Similar postings search ran but nothing met the confidence bar we use for suggestions.');
  }

  return out.slice(0, MAX_LINES);
}
