/**
 * File: src/pages/Scorecard.tsx
 * Purpose: Post-session results — the overall score, strengths, weaknesses, and the judge's
 *   written ruling. Data comes through lib/api.ts via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/scorecards.py (GET /api/sessions/{id}/scorecard)
 * Security notes: Scorecard content derives from the session transcript (work product);
 *   render only, never log.
 */

import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
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

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground">
        Scoring your session… the judge is finalizing your scorecard.
      </p>
    );
  }

  // Still not written after the polling window: an incomplete session returns 409, a
  // completed-but-unscored one 404. Show an honest placeholder rather than a fabricated score.
  const notYetAvailable = error instanceof ApiError && (error.status === 404 || error.status === 409);
  if (isError && notYetAvailable) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Scorecard</h1>
          <Button variant="outline" nativeButton={false} render={<Link to="/dashboard" />}>
            Back to cases
          </Button>
        </div>
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Scorecard</h1>
        <Button variant="outline" nativeButton={false} render={<Link to="/dashboard" />}>
          Back to cases
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardDescription>Overall score</CardDescription>
          <CardTitle className="text-5xl">{scorecard.overallScore}</CardTitle>
        </CardHeader>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Strengths</CardTitle>
          </CardHeader>
          <CardContent className="text-sm whitespace-pre-line text-muted-foreground">
            {scorecard.strengths}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Weaknesses</CardTitle>
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

      {transcript && transcript.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Transcript</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {transcript.map((line) => (
              <TranscriptLine key={line.id} line={line} />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
