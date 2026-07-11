/**
 * File: src/pages/Admin.tsx
 * Purpose: Minimal admin surface (§13) — create a Court and upload its OFFICIAL rule documents
 *   (with source provenance), showing each document's ingestion status. Functional, not polished.
 *   Role-gated here (defense in depth) AND on every backend route (the real control).
 * Depends on: @tanstack/react-query, lib/api.ts, store/auth.ts, components/ui/*
 * Related: backend/app/api/courts.py, scripts/seed_court.py, docs/ARCHITECTURE.md §13
 * Security notes: Only official, operator-sourced documents belong here — the upload form carries
 *   provenance fields (citation + source) for the §13 audit trail. Never AI-generated text.
 */

import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Shield } from 'lucide-react';
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
import { RuleDocumentRow } from '@/components/RuleDocumentRow';
import * as api from '@/lib/api';
import { useAuthStore } from '@/store/auth';

export function Admin() {
  const user = useAuthStore((state) => state.user);
  const queryClient = useQueryClient();

  const [courtName, setCourtName] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [selectedCourtId, setSelectedCourtId] = useState('');
  const [ruleFile, setRuleFile] = useState<File | null>(null);
  const [ruleTitle, setRuleTitle] = useState('');
  const [sourceCitation, setSourceCitation] = useState('');
  const [sourceReference, setSourceReference] = useState('');

  const isAdmin = user?.role === 'admin';

  const { data: courts } = useQuery({
    queryKey: ['courts'],
    queryFn: api.getCourts,
    enabled: isAdmin,
  });
  const { data: ruleDocs } = useQuery({
    queryKey: ['court-rules', selectedCourtId],
    queryFn: () => api.getCourtRules(selectedCourtId),
    enabled: isAdmin && !!selectedCourtId,
    // poll while any document is still ingesting so statuses resolve without a manual refresh
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.ingestionStatus === 'pending') ? 2000 : false,
  });

  const createCourt = useMutation({
    mutationFn: () =>
      api.createCourt({
        name: courtName,
        jurisdictionDescription: jurisdiction || undefined,
      }),
    onSuccess: async (court) => {
      setCourtName('');
      setJurisdiction('');
      setSelectedCourtId(court.id);
      await queryClient.invalidateQueries({ queryKey: ['courts'] });
    },
  });

  const uploadRule = useMutation({
    mutationFn: () => {
      if (!ruleFile) throw new Error('Choose a PDF first.');
      return api.uploadCourtRule(selectedCourtId, ruleFile, {
        title: ruleTitle || undefined,
        sourceCitation: sourceCitation || undefined,
        sourceReference: sourceReference || undefined,
      });
    },
    onSuccess: async () => {
      setRuleFile(null);
      setRuleTitle('');
      setSourceCitation('');
      setSourceReference('');
      await queryClient.invalidateQueries({ queryKey: ['court-rules', selectedCourtId] });
    },
  });

  if (!isAdmin) {
    return (
      <p className="text-sm text-muted-foreground">
        Administrator role required. Court and rule-corpus management is not available on this
        account.
      </p>
    );
  }

  return (
    // Left accent + eyebrow mark this as a distinct administrative section, not the attorney app.
    <div className="flex flex-col gap-6 border-l-2 border-primary/40 pl-5">
      <div>
        <div className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-primary uppercase">
          <Shield className="size-3.5" />
          Administration
        </div>
        <h1 className="mt-1 text-2xl font-semibold">Court administration</h1>
        <p className="text-sm text-muted-foreground">
          Manage the forums and the official procedural rules that ground the AI.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Create a court</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              createCourt.mutate();
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="courtName">Court name</Label>
              <Input
                id="courtName"
                value={courtName}
                onChange={(event) => setCourtName(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="jurisdiction">Jurisdiction description</Label>
              <Input
                id="jurisdiction"
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
              />
            </div>
            {createCourt.isError && (
              <p className="text-sm text-destructive">Could not create the court.</p>
            )}
            <Button type="submit" disabled={createCourt.isPending}>
              Create court
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rule documents</CardTitle>
          <CardDescription>
            Upload OFFICIAL rule documents only (court issuances, statutes from government
            sources) — record where each came from. The AI cites only what is ingested here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="adminCourt">Court</Label>
            <select
              id="adminCourt"
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={selectedCourtId}
              onChange={(event) => setSelectedCourtId(event.target.value)}
            >
              <option value="" disabled>
                Select a court…
              </option>
              {courts?.map((court) => (
                <option key={court.id} value={court.id}>
                  {court.name}
                </option>
              ))}
            </select>
          </div>

          {selectedCourtId && (
            <>
              <form
                className="flex flex-col gap-4"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  uploadRule.mutate();
                }}
              >
                <div className="flex flex-col gap-2">
                  <Label htmlFor="ruleFile">Rule document (PDF)</Label>
                  <Input
                    id="ruleFile"
                    type="file"
                    accept="application/pdf"
                    onChange={(event) => setRuleFile(event.target.files?.[0] ?? null)}
                    required
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="ruleTitle">Title</Label>
                  <Input
                    id="ruleTitle"
                    value={ruleTitle}
                    onChange={(event) => setRuleTitle(event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="sourceCitation">Source citation</Label>
                  <Input
                    id="sourceCitation"
                    value={sourceCitation}
                    onChange={(event) => setSourceCitation(event.target.value)}
                    placeholder="Formal citation of the instrument"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="sourceReference">Source URL / reference</Label>
                  <Input
                    id="sourceReference"
                    value={sourceReference}
                    onChange={(event) => setSourceReference(event.target.value)}
                    placeholder="Where this official copy came from"
                  />
                </div>
                {uploadRule.isError && (
                  // Surface the backend's actual detail (e.g. "File exceeds the 50 MB limit") from
                  // the ApiError message, not a generic string — so the admin knows what to fix.
                  <p className="text-sm text-destructive">
                    {uploadRule.error instanceof Error
                      ? uploadRule.error.message
                      : 'Upload failed. Try again.'}
                  </p>
                )}
                <Button type="submit" disabled={uploadRule.isPending || !ruleFile}>
                  {uploadRule.isPending ? 'Uploading…' : 'Upload rules'}
                </Button>
              </form>

              <div className="flex flex-col gap-2">
                {ruleDocs?.length === 0 && (
                  <p className="text-sm text-muted-foreground">No rule documents yet.</p>
                )}
                {ruleDocs?.map((doc) => (
                  <RuleDocumentRow key={doc.id} courtId={selectedCourtId} doc={doc} />
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {selectedCourtId && (
        <CourtDangerZone
          courtId={selectedCourtId}
          courtName={courts?.find((c) => c.id === selectedCourtId)?.name ?? ''}
          onGone={() => {
            setSelectedCourtId('');
            void queryClient.invalidateQueries({ queryKey: ['courts'] });
          }}
        />
      )}
    </div>
  );
}

/** Court-level Archive/Purge — separated "danger zone", never adjacent to the routine actions.
 *  Purge requires the court name typed back and is refused by the backend (409) while any case
 *  still references the forum. */
function CourtDangerZone({
  courtId,
  courtName,
  onGone,
}: {
  courtId: string;
  courtName: string;
  onGone: () => void;
}) {
  const [confirming, setConfirming] = useState<'archive' | 'purge' | null>(null);
  const [typedName, setTypedName] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onError = (err: unknown) =>
    setError(err instanceof Error ? err.message : 'Action failed.');
  const archive = useMutation({
    mutationFn: () => api.archiveCourt(courtId),
    onSuccess: onGone,
    onError,
  });
  const purge = useMutation({
    mutationFn: () => api.purgeCourt(courtId),
    onSuccess: onGone,
    onError,
  });

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-lg text-destructive">Danger zone</CardTitle>
        <CardDescription>
          Archive retires this forum (cases keep running, without rules grounding — reversible at
          the database level). Purge permanently deletes the forum and its corpus; it is refused
          while any case still references it.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={archive.isPending}
            onClick={() => setConfirming('archive')}
          >
            Archive court
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirming('purge')}
          >
            Purge court…
          </Button>
        </div>
        {confirming && (
          <div className="flex flex-col gap-2 rounded-md border border-destructive/40 p-3">
            <p className="text-sm text-destructive">
              {confirming === 'archive'
                ? `Archive "${courtName}"? Its rules leave retrieval; existing cases keep running without grounding.`
                : `Permanently purge "${courtName}" and its entire rules corpus? This cannot be undone.`}
            </p>
            {confirming === 'purge' && (
              <Input
                value={typedName}
                onChange={(event) => setTypedName(event.target.value)}
                placeholder={`Type "${courtName}" to confirm`}
                aria-label="Type the court name to confirm"
              />
            )}
            <div className="flex gap-2">
              <Button
                variant="destructive"
                size="sm"
                disabled={
                  (confirming === 'purge' && typedName !== courtName) ||
                  archive.isPending ||
                  purge.isPending
                }
                onClick={() => (confirming === 'archive' ? archive.mutate() : purge.mutate())}
              >
                {confirming === 'archive' ? 'Archive' : 'Purge permanently'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setConfirming(null);
                  setTypedName('');
                  setError(null);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
