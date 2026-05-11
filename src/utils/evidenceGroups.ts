import type { DisplaySignalRow } from '../types/verify';
import { getSignalLabel, signalStrengthDotClass } from './formatters';

/** UX-facing buckets — maps engineering strengths to calm presentation groups. */
export type TrustEvidenceBucket = 'verified' | 'caution' | 'limited';

export function classifySignalBucket(row: DisplaySignalRow): TrustEvidenceBucket {
  const raw = row.kind === 'pipeline' ? row.strength : row.status;
  const dot = signalStrengthDotClass(raw);
  if (dot === 'green') return 'verified';
  if (dot === 'red' || dot === 'amber') return 'caution';
  return 'limited';
}

export type GroupedSignals = Record<TrustEvidenceBucket, DisplaySignalRow[]>;

export function groupDisplaySignals(rows: DisplaySignalRow[]): GroupedSignals {
  const out: GroupedSignals = { verified: [], caution: [], limited: [] };
  for (const row of rows) {
    out[classifySignalBucket(row)].push(row);
  }
  return out;
}

export const GROUP_LABELS: Record<TrustEvidenceBucket, { title: string; subtitle: string }> = {
  verified: {
    title: 'Verified',
    subtitle: 'Checks that aligned with employer-level or posting-level corroboration.',
  },
  caution: {
    title: 'Needs attention',
    subtitle: 'Mixed, weak, or conflicting signals—worth a closer look before you commit time.',
  },
  limited: {
    title: 'Limited evidence',
    subtitle: 'Could not be verified from reliable public sources for this run.',
  },
};

export function rowPrimaryLabel(row: DisplaySignalRow): string {
  return row.kind === 'pipeline' ? getSignalLabel(row.id) : row.name;
}
