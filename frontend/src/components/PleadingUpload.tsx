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
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';

const STATUS_LABEL: Record<api.PleadingStatus['status'], string> = {
  pending: 'Ingesting… (extracting + embedding the pleading)',
  ready: 'Ready — the AI will argue from this pleading',
  failed: 'Ingestion failed',
};

/** A visual status chip: a spinner while ingesting, a check when ready, an X on failure — so the
 *  pleading's state reads at a glance instead of as a plain sentence. */
function StatusChip({ status }: { status: api.PleadingStatus['status'] }) {
  const styles: Record<api.PleadingStatus['status'], string> = {
    pending: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    ready: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400',
    failed: 'border-destructive/30 bg-destructive/10 text-destructive',
  };
  const Icon = status === 'ready' ? CheckCircle2 : status === 'failed' ? XCircle : Loader2;
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs',
        styles[status],
      )}
    >
      <Icon className={cn('size-3.5', status === 'pending' && 'motion-safe:animate-spin')} />
      {STATUS_LABEL[status]}
    </span>
  );
}

// Mirrors the backend MAX_UPLOAD_MB default — a friendly pre-check so a large file is caught
// before the upload starts. The server (and Caddy) remain the real enforcement.
const MAX_UPLOAD_MB = 50;

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pleadings', caseId] });
      toast.success('Pleading uploaded — ingesting now.');
    },
    onError: (e) => {
      const msg = e instanceof Error ? e.message : 'Upload failed.';
      setError(msg);
      toast.error(msg);
    },
  });

  const onPick = (file: File | undefined) => {
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
    if (!file) return;
    if (file.type && file.type !== 'application/pdf') {
      setError('Please choose a PDF file.');
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`That file is too large — the limit is ${MAX_UPLOAD_MB} MB.`);
      return;
    }
    upload.mutate(file);
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
        Upload the full complaint/pleading (PDF, up to {MAX_UPLOAD_MB} MB) — Opposing Counsel and the
        Judge reason from it, not just the summary above.
      </p>
      {upload.isPending && <p className="text-sm text-muted-foreground">Uploading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {pleadings && pleadings.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {pleadings.map((p) => (
            <li key={p.id} className="flex flex-col gap-1 rounded border px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate font-medium">{p.filename}</span>
                <StatusChip status={p.status} />
              </div>
              {p.status === 'failed' && p.error && (
                <span className="text-xs text-destructive">{p.error}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
