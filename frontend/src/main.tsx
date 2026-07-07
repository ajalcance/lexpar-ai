/**
 * File: src/main.tsx
 * Purpose: App entry point. Mounts <App/> inside the global providers: TanStack Query
 *   (server state) and the browser router.
 * Depends on: react-dom, @tanstack/react-query, react-router-dom, App.tsx
 * Related: App.tsx (route tree), docs/ARCHITECTURE.md §4
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from '@/App';
import './index.css';

const queryClient = new QueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
