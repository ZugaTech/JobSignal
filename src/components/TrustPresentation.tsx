import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Gauge, Globe, Microscope } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import type { DisplaySignalRow, SanitizedVerifyReport } from '../types/verify';
import {
  getStatusLabel,
  rewriteMicrocopy,
  sanitizeEvidenceDetailForDisplay,
  signalStrengthDotClass,
} from '../utils/formatters';
import {
  GROUP_LABELS,
  groupDisplaySignals,
  rowPrimaryLabel,
  type TrustEvidenceBucket,
} from '../utils/evidenceGroups';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function verdictHeroSubtitle(verdict: string): string {
  switch (verdict) {
    case 'APPLY':
      return 'Public checks looked good for a real listing. Still protect your personal info until you are sure.';
    case 'SKIP':
      return 'We would walk away unless you find new facts that change the picture.';
    default:
      return 'We could not fully confirm this from public data alone. Peek at the employer careers site before you go deep on an application.';
  }
}

function ScoreMetricBar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="space-y-1.5 min-w-0">
      <div className="flex justify-between gap-2 text-[11px] text-neutral-400">
        <span className="truncate">{label}</span>
        <span className="tabular-nums text-neutral-300 shrink-0">{v}</span>
      </div>
      <div className="h-2 bg-neutral-800 rounded-full overflow-hidden">
        <div className="h-full bg-brand/75 rounded-full transition-all" style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function EvidenceScoresInner({ report }: { report: SanitizedVerifyReport }) {
  const band = report.verdict_confidence_band;
  const bandLabel = band ? band.charAt(0).toUpperCase() + band.slice(1) : 'N/A';
  const hasLayers =
    report.company_legitimacy_score > 0 ||
    report.posting_authenticity_score > 0 ||
    report.freshness_score > 0;

  return (
    <div className="space-y-4 pt-2 border-t border-border/40">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="text-xs text-neutral-500 leading-snug max-w-xl">
          Layer scores summarize how strongly employer, posting, and freshness checks lined up. They inform the
          recommendation; they do not replace your judgment.
        </p>
        <div className="text-right text-xs text-neutral-400 space-y-1 shrink-0">
          <p>
            <span className="text-neutral-500">Confidence band </span>
            <span className="text-neutral-100 font-semibold">{bandLabel}</span>
          </p>
          <p>
            <span className="text-neutral-500">Overall strength </span>
            <span className="font-mono tabular-nums text-neutral-100">{report.confidence_score}/100</span>
          </p>
        </div>
      </div>

      {!hasLayers && report.total_signal_count === 0 ? (
        <p className="text-sm text-neutral-500">No layer scores were produced for this run.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <ScoreMetricBar label="Employer alignment" value={report.company_legitimacy_score} />
          <ScoreMetricBar label="Posting authenticity" value={report.posting_authenticity_score} />
          <ScoreMetricBar label="Freshness" value={report.freshness_score} />
        </div>
      )}

      {report.staleness_flag ? (
        <p className="text-xs text-amber-400/90 leading-snug">
          Listing-age hints suggest the post may be older than ideal. Treat timing as a softer signal.
        </p>
      ) : null}

      {report.total_signal_count > 0 ? (
        <p className="text-xs text-neutral-500 leading-snug">
          Supporting metric: {report.verified_signal_count}/{report.total_signal_count} checks resolved (
          {report.coverage_pct}%).
        </p>
      ) : null}

      {report.scorer_version_display ? (
        <p className="text-[10px] text-neutral-600 font-mono">Rules version {report.scorer_version_display}</p>
      ) : null}
    </div>
  );
}

export function TechnicalDetailsAccordion({ report }: { report: SanitizedVerifyReport }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl border border-border/50 bg-neutral-950/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-neutral-900/50 transition-colors min-h-[48px]"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Microscope className="w-4 h-4 text-neutral-500 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-neutral-200">Technical details</p>
            <p className="text-[11px] text-neutral-500 truncate">
              Extra depth if you want it: scores, coverage, request id.
            </p>
          </div>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-neutral-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-neutral-500 shrink-0" />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-border/40"
          >
            <div className="px-4 pb-4 pt-2 space-y-4">
              <EvidenceScoresInner report={report} />
              <div className="rounded-xl bg-neutral-900/60 border border-border/60 px-3 py-2.5 space-y-1">
                <p className="text-[11px] text-neutral-500 font-mono break-all">Request {report.request_id || 'N/A'}</p>
                {report.cached ? (
                  <p className="text-[11px] text-neutral-600">Result served from cache for this input.</p>
                ) : null}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

/** Collapsed by default so mobile users reach reputation before a long evidence list. */
export function EvidenceOverviewAccordion({
  hideSignalsSection,
  rows,
  summaryLine,
}: {
  hideSignalsSection: boolean;
  rows: DisplaySignalRow[];
  summaryLine: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl border border-border/50 bg-neutral-950/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-neutral-900/50 transition-colors min-h-[48px]"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Globe className="w-4 h-4 text-neutral-500 shrink-0" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-neutral-200">Evidence overview</p>
            <p className="text-[11px] text-neutral-500 leading-snug">
              {hideSignalsSection
                ? 'Structured checks were not returned for this run.'
                : 'Tap to expand how each public check landed.'}
            </p>
          </div>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-neutral-500 shrink-0" aria-hidden />
        ) : (
          <ChevronDown className="w-4 h-4 text-neutral-500 shrink-0" aria-hidden />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-border/40"
          >
            <div className="px-4 pb-4 pt-2">
              {hideSignalsSection ? (
                <p className="text-sm text-neutral-500">
                  No structured evidence rows were returned for this check.
                </p>
              ) : (
                <GroupedEvidenceSections rows={rows} summaryLine={summaryLine} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

export function GroupedEvidenceSections({
  rows,
  summaryLine,
}: {
  rows: DisplaySignalRow[];
  summaryLine: string;
}) {
  const grouped = groupDisplaySignals(rows);
  const order: TrustEvidenceBucket[] = ['verified', 'caution', 'limited'];

  return (
    <div className="space-y-6">
      <p className="text-sm text-neutral-400 leading-snug">{summaryLine}</p>
      {order.map((bucket) => {
        const sectionRows = grouped[bucket];
        if (!sectionRows.length) return null;
        const meta = GROUP_LABELS[bucket];
        return (
          <div key={bucket} className="space-y-3">
            <div className="border-l-2 border-brand/40 pl-3">
              <h4 className="text-xs font-bold uppercase tracking-widest text-neutral-400">{meta.title}</h4>
              <p className="text-[11px] text-neutral-500 mt-0.5 leading-snug">{meta.subtitle}</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {sectionRows.map((sig, i) => {
                const title = rowPrimaryLabel(sig);
                const statusText =
                  sig.kind === 'pipeline' ? getStatusLabel(sig.strength) : getStatusLabel(sig.status);
                const raw = sig.kind === 'pipeline' ? sig.strength : sig.status;
                const chroma = signalStrengthDotClass(raw);
                const dot =
                  chroma === 'green'
                    ? 'bg-[#16A34A]'
                    : chroma === 'amber'
                      ? 'bg-[#D97706]'
                      : chroma === 'red'
                        ? 'bg-[#DC2626]'
                        : 'bg-neutral-700';
                const detailText =
                  sig.detail &&
                  sanitizeEvidenceDetailForDisplay(
                    sig.kind === 'pipeline' ? sig.id : undefined,
                    rewriteMicrocopy(sig.detail),
                  );
                return (
                  <div
                    key={`${bucket}-${i}-${title}`}
                    className="bg-neutral-900/45 border border-border/70 rounded-xl p-4 flex items-start justify-between gap-3"
                  >
                    <div className="space-y-1 min-w-0">
                      <p className="text-xs text-neutral-500 uppercase font-semibold tracking-tight line-clamp-2 break-words">
                        {title}
                      </p>
                      <p className="text-sm text-neutral-200 break-words">{statusText}</p>
                      {detailText ? (
                        <p className="text-xs text-neutral-500 line-clamp-4 break-words">{detailText}</p>
                      ) : null}
                    </div>
                    <div className={cn('w-2 h-2 rounded-full shrink-0 mt-1', dot)} aria-hidden />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Compact gauge strip for hero (avoids shouting "Composite" in primary UX). */
export function ConfidenceGaugeStrip({
  score,
  labelText,
}: {
  score: number;
  labelText: string;
}) {
  return (
    <div className="flex flex-col items-stretch md:items-end gap-2 w-full md:w-auto md:min-w-[200px] md:text-right">
      <div className="flex items-center gap-2 md:justify-end text-neutral-400">
        <Gauge className="w-4 h-4 opacity-70" aria-hidden />
        <p className="text-lg font-display font-semibold text-white leading-tight">{labelText}</p>
      </div>
      <div className="w-full h-2 bg-neutral-800 rounded-full overflow-hidden mt-1">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(0, Math.min(100, score))}%` }}
          className={cn(
            'h-full rounded-full',
            score < 34 ? 'bg-[#DC2626]' : score < 67 ? 'bg-[#D97706]' : 'bg-[#16A34A]',
          )}
        />
      </div>
    </div>
  );
}
