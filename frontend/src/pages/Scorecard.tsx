/**
 * File: src/pages/Scorecard.tsx
 * Purpose: Post-session results — the overall score, strengths, weaknesses, and the judge's
 *   written ruling. Data comes through lib/api.ts via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/scorecards.py (GET /api/sessions/{id}/scorecard)
 * Security notes: Scorecard content derives from the session transcript (work product);
 *   render only, never log.
 */

import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Download, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Breadcrumbs, type Crumb } from '@/components/Breadcrumbs';
import { ScoreDial, scoreColor } from '@/components/ScoreDial';
import { TranscriptLine } from '@/components/TranscriptLine';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';

// The scorecard is written by the Judge agent at session end (assess → persist), which takes a few
// seconds after "End session". Poll on 409 (session not yet completed) / 404 (completed but unscored)
// for a while before giving up, so a freshly ended session resolves instead of showing a fallback.
const MAX_SCORECARD_RETRIES = 15; // × 2s ≈ 30s

export function Scorecard() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id ?? '';
  const { data: scorecard, isLoading, isError, error } = useQuery({
    queryKey: ['scorecard', sessionId],
    queryFn: () => api.getScorecard(sessionId),
    retry: (failureCount, err) => {
      const status = err instanceof ApiError ? err.status : 0;
      return (status === 404 || status === 409) && failureCount < MAX_SCORECARD_RETRIES;
    },
    retryDelay: 2000,
  });
  // Only fetch the transcript once the scorecard exists — it's written in the same batch, so before
  // then GET session returns an (unhelpful) empty transcript rather than an error we could retry on.
  const { data: transcript } = useQuery({
    queryKey: ['session-transcript', sessionId],
    queryFn: () => api.getSessionTranscript(sessionId),
    enabled: !!scorecard,
    retry: false,
  });
  // §13: the ruling-provenance audit trail — which sources each AI ruling was grounded in and
  // which citations were flagged as ungrounded. Non-blocking: no rows → no grounding section.
  const { data: provenance } = useQuery({
    queryKey: ['session-provenance', sessionId],
    queryFn: () => api.getSessionProvenance(sessionId),
    enabled: !!scorecard,
    retry: false,
  });
  const allFlaggedCitations = (provenance ?? []).flatMap((record) => record.citationFlags);

  // Breadcrumb chain back to this session's case (Cases › {Case} › Scorecard), so a completed
  // rehearsal is reachable through the case detail — not just via a flat "back to cases". The
  // session→case lookups are plain GETs (no live-room connect); they degrade to Cases › Scorecard.
  const { data: session } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.getSession(sessionId),
    enabled: !!sessionId,
    retry: false,
  });
  const { data: legalCase } = useQuery({
    queryKey: ['case', session?.caseId],
    queryFn: () => api.getCase(session!.caseId),
    enabled: !!session?.caseId,
    retry: false,
  });
  const crumbs: Crumb[] = [
    { label: 'Cases', to: '/dashboard' },
    ...(session?.caseId
      ? [{ label: legalCase?.title ?? 'Case', to: `/case/${session.caseId}` }]
      : []),
    { label: 'Scorecard' },
  ];

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 motion-safe:animate-spin" />
          Scoring your session… the judge is finalizing your scorecard.
        </div>
        <Skeleton className="size-40 self-center rounded-full" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
        <Skeleton className="h-40" />
      </div>
    );
  }

  // Still not written after the polling window: an incomplete session returns 409, a
  // completed-but-unscored one 404. Show an honest placeholder rather than a fabricated score.
  const notYetAvailable = error instanceof ApiError && (error.status === 404 || error.status === 409);
  if (isError && notYetAvailable) {
    return (
      <div className="flex flex-col gap-6">
        <Breadcrumbs items={crumbs} />
        <h1 className="text-2xl font-semibold">Scorecard</h1>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Scorecard not ready</CardTitle>
            <CardDescription>
              We couldn't load a scorecard for this session yet. If you just finished, give it a
              moment and refresh — the judge writes it at the end of the session. If the session
              ended early or the agent wasn't running, there may be nothing to score.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (isError || !scorecard) {
    return <p className="text-sm text-destructive">Could not load the scorecard.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="print:hidden">
        <Breadcrumbs items={crumbs} />
      </div>
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Scorecard</h1>
        {/* Save as PDF via the browser's print dialog (Save as PDF) — no PDF dependency; a print
            stylesheet (index.css) hides the app chrome so the printed page is just the scorecard. */}
        <Button variant="outline" size="sm" onClick={() => window.print()} className="print:hidden">
          <Download className="size-4" />
          Save as PDF
        </Button>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center gap-2 pt-6">
          <CardDescription>Overall score</CardDescription>
          <ScoreDial score={scorecard.overallScore} />
        </CardContent>
      </Card>

      {scorecard.criteria.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Performance breakdown</CardTitle>
            <CardDescription>
              The judge's grade across the four dimensions it weighs.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {scorecard.criteria.map((criterion) => {
              const value = Math.max(0, Math.min(100, Math.round(criterion.score)));
              const color = scoreColor(value);
              return (
                <div key={criterion.name} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-sm">
                    <span>{criterion.name}</span>
                    <span className="font-medium tabular-nums" style={{ color }}>
                      {value}
                    </span>
                  </div>
                  <div
                    className="h-2 overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuenow={value}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={criterion.name}
                  >
                    <div
                      className="h-full rounded-full motion-safe:transition-[width] motion-safe:duration-700"
                      style={{ width: `${value}%`, backgroundColor: color }}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="border-green-500/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <CheckCircle2 className="size-4 text-green-500" aria-hidden />
              Strengths
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm whitespace-pre-line text-muted-foreground">
            {scorecard.strengths}
          </CardContent>
        </Card>
        <Card className="border-amber-500/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AlertTriangle className="size-4 text-amber-500" aria-hidden />
              Weaknesses
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm whitespace-pre-line text-muted-foreground">
            {scorecard.weaknesses}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Judge's ruling</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
          {scorecard.judgeRuling}
        </CardContent>
      </Card>

      {provenance && provenance.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Citation grounding</CardTitle>
            <CardDescription>
              What each AI ruling was grounded in — citations not found in the sources the AI was
              actually shown are flagged, never silently corrected.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {provenance.map((record) => (
              <div key={record.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">
                  {record.rulingType === 'final_ruling' ? 'Final ruling' : 'Objection ruling'}
                </span>
                <span className="text-muted-foreground">
                  {record.chunkIdsUsed.length} source
                  {record.chunkIdsUsed.length === 1 ? '' : 's'} shown
                </span>
                {record.citationFlags.length === 0 ? (
                  <Badge variant="outline">Citations grounded</Badge>
                ) : (
                  <Badge variant="destructive">
                    Unverified: {record.citationFlags.join(', ')}
                  </Badge>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {transcript && transcript.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Transcript</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {transcript.map((line) => (
              <TranscriptLine
                key={line.id}
                line={line}
                flaggedCitations={allFlaggedCitations}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
