/**
 * File: src/pages/Dashboard.tsx
 * Purpose: Lists the attorney's cases. Each case links to its detail page (where a session is
 *   started and past rehearsals live); this page is the "Cases" home. Each card also shows a
 *   rehearsal summary (how many sessions, when last rehearsed) so the list is a progress view, not
 *   just a directory. All data flows through lib/api.ts via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, lib/types.ts, components/ui/*
 * Related: backend/app/api/cases.py, pages/CaseDetail.tsx, pages/CaseUpload.tsx
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import * as api from '@/lib/api';
import type { Case } from '@/lib/types';

export function Dashboard() {
  const { data: cases, isLoading, isError } = useQuery({
    queryKey: ['cases'],
    queryFn: api.getCases,
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Your cases</h1>
          <p className="text-sm text-muted-foreground">
            Pick a case to rehearse, or add a new one.
          </p>
        </div>
        <Button nativeButton={false} render={<Link to="/case/new" />}>
          <Plus className="size-4" />
          New case
        </Button>
      </div>

      {isError && (
        <p className="text-sm text-destructive">Could not load cases. Try again.</p>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      )}

      {cases?.length === 0 && !isLoading && (
        <Card className="items-center gap-4 py-10 text-center">
          <Scale className="size-8 text-muted-foreground" aria-hidden />
          <div className="flex flex-col gap-1">
            <CardTitle className="text-lg">Start your first case</CardTitle>
            <CardDescription>
              Add a case, then rehearse it aloud against opposing counsel and the judge.
            </CardDescription>
          </div>
          <Button nativeButton={false} render={<Link to="/case/new" />}>
            <Plus className="size-4" />
            New case
          </Button>
        </Card>
      )}

      {cases && cases.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {cases.map((legalCase) => (
            <CaseCard key={legalCase.id} legalCase={legalCase} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * One case tile. Fetches the case's sessions to show a rehearsal summary. This is one query per
 * card (an N+1 over the list) — fine at the app's current scale and cached by TanStack; the clean
 * long-term fix is a session-count field on the Case payload from the backend.
 */
function CaseCard({ legalCase }: { legalCase: Case }) {
  const { data: sessions } = useQuery({
    queryKey: ['case-sessions', legalCase.id],
    queryFn: () => api.getCaseSessions(legalCase.id),
    retry: false,
  });

  const count = sessions?.length ?? 0;
  const lastRehearsed =
    sessions && sessions.length > 0
      ? sessions
          .map((session) => session.startedAt)
          .sort()
          .at(-1)
      : null;

  return (
    <Link
      to={`/case/${legalCase.id}`}
      className="rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <Card className="h-full transition-colors hover:border-primary/40">
        <CardHeader>
          <CardTitle>{legalCase.title}</CardTitle>
          <CardDescription>
            Added {new Date(legalCase.createdAt).toLocaleDateString()}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="line-clamp-3 text-sm text-muted-foreground">{legalCase.caseFacts}</p>
          <div className="text-xs text-muted-foreground">
            {sessions === undefined ? (
              <Skeleton className="h-3 w-32" />
            ) : count === 0 ? (
              'No rehearsals yet'
            ) : (
              `${count} rehearsal${count === 1 ? '' : 's'} · last ${new Date(
                lastRehearsed!,
              ).toLocaleDateString()}`
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
