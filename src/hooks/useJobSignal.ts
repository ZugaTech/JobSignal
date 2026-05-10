import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { sanitizeApiResponse } from '../utils/api-helpers';

export type Phase = 'idle' | 'loading' | 'error' | 'success';

export function useJobSignal() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState('Checking the job listing...');
  const [elapsed, setElapsed] = useState(0);

  const apiBase = useCallback(() => {
    if (typeof (window as any).JOBSIGNAL_API_BASE === "string" && (window as any).JOBSIGNAL_API_BASE.trim()) {
      return (window as any).JOBSIGNAL_API_BASE.replace(/\/$/, "");
    }
    const h = window.location.hostname;
    const protocol = window.location.protocol;
    const port = window.location.port;

    if (protocol === "file:" || h === "") {
      return "http://127.0.0.1:8080";
    }
    if ((h === "localhost" || h === "127.0.0.1") && port === "8080") {
      return "";
    }
    if (h === "localhost" || h === "127.0.0.1") {
      return "http://127.0.0.1:8080";
    }
    return "";
  }, []);

  const verify = async (params: { url?: string; text?: string; file?: File | null; includeSimilarJobs?: boolean; forceRefresh?: boolean }) => {
    setPhase('loading');
    setError(null);
    setElapsed(0);
    
    const startTime = performance.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((performance.now() - startTime) / 1000));
    }, 1000);

    const steps = [
      "Checking the job listing...",
      "Verifying company signals...",
      "Scanning public sources...",
      "Comparing cross-platform data...",
      "Reviewing company reputation...",
      "Building your report...",
    ];
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      stepIdx = (stepIdx + 1) % steps.length;
      setLoadingStep(steps[stepIdx]);
    }, 3000);

    try {
      const base = apiBase();
      let response;

      if (params.file) {
        const fd = new FormData();
        if (params.url) fd.append("job_url", params.url);
        if (params.text) fd.append("job_description", params.text);
        fd.append("job_image", params.file);
        fd.append("include_similar_jobs", params.includeSimilarJobs ? "true" : "false");
        if (params.forceRefresh) fd.append("force_refresh", "true");
        
        response = await axios.post(`${base}/v1/verify`, fd);
      } else {
        response = await axios.post(`${base}/v1/verify`, {
          job_url: params.url || null,
          job_description: params.text || null,
          include_similar_jobs: params.includeSimilarJobs,
          force_refresh: params.forceRefresh,
        });
      }

      let data = response.data;

      // Handle partial cache hit
      if (data.cached === true && data.cache_complete === false) {
        setReport(sanitizeApiResponse(data));
        // Continue loading for full report
        const refreshResponse = await axios.post(`${base}/v1/verify`, params.file ? {
          // FormData needs to be recreated if we were to support file refresh here, 
          // but usually URL cache hits don't have files.
        } : {
          job_url: params.url || null,
          job_description: params.text || null,
          include_similar_jobs: params.includeSimilarJobs,
          force_refresh: true,
        });
        data = refreshResponse.data;
      }

      setReport(sanitizeApiResponse(data));
      setPhase('success');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.message || "Something went wrong. Please try again.");
      setPhase('error');
    } finally {
      clearInterval(timer);
      clearInterval(stepTimer);
    }
  };

  return {
    phase,
    report,
    error,
    loadingStep,
    elapsed,
    verify,
    reset: () => {
      setPhase('idle');
      setReport(null);
      setError(null);
    }
  };
}
