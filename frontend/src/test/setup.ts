/**
 * File: src/test/setup.ts
 * Purpose: Global test setup — registers jest-dom matchers for Vitest and clears the DOM
 *   between tests. Referenced by vite.config.ts (test.setupFiles).
 * Depends on: @testing-library/jest-dom, @testing-library/react, vitest
 */

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
