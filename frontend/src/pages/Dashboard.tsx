/**
 * File: src/pages/Dashboard.tsx
 * Purpose: Lists the attorney's cases. Each case links to its detail page (where a session is
 *   started and past rehearsals live); this page is the "Cases" home. All data flows through
 *   lib/api.ts via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, lib/types.ts, components/ui/*
 * Related: backend/app/api/cases.py, pages/CaseDetail.tsx, pages/CaseUpload.tsx
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import * as api from '@/lib/api';

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

      {isLoading && <p className="text-sm text-muted-foreground">Loading cases…</p>}
      {isError && (
        <p className="text-sm text-destructive">Could not load cases. Try again.</p>
      )}

      {cases?.length === 0 && !isLoading && (
        <p className="text-sm text-muted-foreground">
          No cases yet — add your first one to start rehearsing.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {cases?.map((legalCase) => (
          <Link
            key={legalCase.id}
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
              <CardContent>
                <p className="line-clamp-3 text-sm text-muted-foreground">
                  {legalCase.caseFacts}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
