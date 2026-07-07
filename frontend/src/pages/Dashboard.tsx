/**
 * File: src/pages/Dashboard.tsx
 * Purpose: Lists the attorney's cases and lets them start a new sparring session or create a
 *   new case. All data flows through lib/api.ts via TanStack Query.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/cases.py, pages/CaseUpload.tsx, pages/SparringRoom.tsx
 */

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
import * as api from '@/lib/api';

export function Dashboard() {
  const navigate = useNavigate();
  const { data: cases, isLoading, isError } = useQuery({
    queryKey: ['cases'],
    queryFn: api.getCases,
  });

  const startSession = useMutation({
    mutationFn: (caseId: string) => api.createSession(caseId),
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
            <CardFooter>
              <Button
                onClick={() => startSession.mutate(legalCase.id)}
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
