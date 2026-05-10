import { useState, useCallback } from 'react';
import axios, { isAxiosError } from 'axios';
import type { SanitizedVerifyReport } from '../types/verify';
import { sanitizeApiResponse } from '../utils/api-helpers';
import { resolveApiBase } from '../utils/apiBase';

export type Phase = 'idle' | 'loading' | 'error' | 'success';

function messageFromVerifyAxiosError(err: unknown): string {
  if (!isAxiosError(err)) {
    return 'Something went wrong. Please try again.';
  }
  const status = err.response?.status;
  const data = err.response?.data as { detail?: unknown; message?: string } | undefined;

  if (status === 422) {
    return 'We could not validate this request. Check the URL or description and try again.';
  }
  if (status === 429) {
    return 'Too many checks in a short time. Please wait a minute and try again.';
  }
  if (status === 400 && typeof data?.detail === 'string') {
    return data.detail;
  }
  if (status != null && status >= 500) {
    return 'Our verification service had a problem. Please try again in a moment.';
  }
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message.trim();
  }
  if (Array.isArray(data?.detail)) {
    const first = data.detail[0] as { msg?: string } | undefined;
    if (first && typeof first.msg === 'string') return first.msg;
  }
  return 'Something went wrong. Please try again.';
}

export function useJobSignal() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [report, setReport] = useState<SanitizedVerifyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState('Checking the job listing...');
  const [elapsed, setElapsed] = useState(0);

  const apiBase = useCallback(() => resolveApiBase(), []);

  const verify = async (params: {
    url?: string;
    text?: string;
    file?: File | null;
    includeSimilarJobs?: boolean;
    forceRefresh?: boolean;
  }) => {
    setPhase('loading');
    setError(null);
    setElapsed(0);

    const startTime = performance.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((performance.now() - startTime) / 1000));
    }, 1000);

    const steps = [
      'Checking the job listing...',
      'Verifying company signals...',
      'Scanning public sources...',
      'Comparing cross-platform data...',
      'Reviewing company reputation...',
      'Building your report...',
    ];
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      stepIdx = (stepIdx + 1) % steps.length;
      setLoadingStep(steps[stepIdx]);
    }, 3000);

    const base = apiBase();

    const buildMultipart = (forceRefresh: boolean) => {
      const fd = new FormData();
      if (params.url) fd.append('job_url', params.url);
      if (params.text) fd.append('job_description', params.text);
      if (params.file) fd.append('job_image', params.file);
      fd.append('include_similar_jobs', params.includeSimilarJobs ? 'true' : 'false');
      if (forceRefresh || params.forceRefresh) fd.append('force_refresh', 'true');
      return fd;
    };

    const postVerify = async (forceRefresh: boolean) => {
      if (params.file) {
        return axios.post(`${base}/v1/verify`, buildMultipart(forceRefresh));
      }
      return axios.post(`${base}/v1/verify`, {
        job_url: params.url || null,
        job_description: params.text || null,
        include_similar_jobs: params.includeSimilarJobs,
        force_refresh: forceRefresh || !!params.forceRefresh,
      });
    };

    try {
      let response = await postVerify(false);
      let data = response.data;

      if (data.cached === true && data.cache_complete === false) {
        setReport(sanitizeApiResponse(data));
        const refreshResponse = await postVerify(true);
        data = refreshResponse.data;
      }

      setReport(sanitizeApiResponse(data));
      setPhase('success');
    } catch (err: unknown) {
      console.error('verify request failed', err);
      setError(messageFromVerifyAxiosError(err));
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
    hydrateReport: (raw: unknown) => {
      setReport(sanitizeApiResponse(raw));
      setError(null);
      setElapsed(0);
      setPhase('success');
    },
    reset: () => {
      setPhase('idle');
      setReport(null);
      setError(null);
    },
  };
}
