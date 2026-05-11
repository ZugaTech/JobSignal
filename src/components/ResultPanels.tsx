import React from 'react';
import { Building2, ExternalLink } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import type { SanitizedVerifyReport } from '../types/verify';
import { rewriteMicrocopy, isSafeHttpUrl, sanitizeReputationPlainSummary } from '../utils/formatters';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function reputationSourcesCaption(rs: SanitizedVerifyReport['review_summary']): string | null {
  if (!rs) return null;
  const ds = rs.data_sources;
  if (!Array.isArray(ds) || ds.length === 0) return null;
  if (ds.includes('LLM knowledge') && ds.includes('Live search')) {
    return 'Sources: LLM knowledge + Live search';
  }
  if (ds.length === 1 && ds[0] === 'LLM knowledge only') {
    return 'Sources: LLM knowledge only (live data unavailable)';
  }
  if (ds.length === 1 && ds[0] === 'Live search only') {
    return 'Sources: Live search only';
  }
  return `Sources: ${ds.join(', ')}`;
}

export function ReputationSection({ report }: { report: SanitizedVerifyReport }) {
  return (
    <>
      {report.reputationPanelVariant === 'unavailable' && (
        <div className="glass rounded-3xl p-6 md:p-8 space-y-3 border border-border/60">
          <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
            <Building2 className="w-5 h-5 text-brand shrink-0" />
            Company reputation
          </h3>
          <p className="text-sm text-neutral-400 leading-relaxed">
            We did not find enough reliable public chatter to summarize how people feel about this employer.
          </p>
        </div>
      )}

      {report.reputationPanelVariant === 'no_company' && (
        <div className="glass rounded-3xl p-6 md:p-8 space-y-3 border border-border/60">
          <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
            <Building2 className="w-5 h-5 text-brand shrink-0" />
            Company reputation
          </h3>
          <p className="text-sm text-neutral-400 leading-relaxed">
            We could not pin down an employer from your input, so we skipped reputation lookup.
          </p>
        </div>
      )}

      {report.reputationPanelVariant === 'unconfirmed' && (
        <div className="glass rounded-3xl p-6 md:p-8 space-y-3 border border-border/60">
          <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
            <Building2 className="w-5 h-5 text-brand shrink-0" />
            Company reputation
          </h3>
          <p className="text-sm text-neutral-400 leading-relaxed">
            Employer identity not confirmed, so we skipped reputation lookup instead of summarizing the wrong entity.
          </p>
        </div>
      )}

      {report.reputationPanelVariant === 'full' && report.review_summary && (() => {
        const reputationSourcesLine = reputationSourcesCaption(report.review_summary);
        return (
        <div className="glass rounded-3xl p-6 md:p-8 space-y-6 border border-border/60 ring-1 ring-white/[0.04]">
          <div>
            <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
              <Building2 className="w-5 h-5 text-brand shrink-0" />
              Company reputation
            </h3>
            <p className="text-xs text-neutral-500 mt-1.5 leading-snug">
              What people say about the employer in public. Separate from how confident we are in this specific job
              posting.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-5 sm:gap-6">
            <div
              className={cn(
                'w-16 h-16 rounded-2xl flex flex-col items-center justify-center border-2 shrink-0',
                typeof report.review_summary.review_confidence_score === 'number' &&
                  report.review_summary.review_confidence_score >= 67
                  ? 'border-[#16A34A]/50 text-[#16A34A] bg-[#16A34A]/5'
                  : typeof report.review_summary.review_confidence_score === 'number' &&
                      report.review_summary.review_confidence_score >= 34
                    ? 'border-[#D97706]/50 text-[#D97706] bg-[#D97706]/5'
                    : 'border-[#DC2626]/50 text-[#DC2626] bg-[#DC2626]/5',
              )}
            >
              <span className="text-2xl font-black tabular-nums leading-none">
                {typeof report.review_summary.review_confidence_score === 'number' &&
                !Number.isNaN(report.review_summary.review_confidence_score)
                  ? report.review_summary.review_confidence_score
                  : 'N/A'}
              </span>
              <span className="text-[10px] uppercase font-semibold tracking-wide opacity-70 mt-1">Index</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-neutral-500 uppercase tracking-wide font-semibold mb-1">Sentiment</p>
              <p className="text-xl sm:text-2xl font-display font-bold text-white capitalize">
                {(report.review_summary.overall_sentiment || 'mixed or unclear')
                  .replace(/_/g, ' ')
                  .replace(/^unknown$/i, 'Mixed or unclear')}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {(report.review_summary.green_flags || []).map((f: string, i: number) => (
              <span
                key={`g-${i}`}
                className="max-w-full px-3 py-1.5 bg-green-500/10 text-green-400 text-xs font-medium rounded-xl border border-green-500/25 leading-snug break-words text-left"
              >
                <span className="mr-1 opacity-90">✓</span>
                {f}
              </span>
            ))}
            {(report.review_summary.red_flags || []).map((f: string, i: number) => (
              <span
                key={`r-${i}`}
                className="max-w-full px-3 py-1.5 bg-red-500/10 text-red-400 text-xs font-medium rounded-xl border border-red-500/25 leading-snug break-words text-left"
              >
                <span className="mr-1 opacity-90">⚠</span>
                {f}
              </span>
            ))}
          </div>

          <div className="rounded-2xl bg-neutral-900/40 border border-border/80 p-4 md:p-5">
            <p className="text-[13px] sm:text-sm text-neutral-300 leading-[1.65]">
              {sanitizeReputationPlainSummary(report.review_summary.plain_summary)}
            </p>
            {reputationSourcesLine ? (
              <p className="text-[11px] mt-3 leading-snug text-[#525252]">{reputationSourcesLine}</p>
            ) : null}
          </div>

          {report.review_summary.reddit &&
            typeof report.review_summary.reddit === 'object' &&
            report.review_summary.reddit.found === true && (
              <div className="rounded-2xl border border-border/80 bg-neutral-900/30 p-4 space-y-2">
                <p className="text-xs font-bold uppercase tracking-wide text-neutral-400">Reddit vibe</p>
                <p className="text-sm text-neutral-200 capitalize">
                  {String((report.review_summary.reddit as { sentiment?: string }).sentiment || 'mixed')}
                </p>
                <ul className="text-xs text-neutral-500 space-y-1 list-disc pl-4">
                  {(
                    (report.review_summary.reddit as { notable_phrases?: { text?: string }[] }).notable_phrases || []
                  )
                    .slice(0, 3)
                    .map((ph, j) => (
                      <li key={j}>{ph.text || ''}</li>
                    ))}
                </ul>
              </div>
            )}

          {report.review_summary.x_twitter &&
            typeof report.review_summary.x_twitter === 'object' &&
            report.review_summary.x_twitter.found === true && (
              <div className="rounded-2xl border border-border/80 bg-neutral-900/30 p-4 space-y-2">
                <p className="text-xs font-bold uppercase tracking-wide text-neutral-400">X (Twitter) vibe</p>
                <p className="text-sm text-neutral-200 capitalize">
                  {String((report.review_summary.x_twitter as { sentiment?: string }).sentiment || 'mixed')}
                </p>
                <ul className="text-xs text-neutral-500 space-y-1 list-disc pl-4">
                  {(
                    (report.review_summary.x_twitter as { notable_phrases?: { text?: string }[] }).notable_phrases || []
                  )
                    .slice(0, 2)
                    .map((ph, j) => (
                      <li key={j}>{ph.text || ''}</li>
                    ))}
                </ul>
              </div>
            )}
        </div>
        );
      })()}
    </>
  );
}

export function SimilarJobsPanel({ report }: { report: SanitizedVerifyReport }) {
  if (report.hideSimilarJobs) return null;
  if (report.similar_jobs && report.similar_jobs.length === 0 && report.similarJobsEmptyMessage) {
    return (
      <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 border border-border/60">
        <h3 className="text-lg font-bold mb-2">Similar roles we checked</h3>
        <p className="text-sm text-neutral-400 leading-relaxed">{report.similarJobsEmptyMessage}</p>
      </div>
    );
  }
  if (!report.similar_jobs || report.similar_jobs.length === 0) return null;
  return (
    <div className="glass rounded-3xl p-6 md:p-8 space-y-6 border border-border/60">
      <h3 className="text-lg font-bold">Similar roles we checked</h3>
      <div className="space-y-4">
        {report.similar_jobs.map((job, i: number) => {
          const href = typeof job.url === 'string' ? job.url.trim() : '';
          const ok = isSafeHttpUrl(href);
          const inner = (
            <>
              <div className="flex justify-between items-start mb-2 gap-2">
                <h4 className="font-bold text-white group-hover:text-brand transition-colors truncate pr-2">
                  {job.title || 'Role'}
                </h4>
                <ExternalLink className="w-4 h-4 text-neutral-600 shrink-0" />
              </div>
              <p className="text-sm text-neutral-400 mb-3">{job.company || ''}</p>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span
                  className={cn(
                    'text-[10px] font-bold uppercase px-2 py-0.5 rounded-md',
                    job.verdict === 'APPLY'
                      ? 'bg-[#F0FDF4]/20 text-[#16A34A]'
                      : 'bg-[#FFFBEB]/20 text-[#D97706]',
                  )}
                >
                  {job.verdict || 'VERIFY'}
                </span>
                <span className="text-[10px] text-neutral-600 font-bold uppercase">
                  {job.confidence_score != null ? `${job.confidence_score}% confidence` : ''}
                </span>
              </div>
            </>
          );
          return ok ? (
            <a
              key={i}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="block p-4 bg-neutral-900/50 border border-border rounded-2xl hover:border-brand/50 transition-all group"
            >
              {inner}
            </a>
          ) : (
            <div key={i} className="group block p-4 bg-neutral-900/50 border border-border rounded-2xl opacity-80">
              {inner}
              <p className="text-xs text-amber-400 mt-2">Link unavailable</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function verdictNextStepLine(verdict: string): string {
  switch (verdict) {
    case 'APPLY':
      return 'Next: confirm the role on the employer careers site before you share IDs, bank details, or pay any fee.';
    case 'SKIP':
      return 'Next: avoid this listing for applications unless independent facts change the picture.';
    default:
      return 'Next: open the employer careers site (or the board application link) and confirm the posting matches before you apply.';
  }
}

export function ResultsActionsFooter({
  report,
  onReanalyse,
}: {
  report: SanitizedVerifyReport;
  onReanalyse: () => void;
}) {
  return (
    <div className="glass rounded-2xl px-4 py-3 md:px-5 flex flex-col gap-2 border border-border/60">
      <p className="text-xs text-neutral-300 leading-snug">{verdictNextStepLine(report.verdict)}</p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-neutral-600 truncate max-w-[min(100%,16rem)]">
          Request id and scores live under Technical details.
        </p>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {report.cached ? (
            <button
              type="button"
              onClick={onReanalyse}
              className="text-xs font-semibold min-h-[36px] px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:bg-neutral-700 hover:text-white transition-colors border border-border/60"
            >
              Re-analyse (bypass cache)
            </button>
          ) : null}
          <button type="button" className="text-xs text-brand font-semibold hover:underline shrink-0">
            Report issue
          </button>
        </div>
      </div>
    </div>
  );
}
