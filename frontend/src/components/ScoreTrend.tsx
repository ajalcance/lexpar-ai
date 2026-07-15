/**
 * File: src/components/ScoreTrend.tsx
 * Purpose: A tiny inline sparkline of a case's rehearsal scores over time (oldest → newest) so the
 *   attorney sees whether they're improving across sessions. Pure SVG, no dependency; the last
 *   point is emphasized and color-banded (reusing the scorecard's scoreColor) so the current
 *   standing reads at a glance. Renders nothing for fewer than two scored sessions (a line needs
 *   two points).
 * Depends on: react (SVG only), components/ScoreDial (scoreColor)
 * Related: pages/CaseDetail.tsx
 * Security notes: Purely presentational — renders persisted scores only.
 */

import { scoreColor } from '@/components/ScoreDial';

interface Props {
  /** Scores in chronological order (oldest first), 0–100. */
  scores: number[];
}

export function ScoreTrend({ scores }: Props) {
  if (scores.length < 2) return null;

  const width = 120;
  const height = 32;
  const pad = 4;
  const max = 100;
  const min = 0;
  const span = max - min || 1;

  const x = (i: number) => pad + (i * (width - 2 * pad)) / (scores.length - 1);
  const y = (score: number) =>
    height - pad - ((Math.max(min, Math.min(max, score)) - min) / span) * (height - 2 * pad);

  const points = scores.map((s, i) => `${x(i)},${y(s)}`).join(' ');
  const last = scores[scores.length - 1];
  const lastColor = scoreColor(last);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Score trend across ${scores.length} rehearsals, most recent ${Math.round(last)}`}
      className="overflow-visible"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-muted-foreground/50"
      />
      <circle cx={x(scores.length - 1)} cy={y(last)} r={3} fill={lastColor} />
    </svg>
  );
}
