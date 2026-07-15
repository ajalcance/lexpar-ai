/**
 * File: src/components/ScoreTrend.test.tsx
 * Purpose: The score-trend sparkline renders a line for 2+ scored rehearsals and renders nothing
 *   for fewer (a line needs two points) — the guard CaseDetail relies on.
 * Depends on: vitest, @testing-library/react, components/ScoreTrend
 */

import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { ScoreTrend } from '@/components/ScoreTrend';

describe('ScoreTrend', () => {
  it('renders a sparkline for two or more scores', () => {
    const { container, getByRole } = render(<ScoreTrend scores={[40, 62, 85]} />);
    expect(container.querySelector('polyline')).toBeInTheDocument();
    // The aria-label names the count and the most recent score.
    expect(getByRole('img').getAttribute('aria-label')).toMatch(/3 rehearsals.*85/);
  });

  it('renders nothing for fewer than two scores', () => {
    const { container } = render(<ScoreTrend scores={[71]} />);
    expect(container.querySelector('svg')).not.toBeInTheDocument();
  });
});
