/**
 * File: src/pages/Dashboard.tsx
 * Purpose: Lists the attorney's cases and lets them start a new sparring session (choosing the
 *   proceeding type being rehearsed, §13) or create a new case. All data flows through lib/api.ts
 *   via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, lib/types.ts, components/ui/*
 * Related: backend/app/api/cases.py, pages/CaseUpload.tsx, pages/SparringRoom.tsx
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import * as api from '@/lib/api';
import { PROCEEDING_TYPE_LABELS, type ProceedingType } from '@/lib/types';

const DEFAULT_PROCEEDING: ProceedingType = 'oral_argument';

export function Dashboard() {
  const navigate = useNavigate();
  const { data: cases, isLoading, isError } = useQuery({
    queryKey: ['cases'],
    queryFn: api.getCases,
  });

  // Per-case proceeding-type choice (§13, required at session creation). Cases without an
  // explicit choice start as oral argument.
  const [proceedingByCase, setProceedingByCase] = useState<Record<string, ProceedingType>>({});
  const proceedingFor = (caseId: string) => proceedingByCase[caseId] ?? DEFAULT_PROCEEDING;

  const startSession = useMutation({
    mutationFn: ({ caseId, proceedingType }: { caseId: string; proceedingType: ProceedingType }) =>
      api.createSession(caseId, proceedingType),
    onSuccess: (session) => navigate(`/session/${session.id}`),
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

      <div className="grid gap-4 sm:grid-cols-2">
        {cases?.map((legalCase) => (
          <Card key={legalCase.id} className="flex flex-col">
            <CardHeader>
              <CardTitle>{legalCase.title}</CardTitle>
              <CardDescription>
                Added {new Date(legalCase.createdAt).toLocaleDateString()}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1">
              <p className="line-clamp-3 text-sm text-muted-foreground">
                {legalCase.caseFacts}
              </p>
            </CardContent>
            <CardFooter className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`proceeding-${legalCase.id}`}>Proceeding</Label>
                <select
                  id={`proceeding-${legalCase.id}`}
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  value={proceedingFor(legalCase.id)}
                  onChange={(event) =>
                    setProceedingByCase((prev) => ({
                      ...prev,
                      [legalCase.id]: event.target.value as ProceedingType,
                    }))
                  }
                >
                  {Object.entries(PROCEEDING_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                onClick={() =>
                  startSession.mutate({
                    caseId: legalCase.id,
                    proceedingType: proceedingFor(legalCase.id),
                  })
                }
                disabled={startSession.isPending}
              >
                Start sparring
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  );
}
