import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, FileText, Image as ImageIcon, Clipboard, X, Loader2, CheckCircle2, AlertCircle, ArrowRight, ShieldCheck, Globe, Building2, ExternalLink, ChevronDown, ChevronUp, Info, ListOrdered } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Utility for Tailwind classes */
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

import { useJobSignal } from './hooks/useJobSignal';
import { useBatchVerify } from './hooks/useBatchVerify';
import { useClipboardAndHandoff } from './hooks/useClipboardAndHandoff';
import {
  getSignalLabel,
  getStatusLabel,
  rewriteMicrocopy,
  formatCachedAgo,
  signalStrengthDotClass,
  isSafeHttpUrl,
} from './utils/formatters';
import type { SanitizedVerifyReport } from './types/verify';

// --- COMPONENTS ---

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

function EvidenceScoresPanel({ report }: { report: SanitizedVerifyReport }) {
  const band = report.verdict_confidence_band;
  const bandLabel = band ? band.charAt(0).toUpperCase() + band.slice(1) : '—';
  const hasLayers =
    report.company_legitimacy_score > 0 ||
    report.posting_authenticity_score > 0 ||
    report.freshness_score > 0;

  return (
    <section
      className="rounded-2xl border border-border/60 bg-neutral-900/35 p-4 sm:p-5 md:p-6 space-y-4"
      aria-label="Evidence scores from verification engine"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h3 className="text-sm font-bold text-white tracking-tight">Evidence scores</h3>
          <p className="text-xs text-neutral-500 leading-snug max-w-xl">
            Layer scores and composite strength from this run. Employer reputation (when available) is shown separately
            in the right column.
          </p>
        </div>
        <div className="text-right text-xs text-neutral-400 space-y-1 shrink-0">
          <p>
            <span className="text-neutral-500">Verdict band </span>
            <span className="text-neutral-100 font-semibold">{bandLabel}</span>
          </p>
          <p>
            <span className="text-neutral-500">Strength </span>
            <span className="font-mono tabular-nums text-neutral-100">{report.confidence_score}/100</span>
          </p>
        </div>
      </div>

      {!hasLayers && report.total_signal_count === 0 ? (
        <p className="text-sm text-neutral-500">No scored layers were returned for this check.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <ScoreMetricBar label="Company signals" value={report.company_legitimacy_score} />
          <ScoreMetricBar label="Posting signals" value={report.posting_authenticity_score} />
          <ScoreMetricBar label="Freshness" value={report.freshness_score} />
        </div>
      )}

      {report.staleness_flag ? (
        <p className="text-xs text-amber-400/90 leading-snug">
          Listing-age signal suggests possible staleness—use freshness as a weaker signal for this run.
        </p>
      ) : null}

      {report.total_signal_count > 0 ? (
        <p className="text-xs text-neutral-500 leading-snug">
          {`Signal coverage: ${report.verified_signal_count}/${report.total_signal_count} checks resolved (${report.coverage_pct}%).`}
        </p>
      ) : null}

      {report.scorer_version_display ? (
        <p className="text-[10px] text-neutral-600 font-mono">Scorer {report.scorer_version_display}</p>
      ) : null}
    </section>
  );
}

const Header = () => (
  <header className="flex items-center justify-between gap-3 px-4 sm:px-6 pb-3 sm:pb-4 pt-[max(0.75rem,env(safe-area-inset-top,0px))] border-b border-border glass sticky top-0 z-50 min-w-0">
    <div className="flex items-center gap-2 min-w-0 shrink">
      <div className="bg-brand rounded-lg p-1.5 shrink-0">
        <ShieldCheck className="w-6 h-6 text-white" />
      </div>
      <div className="text-lg sm:text-xl font-display font-bold truncate">
        <span>Job</span><span className="text-brand">Signal</span>
      </div>
    </div>
    <nav className="flex items-center gap-2 sm:gap-6 shrink-0">
      <a
        href="#how"
        className="text-xs sm:text-sm text-neutral-400 hover:text-white transition-colors py-2 px-2 min-h-[44px] flex items-center rounded-lg hover:bg-neutral-800/50"
      >
        <span className="sm:hidden">How</span>
        <span className="hidden sm:inline">How it works</span>
      </a>
      <a
        href="https://github.com/ZugaTech/JobSignal"
        target="_blank"
        rel="noreferrer"
        className="text-xs sm:text-sm text-neutral-400 hover:text-white transition-colors py-2 px-2 min-h-[44px] flex items-center rounded-lg hover:bg-neutral-800/50"
      >
        GitHub
      </a>
    </nav>
  </header>
);

const Footer = () => (
  <footer className="py-10 sm:py-12 px-4 sm:px-6 border-t border-border mt-16 sm:mt-20 pb-safe">
    <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
      <div className="flex items-center gap-2 opacity-50">
        <ShieldCheck className="w-5 h-5" />
        <span className="text-sm font-display font-bold">JobSignal</span>
      </div>
      <div className="text-sm text-neutral-500">
        &copy; 2026 JobSignal. Built for AMD &times; LabLab AI.
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2 justify-center items-center">
        <a href="#" className="text-xs text-neutral-500 hover:text-white min-h-[44px] flex items-center px-1">
          Privacy Policy
        </a>
        <a href="#" className="text-xs text-neutral-500 hover:text-white min-h-[44px] flex items-center px-1">
          Terms of Service
        </a>
      </div>
    </div>
  </footer>
);

const TabButton = ({ active, onClick, icon: Icon, label }: { active: boolean, onClick: () => void, icon: any, label: string }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-full text-sm font-medium transition-all shrink-0 snap-start touch-manipulation',
      active 
        ? 'bg-brand text-white shadow-lg shadow-brand/20' 
        : 'text-neutral-400 hover:text-white hover:bg-neutral-800 active:bg-neutral-800'
    )}
  >
    <Icon className="w-4 h-4 shrink-0" />
    <span className="whitespace-nowrap">{label}</span>
  </button>
);

export default function App() {
  const [activeTab, setActiveTab] = useState<'url' | 'text' | 'image' | 'batch'>('url');
  const [jobUrl, setJobUrl] = useState('');
  const [jobText, setJobText] = useState('');
  const [batchUrls, setBatchUrls] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [includeSimilar, setIncludeSimilar] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { phase, report, error, loadingStep, elapsed, verify, reanalyseBypassCache, hydrateReport, reset } = useJobSignal();
  const {
    phase: batchPhase,
    rows: batchRows,
    sortedShortlist,
    error: batchError,
    runBatch,
    resetBatch,
  } = useBatchVerify();

  const handleCloseResults = useCallback(() => {
    resetBatch();
    reset();
  }, [reset, resetBatch]);

  useEffect(() => {
    const overlayOpen = phase === 'success' || batchPhase !== 'idle';
    if (!overlayOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleCloseResults();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, batchPhase, handleCloseResults]);

  const { pendingClipboard, dismissClipboard, confirmClipboard } = useClipboardAndHandoff((data: any) => {
    if (data.url) {
      setJobUrl(data.url);
      setActiveTab('url');
    }
    if (data.cachedResult) {
      hydrateReport(data.cachedResult);
      return;
    }
    if (data.text) {
      setJobText(data.text);
      if (!data.url) setActiveTab('text');
    }
    if (data.batch) {
      setBatchUrls(data.batch.join('\n'));
      setActiveTab('batch');
    }
    
    // Auto-run if we got data from handoff/clipboard
    if (data.url || data.text) {
      setTimeout(() => {
        verify({ 
          url: data.url, 
          text: data.text, 
          includeSimilarJobs: includeSimilar 
        });
      }, 100);
    }
  });

  const handleVerify = () => {
    if (activeTab === 'url') verify({ url: jobUrl, includeSimilarJobs: includeSimilar });
    else if (activeTab === 'text') verify({ text: jobText, includeSimilarJobs: includeSimilar });
    else if (activeTab === 'image') verify({ file, includeSimilarJobs: includeSimilar });
    else if (activeTab === 'batch') {
      const urls = [...new Set(batchUrls.split('\n').map((u) => u.trim()).filter(Boolean))];
      if (!urls.length) return;
      void runBatch(urls, { includeSimilarJobs: includeSimilar });
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) setFile(selectedFile);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type.startsWith('image/')) setFile(droppedFile);
  };

  return (
    <div className="min-h-[100dvh] min-h-screen flex flex-col min-w-0 overflow-x-clip">
      <Header />
      
      <main className="flex-grow max-w-4xl mx-auto w-full min-w-0 px-4 sm:px-6 py-8 sm:py-12 md:py-20">
        <AnimatePresence>
          {pendingClipboard && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="mb-8 bg-brand/10 border border-brand/20 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="flex items-start sm:items-center gap-3 min-w-0">
                <div className="bg-brand rounded-full p-2">
                  <Clipboard className="w-4 h-4 text-white" />
                </div>
                <p className="text-sm text-neutral-300 leading-snug">
                  Job {pendingClipboard.type === 'url' ? 'link' : 'description'} detected in clipboard.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:justify-end">
                <button 
                  type="button"
                  onClick={confirmClipboard}
                  className="min-h-[44px] px-4 py-2.5 bg-brand text-white text-xs font-bold rounded-lg hover:bg-brand-dark transition-colors touch-manipulation"
                >
                  Analyze Now
                </button>
                <button 
                  type="button"
                  onClick={dismissClipboard}
                  className="min-h-[44px] px-4 py-2.5 bg-neutral-800 text-neutral-400 text-xs font-bold rounded-lg hover:bg-neutral-700 transition-colors touch-manipulation"
                >
                  Dismiss
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-10 sm:mb-12 px-1"
        >
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-display font-bold mb-4 tracking-tight leading-tight">
            Verify any job <span className="text-brand">instantly</span>
          </h1>
          <p className="text-base sm:text-lg text-neutral-400 max-w-2xl mx-auto leading-relaxed">
            Multi-source checks on URLs, pasted text, and screenshots—flag ghost listings, stale posts, and low-trust
            patterns before you invest time.
          </p>
        </motion.div>

        <div className="glass rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 shadow-2xl relative overflow-hidden">
          {/* Decorative background glow */}
          <div className="absolute -top-24 -right-24 w-64 h-64 bg-brand/10 blur-[100px] rounded-full pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-brand/5 blur-[100px] rounded-full pointer-events-none" />

          <div className="flex flex-nowrap gap-2 mb-8 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-hide snap-x snap-mandatory justify-start sm:flex-wrap sm:justify-center sm:overflow-visible">
            <TabButton active={activeTab === 'url'} onClick={() => setActiveTab('url')} icon={Search} label="Paste URL" />
            <TabButton active={activeTab === 'text'} onClick={() => setActiveTab('text')} icon={FileText} label="Description" />
            <TabButton active={activeTab === 'image'} onClick={() => setActiveTab('image')} icon={ImageIcon} label="Screenshot" />
            <TabButton active={activeTab === 'batch'} onClick={() => setActiveTab('batch')} icon={Clipboard} label="Batch" />
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.2 }}
              className="space-y-6"
            >
              {activeTab === 'url' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-400 ml-1">Job Posting URL</label>
                  <div className="relative group">
                    <input
                      type="url"
                      inputMode="url"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck={false}
                      enterKeyHint="go"
                      value={jobUrl}
                      onChange={(e) => setJobUrl(e.target.value)}
                      placeholder="https://linkedin.com/jobs/view/..."
                      className="w-full min-h-[48px] bg-neutral-900/50 border border-border rounded-2xl px-5 py-3.5 pr-12 text-base focus:outline-none focus:ring-2 focus:ring-brand/50 transition-all group-hover:border-neutral-700"
                    />
                    <Search className="absolute right-5 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-600 group-focus-within:text-brand transition-colors" />
                  </div>
                </div>
              )}

              {activeTab === 'text' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-400 ml-1">Job Description</label>
                  <textarea
                    value={jobText}
                    onChange={(e) => setJobText(e.target.value)}
                    placeholder="Paste the full job requirements and description here..."
                    rows={6}
                    className="w-full min-h-[160px] bg-neutral-900/50 border border-border rounded-2xl px-5 py-4 text-base focus:outline-none focus:ring-2 focus:ring-brand/50 transition-all hover:border-neutral-700 resize-y"
                  />
                  <p className="text-xs text-neutral-500 italic ml-1 flex items-center gap-1">
                    <Info className="w-3 h-3" />
                    Include company name for full employer verification.
                  </p>
                </div>
              )}

              {activeTab === 'image' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-400 ml-1">Upload Screenshot</label>
                  <div 
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={onDrop}
                    className={cn(
                      'border-2 border-dashed border-border rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all hover:bg-neutral-900/50 hover:border-brand/50 group touch-manipulation min-h-[180px] flex flex-col items-center justify-center',
                      file && "border-brand/50 bg-brand/5"
                    )}
                  >
                    <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
                    <div className="flex flex-col items-center gap-4">
                      {file ? (
                        <>
                          <div className="w-16 h-16 bg-brand/20 rounded-2xl flex items-center justify-center">
                            <CheckCircle2 className="w-8 h-8 text-brand" />
                          </div>
                          <div>
                            <p className="font-medium text-white break-all text-left">{file.name}</p>
                            <p className="text-sm text-neutral-500">{(file.size / 1024).toFixed(1)} KB</p>
                          </div>
                          <button 
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setFile(null); }}
                            className="text-xs text-neutral-500 hover:text-red-400 transition-colors min-h-[44px] px-2 touch-manipulation"
                          >
                            Remove file
                          </button>
                        </>
                      ) : (
                        <>
                          <div className="w-16 h-16 bg-neutral-800 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                            <ImageIcon className="w-8 h-8 text-neutral-500 group-hover:text-brand" />
                          </div>
                          <div>
                            <p className="font-medium text-white">Drag & drop or click to browse</p>
                            <p className="text-sm text-neutral-500">Supports PNG, JPG, WebP</p>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'batch' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-400 ml-1">Batch URLs (one per line)</label>
                  <textarea
                    value={batchUrls}
                    onChange={(e) => setBatchUrls(e.target.value)}
                    placeholder="https://linkedin.com/jobs/view/123&#10;https://indeed.com/viewjob?jk=456"
                    rows={6}
                    className="w-full min-h-[160px] bg-neutral-900/50 border border-border rounded-2xl px-5 py-4 text-base focus:outline-none focus:ring-2 focus:ring-brand/50 transition-all hover:border-neutral-700 resize-y font-mono text-[15px] sm:text-base"
                  />
                </div>
              )}
            </motion.div>
          </AnimatePresence>

          <div className="mt-8 pt-8 border-t border-border flex flex-col md:flex-row items-stretch md:items-center justify-between gap-6">
            <label className="flex items-center gap-3 cursor-pointer group min-h-[44px] py-1 touch-manipulation">
              <div className="relative">
                <input 
                  type="checkbox" 
                  checked={includeSimilar} 
                  onChange={(e) => setIncludeSimilar(e.target.checked)}
                  className="sr-only" 
                />
                <div className={cn(
                  "w-10 h-6 rounded-full transition-colors",
                  includeSimilar ? "bg-brand" : "bg-neutral-800"
                )} />
                <div className={cn(
                  "absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform",
                  includeSimilar ? "translate-x-4" : "translate-x-0"
                )} />
              </div>
              <span className="text-sm text-neutral-400 group-hover:text-neutral-200 transition-colors">
                Find similar verified roles
              </span>
            </label>

            <button
              type="button"
              onClick={handleVerify}
              disabled={phase === 'loading' || batchPhase === 'streaming'}
              className="w-full md:w-auto min-h-[48px] bg-brand hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-3.5 px-8 sm:px-10 rounded-2xl flex items-center justify-center gap-3 transition-all shadow-xl shadow-brand/20 active:scale-[0.98] touch-manipulation"
            >
              {phase === 'loading' || batchPhase === 'streaming' ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>{batchPhase === 'streaming' ? 'Running batch…' : 'Verifying...'}</span>
                </>
              ) : (
                <>
                  <span>Check Posting</span>
                  <ArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* --- LOADING MODAL --- */}
        <AnimatePresence>
          {phase === 'loading' && batchPhase === 'idle' && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[100] flex items-center justify-center px-4 py-6 pt-[max(1.5rem,env(safe-area-inset-top,0px))] pb-[max(1.5rem,env(safe-area-inset-bottom,0px))] bg-background/80 backdrop-blur-xl overscroll-y-contain"
            >
              <div className="max-w-md w-full text-center space-y-8">
                <div className="space-y-3 max-w-xs mx-auto">
                  <div className="h-3 rounded-full bg-neutral-800 animate-pulse w-4/5 mx-auto" />
                  <div className="h-3 rounded-full bg-neutral-800 animate-pulse w-full mx-auto" />
                  <div className="h-3 rounded-full bg-neutral-800 animate-pulse w-3/5 mx-auto" />
                </div>
                <div className="relative">
                  <div className="w-16 h-16 border-4 border-brand/20 border-t-brand rounded-full animate-spin mx-auto" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <ShieldCheck className="w-6 h-6 text-brand animate-pulse" />
                  </div>
                </div>
                <div className="space-y-2">
                  <h2 className="text-2xl font-display font-bold text-white">{loadingStep}</h2>
                  <p className="text-neutral-400 animate-pulse">This usually takes 5-10 seconds...</p>
                  <p className="text-xs text-neutral-600 font-mono">{elapsed}s elapsed</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* --- BATCH STREAM RESULTS --- */}
        <AnimatePresence>
          {batchPhase !== 'idle' && (
            <motion.div
              role="dialog"
              aria-modal="true"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="fixed inset-0 z-[101] overflow-y-auto overscroll-y-contain bg-background/95 backdrop-blur-md px-4 pt-[max(1rem,env(safe-area-inset-top,0px))] pb-[max(1.25rem,env(safe-area-inset-bottom,0px))] sm:px-6 md:p-8 min-h-[100dvh]"
              onClick={handleCloseResults}
            >
              <div
                className="max-w-7xl mx-auto space-y-6 pb-24 max-md:min-h-[100dvh] min-w-0"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between gap-4 glass px-4 py-3 md:px-6 rounded-2xl sticky top-[max(0.5rem,env(safe-area-inset-top,0px))] z-10 border border-border/80">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="bg-brand/15 rounded-lg p-2">
                      <ListOrdered className="w-5 h-5 text-brand" />
                    </div>
                    <div className="min-w-0">
                      <h2 className="text-lg font-display font-bold text-white truncate">Batch verification</h2>
                      <p className="text-xs text-neutral-500">
                        {batchPhase === 'streaming'
                          ? 'Results stream in as each URL finishes.'
                          : batchPhase === 'error'
                            ? 'Something went wrong.'
                            : 'Shortlist is sorted: Apply first, then Verify, then Skip.'}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleCloseResults}
                    className="shrink-0 min-h-[44px] min-w-[44px] inline-flex items-center justify-center hover:bg-neutral-800 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand/40"
                    aria-label="Close batch results"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {batchError && (
                  <div className="bg-red-500/10 border border-red-500/25 rounded-2xl px-4 py-3 text-sm text-red-200/90 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{batchError}</span>
                  </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 lg:items-start">
                  <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 border border-border/60 space-y-4">
                    <h3 className="text-sm font-bold uppercase tracking-widest text-neutral-500">Live progress</h3>
                    <ul className="space-y-3">
                      {batchRows.map((row) => (
                        <li
                          key={row.url}
                          className="flex items-start gap-3 rounded-xl border border-border/80 bg-neutral-900/40 px-3 py-3"
                        >
                          <div className="mt-0.5 shrink-0">
                            {row.status === 'pending' ? (
                              <Loader2 className="w-4 h-4 animate-spin text-brand" />
                            ) : row.ok ? (
                              <CheckCircle2 className="w-4 h-4 text-[#16A34A]" />
                            ) : (
                              <AlertCircle className="w-4 h-4 text-red-400" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs text-neutral-500 break-all">{row.url}</p>
                            {row.status === 'done' && row.ok && (
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span
                                  className={cn(
                                    'text-[10px] font-bold uppercase px-2 py-0.5 rounded-md border',
                                    row.report.verdict === 'APPLY'
                                      ? 'bg-[#F0FDF4]/15 text-[#16A34A] border-[#16A34A]/35'
                                      : row.report.verdict === 'SKIP'
                                        ? 'bg-[#FEF2F2]/15 text-[#DC2626] border-[#DC2626]/35'
                                        : 'bg-[#FFFBEB]/15 text-[#D97706] border-[#D97706]/35',
                                  )}
                                >
                                  {row.report.verdict}
                                </span>
                                <span className="text-[10px] text-neutral-500 font-mono">
                                  {row.report.confidence_score}% · {row.report.confidence_label}
                                </span>
                              </div>
                            )}
                            {row.status === 'done' && !row.ok && (
                              <p className="mt-2 text-xs text-red-300/90">{row.error}</p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 border border-border/60 space-y-4">
                    <h3 className="text-sm font-bold uppercase tracking-widest text-neutral-500 flex items-center gap-2">
                      <ListOrdered className="w-4 h-4 text-brand" />
                      Sorted shortlist
                    </h3>
                    {sortedShortlist.length === 0 ? (
                      <p className="text-sm text-neutral-500 leading-relaxed">
                        {batchPhase === 'streaming'
                          ? 'Successful results will appear here in priority order.'
                          : 'No successful verifications in this batch.'}
                      </p>
                    ) : (
                      <ul className="space-y-3">
                        {sortedShortlist.map(({ url, report: rep }) => {
                          const okLink = isSafeHttpUrl(url);
                          const inner = (
                            <>
                              <div className="flex justify-between items-start gap-2 mb-2">
                                <span
                                  className={cn(
                                    'text-[10px] font-bold uppercase px-2 py-0.5 rounded-md border shrink-0',
                                    rep.verdict === 'APPLY'
                                      ? 'bg-[#F0FDF4]/15 text-[#16A34A] border-[#16A34A]/35'
                                      : rep.verdict === 'SKIP'
                                        ? 'bg-[#FEF2F2]/15 text-[#DC2626] border-[#DC2626]/35'
                                        : 'bg-[#FFFBEB]/15 text-[#D97706] border-[#D97706]/35',
                                  )}
                                >
                                  {rep.verdict}
                                </span>
                                <span className="text-[10px] text-neutral-500 font-mono">
                                  {rep.confidence_score}% · {rep.confidence_label}
                                </span>
                              </div>
                              <p className="text-xs text-neutral-400 break-all">{url}</p>
                              {!okLink && (
                                <p className="text-[11px] text-amber-400 mt-2">Link unavailable</p>
                              )}
                            </>
                          );
                          return (
                            <li key={url}>
                              {okLink ? (
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="block rounded-xl border border-border bg-neutral-900/50 p-4 hover:border-brand/40 transition-colors"
                                >
                                  {inner}
                                </a>
                              ) : (
                                <div className="block rounded-xl border border-border bg-neutral-900/50 p-4">{inner}</div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* --- RESULTS VIEW --- */}
        <AnimatePresence>
          {phase === 'success' && report && batchPhase === 'idle' && (
            <motion.div
              role="dialog"
              aria-modal="true"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="fixed inset-0 z-[100] overflow-y-auto overscroll-y-contain bg-background/95 backdrop-blur-md px-4 pt-[max(1rem,env(safe-area-inset-top,0px))] pb-[max(1.25rem,env(safe-area-inset-bottom,0px))] sm:px-6 md:p-8 min-h-[100dvh]"
              onClick={handleCloseResults}
            >
              <div
                className="max-w-7xl mx-auto space-y-6 pb-24 max-md:min-h-[100dvh] min-w-0"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between gap-4 glass px-4 py-3 md:px-6 rounded-2xl sticky top-[max(0.5rem,env(safe-area-inset-top,0px))] z-10 border border-border/80 shadow-lg shadow-black/20">
                  <div className="flex items-center gap-3 min-w-0 flex-wrap">
                    <div
                      className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border',
                        report.verdict === 'APPLY'
                          ? 'bg-[#F0FDF4]/15 text-[#16A34A] border-[#16A34A]/35'
                          : report.verdict === 'SKIP'
                            ? 'bg-[#FEF2F2]/15 text-[#DC2626] border-[#DC2626]/35'
                            : 'bg-[#FFFBEB]/15 text-[#D97706] border-[#D97706]/35',
                      )}
                    >
                      {report.verdict}
                    </div>
                    {report.cached && (
                      <span className="text-xs text-neutral-500 flex items-center gap-1">
                        <Clipboard className="w-3 h-3" />
                        {formatCachedAgo(String(report.cached_at || report.data_freshness || ''))}
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleCloseResults}
                    className="shrink-0 min-h-[44px] min-w-[44px] inline-flex items-center justify-center hover:bg-neutral-800 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand/40"
                    aria-label="Close results"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 lg:items-start">
                  <div className="lg:col-span-7 space-y-6 min-w-0">
                    <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 space-y-8 border border-border/60">
                      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
                        <div className="min-w-0 flex-1">
                          <h2 className="text-sm font-medium text-neutral-500 uppercase tracking-widest mb-2">
                            Final Verdict
                          </h2>
                          <div
                            className={cn(
                              'text-3xl sm:text-5xl md:text-6xl font-display font-black tracking-tighter break-words',
                              report.verdict === 'APPLY'
                                ? 'text-[#16A34A]'
                                : report.verdict === 'SKIP'
                                  ? 'text-[#DC2626]'
                                  : 'text-[#D97706]',
                            )}
                          >
                            {report.verdict === 'APPLY'
                              ? 'Looks Good'
                              : report.verdict === 'SKIP'
                                ? 'Skip'
                                : 'Verify First'}
                          </div>
                        </div>
                        <div className="flex flex-col items-stretch md:items-end gap-2 w-full md:w-auto md:min-w-[180px] md:text-right">
                          <p className="text-lg font-display font-bold text-white leading-tight">
                            {report.confidence_label === 'None' || !report.confidence_label
                              ? 'Strength unavailable'
                              : `${report.confidence_label} confidence`}
                          </p>
                          <p className="text-xs text-neutral-500 tabular-nums">Composite {report.confidence_score}/100</p>
                          <div className="w-full h-2 bg-neutral-800 rounded-full overflow-hidden mt-1">
                            <motion.div
                              initial={{ width: 0 }}
                              animate={{ width: `${report.confidence_score}%` }}
                              className={cn(
                                'h-full rounded-full',
                                report.confidence_score < 34
                                  ? 'bg-[#DC2626]'
                                  : report.confidence_score < 67
                                    ? 'bg-[#D97706]'
                                    : 'bg-[#16A34A]',
                              )}
                            />
                          </div>
                        </div>
                      </div>

                      <EvidenceScoresPanel report={report} />

                      <div className="space-y-4">
                        <h3 className="text-lg font-bold flex items-center gap-2">
                          <Info className="w-5 h-5 text-brand" />
                          Analysis Summary
                        </h3>
                        <p className="text-neutral-300 leading-relaxed text-base md:text-lg">
                          {rewriteMicrocopy(report.llm_summary)}
                        </p>
                      </div>

                      <div className="space-y-4">
                        <h3 className="text-lg font-bold">Why this verdict?</h3>
                        <ul className="space-y-3">
                          {report.reasons.map((reason: string, i: number) => (
                            <li key={i} className="flex gap-3 text-neutral-400 leading-relaxed">
                              <div className="mt-2 w-1.5 h-1.5 rounded-full bg-brand shrink-0" />
                              <span>{rewriteMicrocopy(reason)}</span>
                            </li>
                          ))}
                        </ul>
                      </div>

                      {report.warnings && report.warnings.length > 0 && (
                        <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-6 space-y-3">
                          <h3 className="text-amber-400 font-bold flex items-center gap-2">
                            <AlertCircle className="w-5 h-5" />
                            Keep in mind
                          </h3>
                          <ul className="space-y-2">
                            {report.warnings.map((w: string, i: number) => (
                              <li key={i} className="text-sm text-amber-200/70 flex gap-2">
                                <span>•</span>
                                <span>{rewriteMicrocopy(w)}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 border border-border/60">
                      <button
                        type="button"
                        onClick={() => setShowSignals(!showSignals)}
                        className="flex flex-col gap-2 w-full text-left group sm:flex-row sm:items-start sm:justify-between"
                      >
                        <div className="space-y-1 min-w-0">
                          <h3 className="text-lg font-bold flex items-center gap-2">
                            <Globe className="w-5 h-5 text-brand shrink-0" />
                            Verification Signals
                          </h3>
                          {!report.hideSignalsSection && (
                            <p className="text-sm text-neutral-500 leading-snug pr-2">
                              {report.signals_summary_line}
                            </p>
                          )}
                        </div>
                        <div className="shrink-0 self-end sm:self-start pt-1">
                          {showSignals ? (
                            <ChevronUp className="text-neutral-600 group-hover:text-white" />
                          ) : (
                            <ChevronDown className="text-neutral-600 group-hover:text-white" />
                          )}
                        </div>
                      </button>

                      {report.hideSignalsSection ? (
                        <p className="text-sm text-neutral-500 mt-4">No signal breakdown was returned for this check.</p>
                      ) : (
                        <AnimatePresence>
                          {showSignals && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="overflow-hidden"
                            >
                              <div className="pt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                                {report.display_signal_rows.map((sig, i: number) => {
                                  const bucket = signalStrengthDotClass(
                                    sig.kind === 'pipeline' ? sig.strength : sig.status,
                                  );
                                  const dot =
                                    bucket === 'green'
                                      ? 'bg-[#16A34A] shadow-[0_0_8px] shadow-[#16A34A]/50'
                                      : bucket === 'amber'
                                        ? 'bg-[#D97706] shadow-[0_0_8px] shadow-[#D97706]/50'
                                        : bucket === 'red'
                                          ? 'bg-[#DC2626] shadow-[0_0_8px] shadow-[#DC2626]/50'
                                          : 'bg-neutral-700 shadow-transparent';
                                  const title =
                                    sig.kind === 'pipeline' ? getSignalLabel(sig.id) : sig.name;
                                  const statusText =
                                    sig.kind === 'pipeline'
                                      ? getStatusLabel(sig.strength)
                                      : sig.status;
                                  return (
                                    <div
                                      key={i}
                                      className="bg-neutral-900/50 border border-border rounded-xl p-4 flex items-center justify-between gap-3"
                                    >
                                      <div className="space-y-1 min-w-0">
                                        <p className="text-xs text-neutral-500 uppercase font-bold tracking-tighter truncate">
                                          {title}
                                        </p>
                                        <p className="text-sm text-neutral-300">{statusText}</p>
                                        {sig.detail ? (
                                          <p className="text-xs text-neutral-600 line-clamp-3">{sig.detail}</p>
                                        ) : null}
                                      </div>
                                      <div className={cn('w-2 h-2 rounded-full shrink-0', dot)} />
                                    </div>
                                  );
                                })}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      )}
                    </div>
                  </div>

                  <div className="lg:col-span-5 space-y-6 min-w-0">
                    {report.reputationPanelVariant === 'unavailable' && (
                      <div className="glass rounded-3xl p-6 md:p-8 space-y-3 border border-border/60">
                        <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
                          <Building2 className="w-5 h-5 text-brand shrink-0" />
                          Company trust
                        </h3>
                        <p className="text-sm text-neutral-400 leading-relaxed">
                          Employer reputation data unavailable for this employer or query.
                        </p>
                      </div>
                    )}

                    {report.reputationPanelVariant === 'no_company' && (
                      <div className="glass rounded-3xl p-6 md:p-8 space-y-3 border border-border/60">
                        <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
                          <Building2 className="w-5 h-5 text-brand shrink-0" />
                          Company trust
                        </h3>
                        <p className="text-sm text-neutral-400 leading-relaxed">
                          We could not identify a clear employer from this input, so reputation signals were not loaded.
                        </p>
                      </div>
                    )}

                    {report.reputationPanelVariant === 'full' && report.review_summary && (
                      <div className="glass rounded-3xl p-6 md:p-8 space-y-6 border border-border/60 ring-1 ring-white/[0.04]">
                        <div>
                          <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
                            <Building2 className="w-5 h-5 text-brand shrink-0" />
                            Company trust
                          </h3>
                          <p className="text-xs text-neutral-500 mt-1.5 leading-snug">
                            Public employer signals — separate from this posting&apos;s job confidence.
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
                                : '—'}
                            </span>
                            <span className="text-[10px] uppercase font-semibold tracking-wide opacity-70 mt-1">
                              Score
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs text-neutral-500 uppercase tracking-wide font-semibold mb-1">
                              Sentiment
                            </p>
                            <p className="text-xl sm:text-2xl font-display font-bold text-white capitalize">
                              {(report.review_summary.overall_sentiment || 'unknown').replace('_', ' ')}
                            </p>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {(report.review_summary.green_flags || []).map((f: string, i: number) => (
                            <span
                              key={`g-${i}`}
                              className="px-3 py-1.5 bg-green-500/10 text-green-400 text-xs font-medium rounded-xl border border-green-500/25 leading-snug"
                            >
                              <span className="mr-1 opacity-90">✓</span>
                              {f}
                            </span>
                          ))}
                          {(report.review_summary.red_flags || []).map((f: string, i: number) => (
                            <span
                              key={`r-${i}`}
                              className="px-3 py-1.5 bg-red-500/10 text-red-400 text-xs font-medium rounded-xl border border-red-500/25 leading-snug"
                            >
                              <span className="mr-1 opacity-90">⚠</span>
                              {f}
                            </span>
                          ))}
                        </div>

                        <div className="rounded-2xl bg-neutral-900/40 border border-border/80 p-4 md:p-5">
                          <p className="text-[13px] sm:text-sm text-neutral-300 leading-[1.65]">
                            {rewriteMicrocopy(report.review_summary.plain_summary || '')}
                          </p>
                        </div>

                        {report.review_summary.reddit &&
                          typeof report.review_summary.reddit === 'object' &&
                          report.review_summary.reddit.found === true && (
                            <div className="rounded-2xl border border-border/80 bg-neutral-900/30 p-4 space-y-2">
                              <p className="text-xs font-bold uppercase tracking-wide text-neutral-400">
                                Reddit sentiment
                              </p>
                              <p className="text-sm text-neutral-200 capitalize">
                                {String((report.review_summary.reddit as { sentiment?: string }).sentiment || 'mixed')}
                              </p>
                              <ul className="text-xs text-neutral-500 space-y-1 list-disc pl-4">
                                {(
                                  (report.review_summary.reddit as { notable_phrases?: { text?: string }[] })
                                    .notable_phrases || []
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
                              <p className="text-xs font-bold uppercase tracking-wide text-neutral-400">
                                X (Twitter) sentiment
                              </p>
                              <p className="text-sm text-neutral-200 capitalize">
                                {String((report.review_summary.x_twitter as { sentiment?: string }).sentiment || 'mixed')}
                              </p>
                              <ul className="text-xs text-neutral-500 space-y-1 list-disc pl-4">
                                {(
                                  (report.review_summary.x_twitter as { notable_phrases?: { text?: string }[] })
                                    .notable_phrases || []
                                )
                                  .slice(0, 2)
                                  .map((ph, j) => (
                                    <li key={j}>{ph.text || ''}</li>
                                  ))}
                              </ul>
                            </div>
                          )}
                      </div>
                    )}

                    {!report.hideSimilarJobs && report.similar_jobs && report.similar_jobs.length === 0 && report.similarJobsEmptyMessage && (
                      <div className="glass rounded-3xl p-5 sm:p-6 md:p-8 border border-border/60">
                        <h3 className="text-lg font-bold mb-2">Similar verified roles</h3>
                        <p className="text-sm text-neutral-400 leading-relaxed">{report.similarJobsEmptyMessage}</p>
                      </div>
                    )}

                    {!report.hideSimilarJobs && report.similar_jobs && report.similar_jobs.length > 0 && (
                      <div className="glass rounded-3xl p-6 md:p-8 space-y-6 border border-border/60">
                        <h3 className="text-lg font-bold">Similar verified roles</h3>
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
                              <div
                                key={i}
                                className="group block p-4 bg-neutral-900/50 border border-border rounded-2xl opacity-80"
                              >
                                {inner}
                                <p className="text-xs text-amber-400 mt-2">Link unavailable</p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    <div className="glass rounded-2xl px-4 py-3 md:px-5 flex flex-wrap items-center justify-between gap-3 border border-border/60">
                      <div className="text-[11px] text-neutral-500 font-mono truncate max-w-[min(100%,14rem)]">
                        ID: {report.request_id}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 shrink-0">
                        {report.cached ? (
                          <button
                            type="button"
                            onClick={() => void reanalyseBypassCache()}
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
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* --- ERROR VIEW --- */}
        <AnimatePresence>
          {phase === 'error' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-8 bg-red-500/10 border border-red-500/20 rounded-2xl sm:rounded-3xl p-6 sm:p-8 text-center space-y-4"
            >
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto">
                <AlertCircle className="w-8 h-8 text-red-500" />
              </div>
              <div className="space-y-2">
                <h3 className="text-xl font-bold text-white">Analysis Interrupted</h3>
                <p className="text-neutral-400">{error}</p>
              </div>
              <button 
                type="button"
                onClick={reset}
                className="bg-neutral-800 hover:bg-neutral-700 text-white font-bold min-h-[48px] px-8 py-3 rounded-xl transition-colors touch-manipulation w-full sm:w-auto max-w-xs mx-auto"
              >
                Try Again
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

        {/* --- HOW IT WORKS --- */}
        <section id="how" className="mt-16 sm:mt-20 space-y-10 sm:space-y-12 px-4 sm:px-6 max-w-6xl mx-auto w-full min-w-0">
          <div className="text-center px-1">
            <h2 className="text-2xl sm:text-3xl font-display font-bold mb-4">How JobSignal Works</h2>
            <p className="text-neutral-400 text-sm sm:text-base">Multi-layered verification for total peace of mind.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
            {[
              { num: '1', title: 'Pattern Analysis', desc: 'We analyze the job URL and description against known trust patterns and scam signatures.' },
              { num: '2', title: 'Cross-Reference', desc: 'We cross-reference the posting with official company domains and public search signals.' },
              { num: '3', title: 'Evidence Verdict', desc: 'You get an evidence-backed verdict: Apply, Verify, or Skip with detailed reasoning.' }
            ].map((step, i) => (
              <div key={i} className="glass p-6 sm:p-8 rounded-2xl sm:rounded-3xl space-y-4 relative overflow-hidden group hover:border-brand/50 transition-colors">
                <div className="text-5xl font-display font-black text-brand/10 absolute -top-2 -right-2 group-hover:text-brand/20 transition-colors">{step.num}</div>
                <h3 className="text-xl font-bold">{step.title}</h3>
                <p className="text-sm text-neutral-400 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <Footer />
    </div>
  );
}
