/**
 * File: src/App.tsx
 * Purpose: Application routes and the auth guard (ARCHITECTURE §4). Authed routes sit behind
 *   ProtectedRoute and share the AppLayout chrome: Cases (dashboard), case detail, new case,
 *   profile, admin, and the session room + scorecard.
 * Depends on: react-router-dom, components/ProtectedRoute, components/AppLayout, pages/*
 * Related: main.tsx (wraps this in the router + query providers), docs/ARCHITECTURE.md §4
 */

import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/AppLayout';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Admin } from '@/pages/Admin';
import { CaseDetail } from '@/pages/CaseDetail';
import { CaseUpload } from '@/pages/CaseUpload';
import { Dashboard } from '@/pages/Dashboard';
import { Login } from '@/pages/Login';
import { Profile } from '@/pages/Profile';
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
          <Route path="/case/:id" element={<CaseDetail />} />
          <Route path="/profile" element={<Profile />} />
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
