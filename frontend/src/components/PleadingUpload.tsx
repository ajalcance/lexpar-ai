/**
 * File: src/components/PleadingUpload.tsx
 * Purpose: Attach a pleading (PDF) to a case and show ingestion status (§12). Uploading kicks off
 *   backend extraction → chunking → embedding; the row polls until it's 'ready' (the agents can
 *   then ground objections/rulings in it) or 'failed'.
 * Depends on: react, @tanstack/react-query, lib/api.ts, components/ui/*
 * Related: pages/CaseUpload.tsx, backend/app/api/cases.py (POST/GET /api/cases/{id}/documents)
 * Security notes: the file is attorney work product — uploaded to the API only, never logged.
 */

import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import * as api from '@/lib/api';

const STATUS_LABEL: Record<api.PleadingStatus['status'], string> = {
  pending: 'Ingesting… (extracting + embedding the pleading)',
  ready: 'Ready — the AI will argue from this pleading',
  failed: 'Ingestion failed',
};

export function PleadingUpload({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: pleadings } = useQuery({
    queryKey: ['pleadings', caseId],
    queryFn: () => api.listPleadings(caseId),
    // poll while anything is still ingesting so 'pending' → 'ready' updates on its own
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.status === 'pending') ? 2000 : false,
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadPleading(caseId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pleadings', caseId] }),
    onError: (e) => setError(e instanceof Error ? e.message : 'Upload failed.'),
  });

  const onPick = (file: File | undefined) => {
    setError(null);
    if (file) upload.mutate(file);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="flex flex-col gap-3">
      <Label htmlFor="pleading">Attach the pleading (PDF)</Label>
      <Input
        id="pleading"
        ref={inputRef}
        type="file"
        accept="application/pdf"
        disabled={upload.isPending}
        onChange={(e) => onPick(e.target.files?.[0])}
      />
      <p className="text-xs text-muted-foreground">
        Upload the full complaint/pleading — Opposing Counsel and the Judge reason from it, not just
        the summary above.
      </p>
      {upload.isPending && <p className="text-sm text-muted-foreground">Uploading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {pleadings && pleadings.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {pleadings.map((p) => (
            <li key={p.id} className="flex items-center justify-between rounded border px-3 py-2">
              <span className="truncate">{p.filename}</span>
              <span
                className={
                  p.status === 'failed'
                    ? 'text-destructive'
                    : p.status === 'ready'
                      ? 'text-foreground'
                      : 'text-muted-foreground'
                }
              >
                {STATUS_LABEL[p.status]}
                {p.status === 'failed' && p.error ? ` — ${p.error}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
