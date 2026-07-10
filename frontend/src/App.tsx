/**
 * File: src/App.tsx
 * Purpose: Application routes and the auth guard. Maps the five routes from ARCHITECTURE §4;
 *   authed routes sit behind ProtectedRoute and share AppLayout chrome.
 * Depends on: react-router-dom, components/ProtectedRoute, components/AppLayout, pages/*
 * Related: main.tsx (wraps this in the router + query providers), docs/ARCHITECTURE.md §4
 */

import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/AppLayout';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Admin } from '@/pages/Admin';
import { CaseUpload } from '@/pages/CaseUpload';
import { Dashboard } from '@/pages/Dashboard';
import { Login } from '@/pages/Login';
import { Scorecard } from '@/pages/Scorecard';
import { SparringRoom } from '@/pages/SparringRoom';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/case/new" element={<CaseUpload />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/session/:id" element={<SparringRoom />} />
          <Route path="/session/:id/scorecard" element={<Scorecard />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
