/**
 * File: src/components/TranscriptLine.tsx
 * Purpose: Renders a single transcript line, styled by speaker. Each role carries a color identity
 *   shared with the SparringVisualizer presence dots (blue = You, red = Opposing Counsel,
 *   amber = Judge) — a leading colored dot on the label + a role-tinted bubble border — so the
 *   transcript scans at a glance and reads as one system with the live-audio visual. The one line
 *   flagged as an interruption (an opposing-counsel objection) gets a distinct destructive
 *   treatment — an "OBJECTION" badge and red accent — so barge-ins are visually unmistakable.
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
  attorney: 'bg-card border-blue-500/40',
  opposing_counsel: 'bg-secondary border-red-500/40',
  judge: 'bg-muted italic border-amber-500/40',
};

/** Role color identity, shared with SparringVisualizer's presence dots. */
const SPEAKER_DOT: Record<SpeakerRole, string> = {
  attorney: 'bg-blue-500',
  opposing_counsel: 'bg-red-500',
  judge: 'bg-amber-500',
};

interface TranscriptLineProps {
  line: Transcript;
  /** §13: citations flagged as ungrounded in this session's rulings (from RulingProvenance).
   *  A line whose content carries one gets an "Unverified citation" marker. */
  flaggedCitations?: string[];
}

export function TranscriptLine({ line, flaggedCitations = [] }: TranscriptLineProps) {
  const { speaker, content, wasInterruption } = line;
  const hasFlaggedCitation = flaggedCitations.some((citation) =>
    content.toLowerCase().includes(citation.toLowerCase()),
  );

  return (
    <div className={cn('flex flex-col gap-1', SPEAKER_ALIGN[speaker])}>
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className={cn('size-2 rounded-full', wasInterruption ? 'bg-red-500' : SPEAKER_DOT[speaker])}
        />
        <span className="text-xs font-medium text-muted-foreground">
          {SPEAKER_LABEL[speaker]}
        </span>
        {wasInterruption && <Badge variant="destructive">Objection</Badge>}
        {hasFlaggedCitation && <Badge variant="destructive">Unverified citation</Badge>}
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
