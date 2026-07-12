/**
 * File: src/components/DemoScript.test.tsx
 * Purpose: The reviewer script panel renders the six read-aloud segments and the jurisprudence
 *   disclaimer — a hackathon judging aid, so its content is worth guarding.
 * Depends on: vitest, @testing-library/react, components/DemoScript
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DemoScript } from '@/components/DemoScript';

describe('DemoScript', () => {
  it('renders the read-aloud script and the outcome cues', () => {
    render(<DemoScript />);
    expect(screen.getByText('Live test script')).toBeInTheDocument();
    // The opening line and a bait line are present verbatim.
    expect(screen.getByText(/Civil Case No\. 2001-11-164/)).toBeInTheDocument();
    expect(screen.getByText(/ultra vires act as a matter of law/)).toBeInTheDocument();
    // Both rulings are demonstrated (overrule + sustain baits).
    expect(screen.getAllByText('Should be overruled').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Should be sustained').length).toBeGreaterThan(0);
  });

  it('makes clear the agents run their own LLM, not a hard-coded script', () => {
    render(<DemoScript />);
    expect(screen.getByText(/not a hard-coded script/)).toBeInTheDocument();
    expect(screen.getByText(/driven by their own live LLM/)).toBeInTheDocument();
  });

  it('shows the real-jurisprudence disclaimer', () => {
    render(<DemoScript />);
    expect(screen.getByText(/G\.R\. No\. 218738/)).toBeInTheDocument();
    expect(screen.getByText(/Supreme Court of the Philippines/)).toBeInTheDocument();
  });
});
