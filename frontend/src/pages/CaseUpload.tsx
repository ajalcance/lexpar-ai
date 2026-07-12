/**
 * File: src/pages/CaseUpload.tsx
 * Purpose: Form for an attorney to create a new case as a structured CASE PROFILE — caption,
 *   docket number, the parties, WHICH SIDE the attorney represents (Opposing Counsel takes the
 *   other by declaration, never inference), and the relief sought. The pleading attached next
 *   (§12) carries the substance; the old free-text "case facts" is now optional context. The
 *   profile is what grounds STT keyterms, the matter framing, and OC's stance (see
 *   ARCHITECTURE §6.5). Submits through lib/api.ts.
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
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { PleadingUpload } from '@/components/PleadingUpload';
import * as api from '@/lib/api';

export function CaseUpload() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState('');
  const [caseNumber, setCaseNumber] = useState('');
  const [petitioner, setPetitioner] = useState('');
  const [respondent, setRespondent] = useState('');
  const [representedParty, setRepresentedParty] = useState<'petitioner' | 'respondent' | ''>('');
  const [reliefSought, setReliefSought] = useState('');
  const [caseFacts, setCaseFacts] = useState('');
  const [courtId, setCourtId] = useState('');
  const [createdCaseId, setCreatedCaseId] = useState<string | null>(null);

  // §13: the forum whose procedural rules ground this case. REQUIRED when the catalog has
  // courts; an unseeded instance (no courts yet) may still create cases, with a visible notice
  // that sessions won't have rules grounding until an admin adds the court.
  const { data: courts } = useQuery({ queryKey: ['courts'], queryFn: api.getCourts });
  const courtsAvailable = (courts?.length ?? 0) > 0;

  const createCase = useMutation({
    mutationFn: () =>
      api.createCase({
        title,
        caseNumber,
        petitioner,
        respondent,
        representedParty,
        reliefSought,
        caseFacts,
        courtId: courtId || null,
      }),
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
      <div className="mx-auto max-w-2xl">
        <Breadcrumbs
          items={[{ label: 'Cases', to: '/dashboard' }, { label: 'New case' }]}
        />
        <Card>
          <CardHeader>
            <CardTitle>Case created — attach the pleading</CardTitle>
            <CardDescription>
              Upload the full complaint/pleading so Opposing Counsel and the Judge reason from the
              real filing. You can also skip and do this later.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <PleadingUpload caseId={createdCaseId} />
            <Button onClick={() => navigate(`/case/${createdCaseId}`)}>Done</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Breadcrumbs items={[{ label: 'Cases', to: '/dashboard' }, { label: 'New case' }]} />
      <Card>
      <CardHeader>
        <CardTitle>New case</CardTitle>
        <CardDescription>
          Identify the case and your side. The pleading you attach next carries the substance —
          opposing counsel and the judge anchor to what you state here.
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
            <Label htmlFor="caseNumber">Case number (optional)</Label>
            <Input
              id="caseNumber"
              value={caseNumber}
              onChange={(event) => setCaseNumber(event.target.value)}
              placeholder="G.R. No. 218738 / Civil Case No. 2001-11-164"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="petitioner">Petitioner / plaintiff</Label>
              <Input
                id="petitioner"
                value={petitioner}
                onChange={(event) => setPetitioner(event.target.value)}
                placeholder="Metropolitan Bank & Trust Company"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="respondent">Respondent / defendant</Label>
              <Input
                id="respondent"
                value={respondent}
                onChange={(event) => setRespondent(event.target.value)}
                placeholder="Salazar Realty Corporation"
                required
              />
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="representedParty">You represent</Label>
            <select
              id="representedParty"
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={representedParty}
              onChange={(event) =>
                setRepresentedParty(event.target.value as 'petitioner' | 'respondent' | '')
              }
              required
            >
              <option value="" disabled>
                Select your side…
              </option>
              <option value="petitioner">Petitioner / plaintiff</option>
              <option value="respondent">Respondent / defendant</option>
            </select>
            <p className="text-xs text-muted-foreground">
              Opposing counsel will argue for the other side.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="reliefSought">Relief sought</Label>
            <Textarea
              id="reliefSought"
              value={reliefSought}
              onChange={(event) => setReliefSought(event.target.value)}
              placeholder="Nullification of the mortgage and foreclosure; quieting of title."
              rows={2}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="caseFacts">Additional context (optional)</Label>
            <Textarea
              id="caseFacts"
              value={caseFacts}
              onChange={(event) => setCaseFacts(event.target.value)}
              placeholder="Anything not in the pleading — posture, stipulations, points of emphasis…"
              rows={4}
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
    </div>
  );
}
