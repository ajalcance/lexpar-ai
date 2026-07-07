/**
 * File: src/test/utils.tsx
 * Purpose: Test helper that renders a component inside the providers pages depend on — a
 *   fresh TanStack Query client and a MemoryRouter — so tests exercise real routing/query
 *   behavior without the full app shell.
 * Depends on: @testing-library/react, @tanstack/react-query, react-router-dom
 * Related: src/**\/*.test.tsx
 */

import type { ReactElement, ReactNode } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/** Render `ui` wrapped in a query client + router, starting at `initialPath`. */
export function renderWithProviders(ui: ReactElement, initialPath = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper });
}
