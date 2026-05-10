import { useCallback, useMemo, useState } from 'react';
import type { SanitizedVerifyReport } from '../types/verify';
import { sanitizeApiResponse } from '../utils/api-helpers';
import { resolveApiBase } from '../utils/apiBase';

export type BatchPhase = 'idle' | 'streaming' | 'done' | 'error';

export type BatchRow =
  | { url: string; status: 'pending' }
  | { url: string; status: 'done'; ok: true; report: SanitizedVerifyReport }
  | { url: string; status: 'done'; ok: false; error: string };

const VERDICT_RANK: Record<string, number> = { APPLY: 0, VERIFY: 1, SKIP: 2 };

export function sortBatchShortlist(rows: BatchRow[]): Array<{ url: string; report: SanitizedVerifyReport }> {
  const doneOk = rows.filter((r): r is Extract<BatchRow, { status: 'done'; ok: true }> => r.status === 'done' && r.ok);
  return [...doneOk]
    .map((r) => ({ url: r.url, report: r.report }))
    .sort((a, b) => {
      const va = VERDICT_RANK[String(a.report.verdict)] ?? 99;
      const vb = VERDICT_RANK[String(b.report.verdict)] ?? 99;
      if (va !== vb) return va - vb;
      return (b.report.confidence_score ?? 0) - (a.report.confidence_score ?? 0);
    });
}

async function messageFromFailedResponse(res: Response): Promise<string> {
  const status = res.status;
  try {
    const data = (await res.json()) as { detail?: unknown; message?: string };
    if (status === 422) {
      return 'We could not validate this batch request. Check URLs (max 40) and try again.';
    }
    if (status === 429) {
      return 'Too many checks in a short time. Please wait a minute and try again.';
    }
    if (status >= 500) {
      return 'Our verification service had a problem. Please try again in a moment.';
    }
    if (typeof data.message === 'string' && data.message.trim()) return data.message.trim();
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      const first = data.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${status}).`;
}

function parseBatchLine(line: string): { url: string; ok: boolean; report?: unknown; error?: string } | null {
  const t = line.trim();
  if (!t) return null;
  try {
    const obj = JSON.parse(t) as unknown;
    if (!obj || typeof obj !== 'object') return null;
    const rec = obj as Record<string, unknown>;
    const url = typeof rec.url === 'string' ? rec.url : '';
    const ok = Boolean(rec.ok);
    if (!url) return null;
    return {
      url,
      ok,
      report: rec.report,
      error: typeof rec.error === 'string' ? rec.error : undefined,
    };
  } catch {
    return null;
  }
}

export function useBatchVerify() {
  const [phase, setPhase] = useState<BatchPhase>('idle');
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const sortedShortlist = useMemo(() => sortBatchShortlist(rows), [rows]);

  const resetBatch = useCallback(() => {
    setPhase('idle');
    setRows([]);
    setError(null);
  }, []);

  const runBatch = useCallback(async (urls: string[], opts: { includeSimilarJobs?: boolean }) => {
    const unique = [...new Set(urls.map((u) => u.trim()).filter(Boolean))];
    if (!unique.length) return;

    setPhase('streaming');
    setError(null);
    setRows(unique.map((url) => ({ url, status: 'pending' as const })));

    const base = resolveApiBase();

    let response: Response;
    try {
      response = await fetch(`${base}/v1/verify/batch`, {
        method: 'POST',
        headers: {
          Accept: 'application/x-ndjson',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          urls: unique,
          options: {
            include_similar_jobs: opts.includeSimilarJobs,
            force_refresh: false,
          },
        }),
      });
    } catch (e) {
      console.error('batch verify network error', e);
      setError('Could not reach the verification service. Check your connection and try again.');
      setPhase('error');
      return;
    }

    if (!response.ok) {
      const msg = await messageFromFailedResponse(response);
      setError(msg);
      setPhase('error');
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      setError('Streaming response was not available.');
      setPhase('error');
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          const parsed = parseBatchLine(line);
          if (!parsed) continue;
          setRows((prev) =>
            prev.map((row) => {
              if (row.url !== parsed.url) return row;
              if (parsed.ok && parsed.report && typeof parsed.report === 'object') {
                return {
                  url: parsed.url,
                  status: 'done',
                  ok: true,
                  report: sanitizeApiResponse(parsed.report),
                };
              }
              return {
                url: parsed.url,
                status: 'done',
                ok: false,
                error: parsed.error?.trim() || 'Verification failed for this URL.',
              };
            }),
          );
        }
      }
      const tail = parseBatchLine(buffer);
      if (tail) {
        setRows((prev) =>
          prev.map((row) => {
            if (row.url !== tail.url) return row;
            if (tail.ok && tail.report && typeof tail.report === 'object') {
              return {
                url: tail.url,
                status: 'done',
                ok: true,
                report: sanitizeApiResponse(tail.report),
              };
            }
            return {
              url: tail.url,
              status: 'done',
              ok: false,
              error: tail.error?.trim() || 'Verification failed for this URL.',
            };
          }),
        );
      }
      setPhase('done');
    } catch (e) {
      console.error('batch verify stream error', e);
      setError('The batch stream was interrupted. Partial results may be shown.');
      setPhase('error');
    }
  }, []);

  return { phase, rows, sortedShortlist, error, runBatch, resetBatch };
}
