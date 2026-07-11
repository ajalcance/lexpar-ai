/**
 * File: src/components/RuleDocumentRow.tsx
 * Purpose: One rule document in the admin corpus list, with the two-tier deletion controls (§13):
 *   Replace (atomic supersede — the routine "corrected version" action), Archive (soft,
 *   reversible), Restore (blocked while superseded), and Purge — deliberately high-friction:
 *   opens a separate confirm area showing the provenance-impact count and requiring the document
 *   title typed back, so it is never one accidental click away from the routine actions.
 * Depends on: react, @tanstack/react-query, lib/api.ts, lib/types.ts, components/ui/*
 * Related: pages/Admin.tsx (renders one per document), backend/app/api/courts.py (the routes)
 * Security notes: Admin-only surface (page-gated + every backend route re-checks the role).
 */

import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import * as api from '@/lib/api';
import type { CourtRuleDocument } from '@/lib/types';

const STATUS_VARIANT = {
  pending: 'secondary',
  ready: 'outline',
  failed: 'destructive',
} as const;

interface Props {
  courtId: string;
  doc: CourtRuleDocument;
}

export function RuleDocumentRow({ courtId, doc }: Props) {
  const queryClient = useQueryClient();
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const [confirmingPurge, setConfirmingPurge] = useState(false);
  const [purgeTitle, setPurgeTitle] = useState('');
  const [error, setError] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['court-rules', courtId] });
  const onError = (err: unknown) =>
    setError(err instanceof Error ? err.message : 'Action failed. Try again.');

  const replace = useMutation({
    mutationFn: (file: File) => api.replaceCourtRule(courtId, doc.id, file),
    onSuccess: refresh,
    onError,
  });
  const archive = useMutation({
    mutationFn: () => api.archiveCourtRule(courtId, doc.id),
    onSuccess: refresh,
    onError,
  });
  const restore = useMutation({
    mutationFn: () => api.restoreCourtRule(courtId, doc.id),
    onSuccess: refresh,
    onError,
  });
  const purge = useMutation({
    mutationFn: () => api.purgeCourtRule(courtId, doc.id),
    onSuccess: () => {
      setConfirmingPurge(false);
      void refresh();
    },
    onError,
  });
  // The loud warning: fetched only when the purge confirm area is open.
  const { data: impact } = useQuery({
    queryKey: ['rule-purge-impact', doc.id],
    queryFn: () => api.getCourtRulePurgeImpact(courtId, doc.id),
    enabled: confirmingPurge,
  });

  const busy = replace.isPending || archive.isPending || restore.isPending || purge.isPending;

  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={doc.archived ? 'font-medium text-muted-foreground line-through' : 'font-medium'}>
          {doc.title}
        </span>
        {doc.sourceCitation && (
          <span className="text-muted-foreground">{doc.sourceCitation}</span>
        )}
        <Badge variant={STATUS_VARIANT[doc.ingestionStatus]}>
          {doc.ingestionStatus}
          {doc.ingestionStatus === 'ready' ? ` — ${doc.chunkCount} chunks` : ''}
        </Badge>
        {doc.archived && (
          <Badge variant="secondary">{doc.superseded ? 'superseded' : 'archived'}</Badge>
        )}
        {doc.error && <span className="text-destructive">{doc.error}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {!doc.archived && (
          <>
            {/* Replace: the routine corrected-version action (atomic supersede). */}
            <input
              ref={replaceInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              data-testid={`replace-file-${doc.id}`}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) replace.mutate(file);
                event.target.value = '';
              }}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => replaceInputRef.current?.click()}
            >
              {replace.isPending ? 'Replacing…' : 'Replace…'}
            </Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => archive.mutate()}>
              Archive
            </Button>
          </>
        )}
        {doc.archived && !doc.superseded && (
          <Button variant="outline" size="sm" disabled={busy} onClick={() => restore.mutate()}>
            Restore
          </Button>
        )}
        {!confirmingPurge ? (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto text-destructive hover:text-destructive"
            disabled={busy}
            onClick={() => setConfirmingPurge(true)}
          >
            Purge…
          </Button>
        ) : null}
      </div>

      {confirmingPurge && (
        <div className="flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="text-sm text-destructive">
            Purge permanently deletes this document, its {doc.chunkCount} chunks, and the stored
            file. {impact ? `${impact.provenanceRulings} past ruling(s) cite it — their audit trail
            will no longer resolve to source text.` : 'Checking audit-trail impact…'} This cannot
            be undone.
          </p>
          <label className="text-xs text-muted-foreground" htmlFor={`purge-confirm-${doc.id}`}>
            Type the document title to confirm
          </label>
          <Input
            id={`purge-confirm-${doc.id}`}
            value={purgeTitle}
            onChange={(event) => setPurgeTitle(event.target.value)}
            placeholder={doc.title}
          />
          <div className="flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              disabled={purgeTitle !== doc.title || purge.isPending}
              onClick={() => purge.mutate()}
            >
              {purge.isPending ? 'Purging…' : 'Purge permanently'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setConfirmingPurge(false);
                setPurgeTitle('');
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
