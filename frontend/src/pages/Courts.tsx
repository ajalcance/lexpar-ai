/**
 * File: src/pages/Courts.tsx
 * Purpose: The owner's Courts surface (§13) — create a Court and upload its OFFICIAL rule documents
 *   (with source provenance), showing each document's ingestion status. No roles: every account
 *   manages its OWN courts (the backend scopes every route to the owner). Functional, not polished.
 * Depends on: @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: backend/app/api/courts.py, scripts/seed_court.py, docs/ARCHITECTURE.md §13
 * Security notes: Only official, owner-sourced documents belong here — the upload form carries
 *   provenance fields (citation + source) for the §13 audit trail. Never AI-generated text.
 */

import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Landmark, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { LINE_MAX, TEXT_MAX } from '@/lib/limits';
import { DESTRUCTIVE_ACTIONS_ENABLED } from '@/lib/flags';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';

export function Courts() {
  const queryClient = useQueryClient();

  const [courtName, setCourtName] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [selectedCourtId, setSelectedCourtId] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [ruleFile, setRuleFile] = useState<File | null>(null);
  const [ruleTitle, setRuleTitle] = useState('');
  const [sourceCitation, setSourceCitation] = useState('');
  const [sourceReference, setSourceReference] = useState('');

  // The owner's full catalog: every forum they own including archived ones (they stay visible —
  // and purgeable — instead of vanishing). Key is namespaced under ['courts'] so create/archive/
  // purge can invalidate both this and the case-creation (active-only) list with one prefix.
  const { data: courts } = useQuery({
    queryKey: ['courts', 'all'],
    queryFn: () => api.getCourts({ includeArchived: true }),
  });
  const selectedCourt = courts?.find((court) => court.id === selectedCourtId);
  // The list is the landing view; the create form is a toggled affordance — auto-open only when
  // the catalog is empty (nothing to list yet, creation is the only sensible next step).
  const createOpen = showCreate || courts?.length === 0;
  const { data: ruleDocs } = useQuery({
    queryKey: ['court-rules', selectedCourtId],
    queryFn: () => api.getCourtRules(selectedCourtId),
    enabled: !!selectedCourtId && !selectedCourt?.archived,
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
      setShowCreate(false);
      setSelectedCourtId(court.id);
      await queryClient.invalidateQueries({ queryKey: ['courts'] });
      toast.success(`Court "${court.name}" created — upload its rule PDFs below.`);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : 'Could not create the court.'),
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
      toast.success('Rule document uploaded — ingesting now.');
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : 'Upload failed.'),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-primary uppercase">
          <Landmark className="size-3.5" />
          Courts
        </div>
        <h1 className="mt-1 text-2xl font-semibold">Your courts</h1>
        <p className="text-sm text-muted-foreground">
          Manage the forums and the official procedural rules that ground the AI in your cases.
        </p>
      </div>

      {/* The catalog is the landing view (mirrors the Cases dashboard): every forum listed —
          archived ones included, badged. Creation is a separate, clearly-delineated card below. */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-lg">Existing courts</CardTitle>
              <CardDescription>
                Every forum in the catalog. Select one to manage its rule corpus.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowCreate((open) => !open)}>
              <Plus className="size-4" />
              New court
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {courts?.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No courts yet — create the first forum below.
            </p>
          )}
          {courts && courts.length > 0 && (
            <div className="flex flex-col gap-2">
              {courts.map((court) => (
                <button
                  key={court.id}
                  type="button"
                  onClick={() => setSelectedCourtId(court.id)}
                  className={cn(
                    'flex items-center justify-between gap-3 rounded-md border px-4 py-3 text-left text-sm transition-colors hover:border-primary/40',
                    selectedCourtId === court.id && 'border-primary bg-muted/40',
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{court.name}</span>
                    {court.archived && <Badge variant="outline">Archived</Badge>}
                  </span>
                  {court.jurisdictionDescription && (
                    <span className="truncate text-xs text-muted-foreground">
                      {court.jurisdictionDescription}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create — a distinct card (blue "action" accent) so it's never mistaken for a court row. */}
      {createOpen && (
        <Card className="border-blue-500/30 border-l-4 border-l-blue-500 bg-blue-500/5">
          <CardHeader>
            <CardTitle className="text-lg">Create a court</CardTitle>
            <CardDescription>Add a forum, then upload its official rule PDFs below.</CardDescription>
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
                  maxLength={LINE_MAX}
                  value={courtName}
                  onChange={(event) => setCourtName(event.target.value)}
                  placeholder="e.g. Special Commercial Court, RTC Branch 9"
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="jurisdiction">Jurisdiction description</Label>
                <Input
                  id="jurisdiction"
                  maxLength={TEXT_MAX}
                  value={jurisdiction}
                  onChange={(event) => setJurisdiction(event.target.value)}
                  placeholder="Optional — the forum this court covers"
                />
              </div>
              {createCourt.isError && (
                <p className="text-sm text-destructive">Could not create the court.</p>
              )}
              <div className="flex gap-2">
                <Button type="submit" disabled={createCourt.isPending}>
                  Create court
                </Button>
                {courts && courts.length > 0 && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowCreate(false)}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Rule documents{selectedCourt ? ` — ${selectedCourt.name}` : ''}
          </CardTitle>
          <CardDescription>
            Upload OFFICIAL rule documents only (court issuances, statutes from government
            sources) — record where each came from. The AI cites only what is ingested here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!selectedCourt && (
            <p className="text-sm text-muted-foreground">
              Select a court above to manage its rules.
            </p>
          )}

          {selectedCourt?.archived && (
            <p className="text-sm text-muted-foreground">
              This forum is archived — its rules are out of retrieval and uploads are closed. You
              can purge it permanently below.
            </p>
          )}

          {selectedCourt && !selectedCourt.archived && (
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
                maxLength={LINE_MAX}
                    value={ruleTitle}
                    onChange={(event) => setRuleTitle(event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="sourceCitation">Source citation</Label>
                  <Input
                    id="sourceCitation"
                maxLength={LINE_MAX}
                    value={sourceCitation}
                    onChange={(event) => setSourceCitation(event.target.value)}
                    placeholder="Formal citation of the instrument"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="sourceReference">Source URL / reference</Label>
                  <Input
                    id="sourceReference"
                maxLength={LINE_MAX}
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

      {selectedCourt && DESTRUCTIVE_ACTIONS_ENABLED && (
        <CourtDangerZone
          courtId={selectedCourt.id}
          courtName={selectedCourt.name}
          archived={selectedCourt.archived}
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
  archived,
  onGone,
}: {
  courtId: string;
  courtName: string;
  /** Already archived → only Purge is offered (re-archiving is meaningless and the route 404s). */
  archived: boolean;
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
          {!archived && (
            <Button
              variant="outline"
              size="sm"
              disabled={archive.isPending}
              onClick={() => setConfirming('archive')}
            >
              Archive court
            </Button>
          )}
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
