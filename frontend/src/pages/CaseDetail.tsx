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
import { scoreColor } from '@/components/ScoreDial';
import { ScoreTrend } from '@/components/ScoreTrend';
import * as api from '@/lib/api';
import { DESTRUCTIVE_ACTIONS_ENABLED } from '@/lib/flags';
import {
  PROCEEDING_TYPE_LABELS,
  type Case,
  type ProceedingType,
  type Session,
} from '@/lib/types';

const DEFAULT_PROCEEDING: ProceedingType = 'oral_argument';

// Only oral argument is validated end-to-end so far; the others are shown for reference but not
// yet selectable. Add a type here as it's tested — the disabled options light up automatically.
const ENABLED_PROCEEDINGS: readonly ProceedingType[] = ['oral_argument'];

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

      <CaseProfile legalCase={legalCase} />

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Case facts</CardTitle>
        </CardHeader>
        <CardContent className="text-sm whitespace-pre-line text-muted-foreground">
          {legalCase.caseFacts || 'No case facts recorded.'}
        </CardContent>
      </Card>

      {/* The primary action — subtly highlighted (blue = the attorney's move) so real users, not
          just judges, land here. A faint tint + a left accent line: punchy, not aggressive. */}
      <Card className="border-blue-500/30 border-l-4 border-l-blue-500 bg-blue-500/5 shadow-sm">
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
              {Object.entries(PROCEEDING_TYPE_LABELS).map(([value, label]) => {
                const enabled = ENABLED_PROCEEDINGS.includes(value as ProceedingType);
                return (
                  <option key={value} value={value} disabled={!enabled}>
                    {enabled ? label : `${label} — coming soon`}
                  </option>
                );
              })}
            </select>
            <p className="text-xs text-muted-foreground">
              Only oral argument is available in this release; the others are coming soon.
            </p>
          </div>
          <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
            Start sparring
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-lg">Rehearsal history</CardTitle>
              <CardDescription>Past sessions for this case and their scorecards.</CardDescription>
            </div>
            {/* Score trend across scored rehearsals (oldest → newest) — a glance at whether the
                attorney is improving. Hidden until there are two scored sessions to connect. */}
            <ScoreTrend
              scores={
                (sessions ?? [])
                  .filter((s) => s.overallScore !== null)
                  .map((s) => s.overallScore as number)
                  .reverse() // sessions are newest-first; the trend runs oldest → newest
              }
            />
          </div>
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
                  {session.overallScore !== null && (
                    <span
                      className="rounded px-1.5 py-0.5 text-xs font-semibold text-white"
                      style={{ backgroundColor: scoreColor(session.overallScore) }}
                    >
                      {Math.round(session.overallScore)}
                    </span>
                  )}
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
            Archive hides this case (sessions and scorecards are kept). Purge permanently deletes
            the case and everything under it.
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
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => setConfirming('purge')}
            >
              Purge case…
            </Button>
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

/**
 * The case's stated identity (profile) — docket number, parties, the side the attorney represents,
 * and the relief sought. Renders only the fields that were actually provided; if none were (a
 * pre-profile case), the whole card is omitted so it never shows an empty shell.
 */
function CaseProfile({ legalCase }: { legalCase: Case }) {
  const { caseNumber, petitioner, respondent, representedParty, reliefSought } = legalCase;
  const rows: { label: string; value: string }[] = [];
  if (caseNumber) rows.push({ label: 'Docket number', value: caseNumber });
  if (petitioner) rows.push({ label: 'Petitioner', value: petitioner });
  if (respondent) rows.push({ label: 'Respondent', value: respondent });
  if (representedParty) {
    const name = representedParty === 'petitioner' ? petitioner : respondent;
    const side = representedParty === 'petitioner' ? 'Petitioner' : 'Respondent';
    rows.push({ label: 'You represent', value: name ? `${side} (${name})` : side });
  }
  if (reliefSought) rows.push({ label: 'Relief sought', value: reliefSought });

  if (rows.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Case profile</CardTitle>
        <CardDescription>What the AI treats as on the record from the start.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {rows.map((row) => (
            <div key={row.label} className="flex flex-col gap-0.5">
              <dt className="text-xs text-muted-foreground">{row.label}</dt>
              <dd className="whitespace-pre-line">{row.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
