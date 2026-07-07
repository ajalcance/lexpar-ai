/**
 * File: src/components/TranscriptLine.tsx
 * Purpose: Renders a single transcript line, styled by speaker. The one line flagged as an
 *   interruption (an opposing-counsel objection) gets a distinct destructive treatment — an
 *   "OBJECTION" badge and red accent — so barge-ins are visually unmistakable.
 * Depends on: components/ui/badge, lib/types.ts, lib/utils (cn)
 * Related: pages/SparringRoom.tsx, hooks/useSparringSession.ts
 * Security notes: Displays transcript content (attorney work product) for the live session
 *   only. Rendered, never logged.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { SpeakerRole, Transcript } from '@/lib/types';

const SPEAKER_LABEL: Record<SpeakerRole, string> = {
  attorney: 'You (Attorney)',
  opposing_counsel: 'Opposing Counsel',
  judge: 'Judge',
};

/** Alignment per speaker so the exchange reads like a conversation. */
const SPEAKER_ALIGN: Record<SpeakerRole, string> = {
  attorney: 'items-start',
  opposing_counsel: 'items-end',
  judge: 'items-center',
};

const SPEAKER_BUBBLE: Record<SpeakerRole, string> = {
  attorney: 'bg-card',
  opposing_counsel: 'bg-secondary',
  judge: 'bg-muted italic',
};

interface TranscriptLineProps {
  line: Transcript;
}

export function TranscriptLine({ line }: TranscriptLineProps) {
  const { speaker, content, wasInterruption } = line;

  return (
    <div className={cn('flex flex-col gap-1', SPEAKER_ALIGN[speaker])}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {SPEAKER_LABEL[speaker]}
        </span>
        {wasInterruption && <Badge variant="destructive">Objection</Badge>}
      </div>
      <div
        className={cn(
          'max-w-lg rounded-lg border px-4 py-2 text-sm',
          wasInterruption
            ? 'border-destructive/50 bg-destructive/10 font-medium text-destructive'
            : SPEAKER_BUBBLE[speaker],
        )}
      >
        {content}
      </div>
    </div>
  );
}
