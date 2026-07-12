/**
 * File: src/components/ScoreDial.tsx
 * Purpose: The scorecard's headline number, rendered as a radial gauge instead of a bare digit —
 *   a ring fills to the score and is color-banded (red = needs work, amber = solid, green = strong)
 *   so a 42 and a 91 no longer look identical. Same color family as the role/status system.
 * Depends on: react (SVG only, no deps)
 * Related: pages/Scorecard.tsx
 * Security notes: Purely presentational; renders a persisted score only.
 */

/** Performance bands (0–100). Colors match the app's role/status palette (red/amber/green-500). */
function band(score: number): { color: string; label: string } {
  if (score >= 75) return { color: '#22c55e', label: 'Strong' };
  if (score >= 50) return { color: '#f59e0b', label: 'Solid, room to sharpen' };
  return { color: '#ef4444', label: 'Needs work' };
}

/** The band color for a score — shared with the scorecard's per-criterion bars so they read as
 *  the same system as the overall dial. */
export function scoreColor(score: number): string {
  return band(Math.max(0, Math.min(100, Math.round(score)))).color;
}

interface Props {
  /** 0–100. Clamped + rounded before display. */
  score: number;
}

export function ScoreDial({ score }: Props) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const { color, label } = band(value);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const filled = (circumference * value) / 100;

  return (
    <div
      role="img"
      aria-label={`Overall score ${value} out of 100 — ${label}`}
      className="relative flex size-40 items-center justify-center"
    >
      <svg viewBox="0 0 120 120" className="size-40 -rotate-90" aria-hidden>
        <circle cx="60" cy="60" r={radius} fill="none" strokeWidth="10" className="stroke-muted" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          stroke={color}
          strokeDasharray={`${filled} ${circumference}`}
          className="motion-safe:transition-[stroke-dasharray] motion-safe:duration-700"
        />
      </svg>
      <div className="absolute flex flex-col items-center gap-0.5">
        <div className="flex items-baseline gap-0.5">
          <span className="text-4xl font-semibold" style={{ color }}>
            {value}
          </span>
          <span className="text-sm text-muted-foreground">/100</span>
        </div>
        <span className="text-xs font-medium" style={{ color }}>
          {label}
        </span>
      </div>
    </div>
  );
}
