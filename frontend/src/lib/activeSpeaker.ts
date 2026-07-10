/**
 * File: src/lib/activeSpeaker.ts
 * Purpose: Pure mapping from LiveKit active speakers to the UI's speaker label. The Judge is a
 *   REAL room participant (identity "judge", published by the agents worker), so attribution is
 *   structural: judge identity → Judge, any other remote participant → Opposing Counsel, the local
 *   participant → the attorney. Judge wins when several speak at once (you don't talk over the
 *   judge). Kept pure/livekit-free so it is unit-tested.
 * Related: hooks/useSparringRoom.ts (feeds ActiveSpeakersChanged through this),
 *   agents/judge_participant.py (publishes the judge identity), docs/ARCHITECTURE.md §6.5
 * Security notes: Operates on participant identities only — no content.
 */

export type ActiveSpeaker = 'you' | 'opposing_counsel' | 'judge' | null;

/** The identity the agents worker mints for the judge participant (judge_participant.py). */
export const JUDGE_IDENTITY = 'judge';

interface SpeakerLike {
  isLocal: boolean;
  identity: string;
}

/** Map the current active speakers to a single UI label (judge > opposing counsel > you). */
export function mapActiveSpeaker(speakers: SpeakerLike[]): ActiveSpeaker {
  if (speakers.some((p) => !p.isLocal && p.identity === JUDGE_IDENTITY)) {
    return 'judge';
  }
  if (speakers.some((p) => !p.isLocal)) {
    return 'opposing_counsel';
  }
  if (speakers.some((p) => p.isLocal)) {
    return 'you';
  }
  return null;
}

/** Coarse per-role audio levels (0..1) for the presence dots — no analyser, straight from the
 *  participants' `audioLevel` that LiveKit already reports via ActiveSpeakersChanged. Absent
 *  (non-speaking) participants stay at 0; duplicates keep the loudest. */
export interface AudioLevels {
  you: number;
  opposing_counsel: number;
  judge: number;
}

interface LevelLike extends SpeakerLike {
  audioLevel: number;
}

export function mapAudioLevels(speakers: LevelLike[]): AudioLevels {
  const levels: AudioLevels = { you: 0, opposing_counsel: 0, judge: 0 };
  for (const p of speakers) {
    const role: keyof AudioLevels = p.isLocal
      ? 'you'
      : p.identity === JUDGE_IDENTITY
        ? 'judge'
        : 'opposing_counsel';
    levels[role] = Math.max(levels[role], p.audioLevel);
  }
  return levels;
}
