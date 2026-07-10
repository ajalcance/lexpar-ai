/**
 * File: src/pages/CaseUpload.tsx
 * Purpose: Form for an attorney to create a new case from a title and case facts (with an
 *   optional document input, cosmetic until real uploads land). Submits through lib/api.ts
 *   and returns to the dashboard.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/cases.py (POST /api/cases)
 * Security notes: case_facts is attorney work product — never log its contents. Here it only
 *   passes through the API function.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PleadingUpload } from '@/components/PleadingUpload';
import * as api from '@/lib/api';

export function CaseUpload() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [caseFacts, setCaseFacts] = useState('');
  const [courtId, setCourtId] = useState('');
  const [createdCaseId, setCreatedCaseId] = useState<string | null>(null);

  // §13: the forum whose procedural rules ground this case. REQUIRED when the catalog has
  // courts; an unseeded instance (no courts yet) may still create cases, with a visible notice
  // that sessions won't have rules grounding until an admin adds the court.
  const { data: courts } = useQuery({ queryKey: ['courts'], queryFn: api.getCourts });
  const courtsAvailable = (courts?.length ?? 0) > 0;

  const createCase = useMutation({
    mutationFn: () => api.createCase({ title, caseFacts, courtId: courtId || null }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ['cases'] });
      // Reveal the pleading-upload step for the new case instead of leaving immediately, so the
      // attorney can attach the full filing that grounds the AI (§12).
      setCreatedCaseId(created.id);
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    createCase.mutate();
  };

  if (createdCaseId) {
    return (
      <Card className="mx-auto max-w-2xl">
        <CardHeader>
          <CardTitle>Case created — attach the pleading</CardTitle>
          <CardDescription>
            Upload the full complaint/pleading so Opposing Counsel and the Judge reason from the
            real filing. You can also skip and do this later.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <PleadingUpload caseId={createdCaseId} />
          <Button onClick={() => navigate('/dashboard')}>Done — go to dashboard</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <CardTitle>New case</CardTitle>
        <CardDescription>
          Give the case a title and the facts your opponent will argue against.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="title">Case title</Label>
            <Input
              id="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Rivera v. Coastal Logistics"
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="caseFacts">Case facts</Label>
            <Textarea
              id="caseFacts"
              value={caseFacts}
              onChange={(event) => setCaseFacts(event.target.value)}
              placeholder="Summarize the dispute, the parties, and the key facts…"
              rows={6}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="court">Court</Label>
            {courtsAvailable ? (
              <select
                id="court"
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                value={courtId}
                onChange={(event) => setCourtId(event.target.value)}
                required
              >
                <option value="" disabled>
                  Select the forum…
                </option>
                {courts?.map((court) => (
                  <option key={court.id} value={court.id}>
                    {court.name}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-xs text-muted-foreground">
                No courts configured yet — the AI will argue without procedural-rules grounding
                until an administrator adds this case's forum.
              </p>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            After creating the case you'll attach the full pleading (PDF) that the AI argues from.
          </p>
          {createCase.isError && (
            <p className="text-sm text-destructive">
              Could not create the case. Try again.
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={createCase.isPending}>
              {createCase.isPending ? 'Creating…' : 'Create case'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/dashboard')}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
