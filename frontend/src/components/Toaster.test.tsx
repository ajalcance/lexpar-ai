/**
 * File: src/components/Toaster.test.tsx
 * Purpose: The toast store + Toaster render pushed messages and let them be dismissed — the
 *   app-wide feedback path mutations rely on.
 * Depends on: vitest, @testing-library/*, components/Toaster, lib/toast
 */

import { afterEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Toaster } from '@/components/Toaster';
import { toast, useToastStore } from '@/lib/toast';

describe('Toaster', () => {
  afterEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  it('renders a pushed toast and dismisses it on click', async () => {
    render(<Toaster />);
    expect(screen.queryByText('Case created')).not.toBeInTheDocument();

    toast.success('Case created');
    expect(await screen.findByText('Case created')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByText('Case created')).not.toBeInTheDocument();
  });

  it('renders nothing when there are no toasts', () => {
    const { container } = render(<Toaster />);
    expect(container).toBeEmptyDOMElement();
  });
});
