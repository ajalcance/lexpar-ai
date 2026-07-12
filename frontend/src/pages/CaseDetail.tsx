/**
 * File: src/pages/CaseDetail.tsx
 * Purpose: A single case's hub — its facts, the control to start a new sparring session (choosing
 *   the proceeding type, §13), and its rehearsal history (past sessions, each linking to its
 *   scorecard) so completed sessions are reachable again. Data flows through lib/api.ts.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, lib/types.ts,
 *   components/Breadcrumbs, components/ui/*
 * Related: backend/app/api/cases.py (GET /api/cases/{id}, GET /api/cases/{id}/sessions),
 *   pages/Dashboard.tsx (links here), pages/SparringRoom.tsx, pages/Scorecard.tsx
 * Security notes: case_facts and session history are attorney work product — render only, never log.
 */

import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { useAuthStore } from '@/store/auth';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import * as api from '@/lib/api';
import { DESTRUCTIVE_ACTIONS_ENABLED } from '@/lib/flags';
import {
  PROCEEDING_TYPE_LABELS,
  type ProceedingType,
  type Session,
} from '@/lib/types';

const DEFAULT_PROCEEDING: ProceedingType = 'oral_argument';

const STATUS_LABEL: Record<Session['status'], string> = {
  in_progress: 'In progress',
  completed: 'Completed',
  abandoned: 'Ended early',
};

export function CaseDetail() {
  const { id } = useParams<{ id: string }>();
  const caseId = id ?? '';
  const navigate = useNavigate();

  const { data: legalCase, isLoading, isError } = useQuery({
    queryKey: ['case', caseId],
    queryFn: () => api.getCase(caseId),
  });
  const { data: sessions } = useQuery({
    queryKey: ['case-sessions', caseId],
    queryFn: () => api.getCaseSessions(caseId),
  });

  const [proceeding, setProceeding] = useState<ProceedingType>(DEFAULT_PROCEEDING);

  const startSession = useMutation({
    mutationFn: () => api.createSession(caseId, proceeding),
    onSuccess: (session) => navigate(`/session/${session.id}`),
  });

  // Two-tier deletion: Archive (soft, owner) is the default; Purge (hard) is admin-only and
  // requires the case title typed back — never one accidental click away from Archive.
  const user = useAuthStore((state) => state.user);
  const [confirming, setConfirming] = useState<'archive' | 'purge' | null>(null);
  const [typedTitle, setTypedTitle] = useState('');
  const [dangerError, setDangerError] = useState<string | null>(null);
  const onDangerError = (err: unknown) =>
    setDangerError(err instanceof Error ? err.message : 'Action failed.');
  const archiveCase = useMutation({
    mutationFn: () => api.archiveCase(caseId),
    onSuccess: () => navigate('/dashboard'),
    onError: onDangerError,
  });
  const purgeCase = useMutation({
    mutationFn: () => api.purgeCase(caseId),
    onSuccess: () => navigate('/dashboard'),
    onError: onDangerError,
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading case…</p>;
  }
  if (isError || !legalCase) {
    return <p className="text-sm text-destructive">Could not load this case.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs
        items={[{ label: 'Cases', to: '/dashboard' }, { label: legalCase.title }]}
      />

      <div>
        <h1 className="text-2xl font-semibold">{legalCase.title}</h1>
        <p className="text-sm text-muted-foreground">
          Added {new Date(legalCase.createdAt).toLocaleDateString()}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Case facts</CardTitle>
        </CardHeader>
        <CardContent className="text-sm whitespace-pre-line text-muted-foreground">
          {legalCase.caseFacts || 'No case facts recorded.'}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Start a sparring session</CardTitle>
          <CardDescription>
            Choose the proceeding you're rehearsing — it sets which objections opposing counsel
            may raise.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="proceeding">Proceeding</Label>
            <select
              id="proceeding"
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={proceeding}
              onChange={(event) => setProceeding(event.target.value as ProceedingType)}
            >
              {Object.entries(PROCEEDING_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
            Start sparring
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rehearsal history</CardTitle>
          <CardDescription>Past sessions for this case and their scorecards.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!sessions || sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No sessions yet — start one above to build a record.
            </p>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {PROCEEDING_TYPE_LABELS[session.proceedingType]}
                  </span>
                  <Badge variant={session.status === 'completed' ? 'outline' : 'secondary'}>
                    {STATUS_LABEL[session.status]}
                  </Badge>
                  <span className="text-muted-foreground">
                    {new Date(session.startedAt).toLocaleString()}
                  </span>
                </div>
                {session.status === 'in_progress' ? (
                  <Button
                    variant="outline"
                    size="sm"
                    nativeButton={false}
                    render={<Link to={`/session/${session.id}`} />}
                  >
                    Resume session
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    nativeButton={false}
                    render={<Link to={`/session/${session.id}/scorecard`} />}
                  >
                    View scorecard
                  </Button>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {DESTRUCTIVE_ACTIONS_ENABLED && (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-lg text-destructive">Danger zone</CardTitle>
          <CardDescription>
            Archive hides this case (sessions and scorecards are kept).
            {user?.role === 'admin' &&
              ' Purge permanently deletes the case and everything under it.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={archiveCase.isPending}
              onClick={() => setConfirming('archive')}
            >
              Archive case
            </Button>
            {user?.role === 'admin' && (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setConfirming('purge')}
              >
                Purge case…
              </Button>
            )}
          </div>
          {confirming && (
            <div className="flex flex-col gap-2 rounded-md border border-destructive/40 p-3">
              <p className="text-sm text-destructive">
                {confirming === 'archive'
                  ? `Archive "${legalCase.title}"? It disappears from your cases; nothing is deleted.`
                  : `Permanently purge "${legalCase.title}" — sessions, transcripts, scorecards, and documents included? This cannot be undone.`}
              </p>
              {confirming === 'purge' && (
                <input
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  value={typedTitle}
                  onChange={(event) => setTypedTitle(event.target.value)}
                  placeholder={`Type "${legalCase.title}" to confirm`}
                  aria-label="Type the case title to confirm"
                />
              )}
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={
                    (confirming === 'purge' && typedTitle !== legalCase.title) ||
                    archiveCase.isPending ||
                    purgeCase.isPending
                  }
                  onClick={() =>
                    confirming === 'archive' ? archiveCase.mutate() : purgeCase.mutate()
                  }
                >
                  {confirming === 'archive' ? 'Archive' : 'Purge permanently'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setConfirming(null);
                    setTypedTitle('');
                    setDangerError(null);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {dangerError && <p className="text-sm text-destructive">{dangerError}</p>}
        </CardContent>
      </Card>
      )}
    </div>
  );
}
