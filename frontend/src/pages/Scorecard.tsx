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
import * as api from '@/lib/api';

export function Scorecard() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id ?? '';
  const { data: scorecard, isLoading, isError } = useQuery({
    queryKey: ['scorecard', sessionId],
    queryFn: () => api.getScorecard(sessionId),
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Scoring your session…</p>;
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
          <CardContent className="text-sm text-muted-foreground">
            {scorecard.strengths}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Weaknesses</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {scorecard.weaknesses}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Judge's ruling</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-relaxed text-muted-foreground">
          {scorecard.judgeRuling}
        </CardContent>
      </Card>
    </div>
  );
}
