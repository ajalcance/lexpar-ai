/**
 * File: src/lib/toast.ts
 * Purpose: A tiny app-wide toast store (no dependency — built on the same Zustand the app already
 *   uses). `toast.error(...)` / `toast.success(...)` push a transient message that auto-dismisses;
 *   the <Toaster /> mounted at the app root renders them. Gives mutations a consistent way to
 *   surface success/failure instead of silent or scattered inline errors.
 * Depends on: zustand
 * Related: components/Toaster.tsx (renders these), App.tsx (mounts the Toaster)
 * Security notes: Messages are UI strings only — never pass raw work product or credentials here.
 */

import { create } from 'zustand';

export type ToastVariant = 'error' | 'success' | 'info';

export interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastState {
  toasts: Toast[];
  push: (message: string, variant: ToastVariant) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;
/** How long a toast stays up before auto-dismissing. */
export const TOAST_TTL_MS = 5000;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (message, variant) => {
    const id = nextId++;
    set((state) => ({ toasts: [...state.toasts, { id, message, variant }] }));
    setTimeout(() => get().dismiss(id), TOAST_TTL_MS);
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/** Fire-and-forget helpers callable from anywhere (mutation onError/onSuccess, etc.). */
export const toast = {
  error: (message: string) => useToastStore.getState().push(message, 'error'),
  success: (message: string) => useToastStore.getState().push(message, 'success'),
  info: (message: string) => useToastStore.getState().push(message, 'info'),
};
