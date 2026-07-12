/**
 * File: src/hooks/useSparringRoom.ts
 * Purpose: Owns the real LiveKit connection for a sparring session (Gap 1/2) — fetches the room
 *   token, connects via lib/livekit.ts, publishes the browser microphone (which triggers the
 *   permission prompt), plays the agent's audio, and exposes real connection-state, active-speaker,
 *   and mute state. Decides live vs. fallback: if the token/connect fails, or no agent joins within
 *   a few seconds, callers fall back to the scripted mock; a later agent join promotes to live.
 * Depends on: livekit-client, lib/livekit.ts (connectToRoom/disconnectFromRoom), lib/api.ts (token)
 * Related: pages/SparringRoom.tsx (consumer), hooks/useSparringSession.ts (the fallback script)
 * Security notes: The token grants room access — fetched per session, held in memory, never logged.
 *   Microphone audio is published to the session room only.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ConnectionState, RoomEvent, Track } from 'livekit-client';
import type { Participant, RemoteTrack, Room } from 'livekit-client';
import {
  JUDGE_IDENTITY,
  mapActiveSpeaker,
  mapAudioLevels,
  type ActiveSpeaker,
  type AudioLevels,
} from '@/lib/activeSpeaker';
import type { VisualizedTrack } from '@/hooks/useAudioVisualization';
import * as api from '@/lib/api';
import { connectToRoom, disconnectFromRoom } from '@/lib/livekit';
import {
  objectionEventToLine,
  parseJudgeSpeaking,
  parseObjectionData,
  parseRulingData,
  parseTranscriptData,
  rulingEventToLine,
  transcriptEventToLine,
} from '@/lib/objectionEvent';
import type { Transcript } from '@/lib/types';

export type SparringMode = 'connecting' | 'live' | 'fallback';
export type ConnStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed';
export type { ActiveSpeaker } from '@/lib/activeSpeaker';

/** How long to wait for the agent to join before falling back to the scripted mock. */
const AGENT_JOIN_TIMEOUT_MS = 5000;

/** Force a fallback if the connection neither connects nor fails within this window (stalled ICE). */
const CONNECT_TIMEOUT_MS = 8000;

/** Max wait for the agent to deliver the judge's ruling + write the scorecard before navigating
 *  anyway. This is a SAFETY NET for a missing/broken agent, NOT the normal path (that's the
 *  `end_complete` signal) — so it must comfortably exceed the longest real end-of-session:
 *  the `assess_session` LLM call (reasons over the whole transcript — can be 15-25s on a long
 *  session) PLUS the spoken closing ruling PLUS persistence. At 30s it fired mid-ruling on long
 *  sessions and navigated away, cutting the judge off. 90s covers a long deliberation + ruling;
 *  a truly-dead agent is caught sooner by the room's Disconnected event, so the long wait only
 *  applies to the rare hung-but-connected case. */
const END_SESSION_TIMEOUT_MS = 90000;

function mapConnectionState(state: ConnectionState): ConnStatus {
  switch (state) {
    case ConnectionState.Connected:
      return 'connected';
    case ConnectionState.Connecting:
      return 'connecting';
    case ConnectionState.Reconnecting:
    case ConnectionState.SignalReconnecting:
      return 'reconnecting';
    default:
      return 'disconnected';
  }
}

export function useSparringRoom(sessionId: string) {
  const [mode, setMode] = useState<SparringMode>('connecting');
  const [connectionState, setConnectionState] = useState<ConnStatus>('connecting');
  const [activeSpeaker, setActiveSpeaker] = useState<ActiveSpeaker>(null);
  // The active speaker's audio track (drives the equalizer) + coarse per-role levels (the dots).
  const [activeTrack, setActiveTrack] = useState<VisualizedTrack | null>(null);
  const [audioLevels, setAudioLevels] = useState<AudioLevels>({
    you: 0,
    opposing_counsel: 0,
    judge: 0,
  });
  const [isMuted, setIsMuted] = useState(false);
  const [micBlocked, setMicBlocked] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [judgeSpeaking, setJudgeSpeaking] = useState(false);
  // The live written transcript — every committed line in ARRIVAL order (stable, no re-sorting so
  // lines never jump): attorney statements, OC counter-arguments, objections (red), inline
  // rulings, and the judge's order line. Objection/ruling events carry their own styling.
  const [transcript, setTranscript] = useState<Transcript[]>([]);
  const roomRef = useRef<Room | null>(null);
  // Resolves the endSession() promise when the agent's `end_complete` arrives (ruling delivered +
  // scorecard written), so the page navigates only after the judge has spoken.
  const endResolverRef = useRef<(() => void) | null>(null);
  // Dedup keys for data-channel events, shared across effect re-runs (a ref, not per-effect state)
  // so a double-registered listener / reconnect can't double-render one event. Reset per session.
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setTranscript([]); // clear any prior session's transcript lines
    setJudgeSpeaking(false);
    setActiveTrack(null);
    setAudioLevels({ you: 0, opposing_counsel: 0, judge: 0 });
    if (!sessionId) {
      return;
    }
    // Dedup keys for data-channel events (objection/ruling); the set is a ref shared across effect
    // re-runs, cleared here per session. markSeen returns true the first time a key is seen (render
    // it) and false thereafter (drop the duplicate).
    seenRef.current = new Set<string>();
    const markSeen = (key: string): boolean => {
      if (seenRef.current.has(key)) return false;
      seenRef.current.add(key);
      return true;
    };
    let cancelled = false;
    let settled = false;
    let connectTimer: ReturnType<typeof setTimeout> | undefined;
    let agentTimer: ReturnType<typeof setTimeout> | undefined;
    const audioEls: HTMLMediaElement[] = [];
    const attachedTracks: RemoteTrack[] = [];
    // Removes the autoplay-unblock gesture listeners (set in start(), torn down on unmount).
    let removeUnblockListeners: (() => void) | undefined;

    // Pre-connect fallback: token failed, connect rejected, or the connect stalled.
    const fallBack = () => {
      if (cancelled || settled) return;
      settled = true;
      setMode('fallback');
      setConnectionState('failed');
    };

    const attachAudio = (track: RemoteTrack) => {
      if (track.kind !== Track.Kind.Audio) {
        return;
      }
      // Dedup: a track can arrive both from the TrackSubscribed event AND the after-connect sweep
      // (attachExistingTracks) — attaching twice would create two <audio> elements → doubled audio.
      if (attachedTracks.includes(track)) {
        return;
      }
      const el = track.attach();
      el.style.display = 'none';
      document.body.appendChild(el);
      audioEls.push(el);
      attachedTracks.push(track); // kept so cleanup can detach() (not just remove the element)
    };

    // Attach any audio tracks that were ALREADY subscribed by the time we registered the
    // TrackSubscribed handler. autoSubscribe delivers tracks published before we connected (the
    // agent is usually in the room first) during room.connect(), firing TrackSubscribed BEFORE our
    // listener exists — so without this sweep those tracks (e.g. Opposing Counsel) are subscribed
    // but never attached to an <audio> element: the analyser/active-speaker still see them (bars
    // move, badge shows "speaking") while the user hears nothing.
    const attachExistingTracks = (room: Room) => {
      room.remoteParticipants.forEach((participant) => {
        participant.audioTrackPublications.forEach((publication) => {
          if (publication.track) attachAudio(publication.track);
        });
      });
    };

    const updateSpeaker = (speakers: Participant[]) => {
      if (cancelled) return;
      // Structural attribution: the Judge is a real participant (identity "judge"), so who is
      // speaking comes straight from the participant identities — no synthetic events needed.
      const label = mapActiveSpeaker(speakers);
      setActiveSpeaker(label);
      // Resolve the active speaker's audio track for the equalizer analyser (the visual reacts to
      // whoever the badge names), and the coarse per-role levels for the presence dots — both from
      // the same ActiveSpeakersChanged payload, no extra analyser for the dots.
      let active: Participant | undefined;
      if (label === 'judge') {
        active = speakers.find((p) => !p.isLocal && p.identity === JUDGE_IDENTITY);
      } else if (label === 'opposing_counsel') {
        active = speakers.find((p) => !p.isLocal);
      } else if (label === 'you') {
        active = speakers.find((p) => p.isLocal);
      }
      const publication = active?.audioTrackPublications.values().next().value;
      // Stable Track reference per participant, so re-emits with the same speaker don't churn the
      // analyser (React bails on an identical setState value). audioTrackPublications only holds
      // audio tracks, so the subscribed track is a Local/RemoteAudioTrack.
      setActiveTrack((publication?.track as VisualizedTrack | undefined) ?? null);
      setAudioLevels(mapAudioLevels(speakers));
    };

    const promoteToLive = () => {
      if (cancelled) return;
      clearTimeout(agentTimer);
      setMode('live');
    };

    async function start() {
      setMode('connecting');
      setConnectionState('connecting');
      connectTimer = setTimeout(fallBack, CONNECT_TIMEOUT_MS); // stalled connect → fall back
      try {
        const access = await api.getLiveKitToken(sessionId);
        if (cancelled || settled) return;
        const room = await connectToRoom(access);
        clearTimeout(connectTimer);
        if (cancelled || settled) {
          void disconnectFromRoom(room);
          return;
        }
        settled = true;
        roomRef.current = room;

        room.on(RoomEvent.ConnectionStateChanged, (state) => {
          if (!cancelled) setConnectionState(mapConnectionState(state));
        });
        room.on(RoomEvent.ActiveSpeakersChanged, updateSpeaker);
        room.on(RoomEvent.TrackSubscribed, (track) => attachAudio(track));
        room.on(RoomEvent.ParticipantConnected, promoteToLive);
        // A terminal drop (auto-reconnect exhausted / server closed the room). Surface it clearly
        // and log the reason instead of leaving a dead-but-"live"-looking view. Intentional
        // disconnects during unmount are ignored via the `cancelled` guard.
        room.on(RoomEvent.Disconnected, (reason) => {
          if (cancelled) return;
          console.warn('[SparringRoom] LiveKit disconnected', reason);
          setConnectionState('disconnected');
        });
        // Browsers may block audio playback until a user gesture; surface an "enable audio" path
        // rather than the agent being silently inaudible.
        room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
          if (!cancelled) setAudioBlocked(!room.canPlaybackAudio);
        });
        room.on(RoomEvent.DataReceived, (payload) => {
          if (cancelled) return;
          const text = new TextDecoder().decode(payload);
          // Judge-speaking boundary: the judge shares the OC agent participant, so this is how the
          // active-speaker label knows the current audio is the Judge, not Opposing Counsel.
          const speaking = parseJudgeSpeaking(text);
          if (speaking !== null) {
            setJudgeSpeaking(speaking);
            return;
          }
          // Live written transcript: a committed speech turn (attorney / OC / judge order).
          const turn = parseTranscriptData(text);
          if (turn) {
            if (markSeen(`transcript:${turn.speaker}:${turn.timestamp}`)) {
              setTranscript((prev) => [...prev, transcriptEventToLine(turn, sessionId)]);
            }
            return;
          }
          // Gap 3: an objection event from the agent → render it via the existing TranscriptLine.
          const event = parseObjectionData(text);
          if (event) {
            // Dedup on the agent's stable timestamp: a redelivered packet or a double-registered
            // listener must not double-render one objection (the live double-hearsay bug).
            if (markSeen(`objection:${event.timestamp}`)) {
              setTranscript((prev) => [...prev, objectionEventToLine(event, sessionId)]);
            }
            return;
          }
          // Inline judge ruling ("Sustained/Overruled — <reason>") → render as a judge line.
          const ruling = parseRulingData(text);
          if (ruling) {
            if (markSeen(`ruling:${ruling.timestamp}`)) {
              setTranscript((prev) => [...prev, rulingEventToLine(ruling, sessionId)]);
            }
            return;
          }
          // Control channel: the agent finished delivering the judge's ruling + wrote the scorecard.
          try {
            const message = JSON.parse(text) as { type?: string };
            if (message?.type === 'end_complete' && endResolverRef.current) {
              endResolverRef.current();
              endResolverRef.current = null;
            }
          } catch {
            /* not a control message */
          }
        });

        // Now that the TrackSubscribed handler is registered, attach anything already subscribed
        // during connect() (Fix for the "bars move but no audio" bug — see attachExistingTracks).
        attachExistingTracks(room);

        setConnectionState(mapConnectionState(room.state));

        // Publish the mic — this triggers the browser permission prompt.
        try {
          await room.localParticipant.setMicrophoneEnabled(true);
          if (!cancelled) setIsMuted(false);
        } catch (err) {
          if (!cancelled) setMicBlocked(true);
          console.warn('[SparringRoom] microphone unavailable', err);
        }

        // Try to start audio playback now (works if we're still in the click's gesture context);
        // if the browser blocks it, `audioBlocked` drives an "enable audio" affordance.
        try {
          await room.startAudio();
        } catch {
          /* blocked — reflected via canPlaybackAudio below */
        }
        if (!cancelled) setAudioBlocked(!room.canPlaybackAudio);

        // Autoplay safety net (the no-audio bug): if playback is blocked (we arrived by navigation,
        // not a click), unblock it on the next user interaction anywhere on the page. Registered
        // UNCONDITIONALLY — canPlaybackAudio can read true here (before any track is playing) and
        // flip false later when audio actually arrives, so gating on it now would skip the listener
        // and leave the user stuck. They persist until playback actually succeeds, then self-remove;
        // the explicit "Enable audio" button remains as a visible fallback.
        const unblock = () => {
          roomRef.current
            ?.startAudio()
            .then(() => {
              if (cancelled) return;
              const canPlay = !!roomRef.current?.canPlaybackAudio;
              setAudioBlocked(!canPlay);
              if (canPlay) removeUnblockListeners?.();
            })
            .catch(() => undefined);
        };
        window.addEventListener('pointerdown', unblock);
        window.addEventListener('keydown', unblock);
        removeUnblockListeners = () => {
          window.removeEventListener('pointerdown', unblock);
          window.removeEventListener('keydown', unblock);
          removeUnblockListeners = undefined;
        };

        // Live now if the agent is already here; otherwise show the mock after the timeout while
        // staying connected (a later ParticipantConnected still promotes us to live).
        if (room.remoteParticipants.size > 0) {
          promoteToLive();
        } else {
          agentTimer = setTimeout(() => {
            if (!cancelled) setMode('fallback');
          }, AGENT_JOIN_TIMEOUT_MS);
        }
      } catch (err) {
        clearTimeout(connectTimer);
        console.error('[SparringRoom] LiveKit connect failed', err);
        fallBack();
      }
    }

    // Defer the connect one tick so React StrictMode's dev double-mount (setup → cleanup → setup)
    // collapses to a single connection instead of two racing connects with the same identity.
    const startTimer = setTimeout(() => {
      void start();
    }, 0);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      clearTimeout(connectTimer);
      clearTimeout(agentTimer);
      removeUnblockListeners?.(); // drop the window gesture listeners if they never fired
      // Release media first (detach the tracks, not just remove the elements), then drop our
      // listeners and disconnect so repeated sessions don't leak tracks or handlers.
      attachedTracks.forEach((track) => track.detach());
      audioEls.forEach((el) => el.remove());
      const room = roomRef.current;
      if (room) {
        room.removeAllListeners();
        void disconnectFromRoom(room);
      }
      roomRef.current = null;
    };
  }, [sessionId]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const enabled = room.localParticipant.isMicrophoneEnabled;
    try {
      await room.localParticipant.setMicrophoneEnabled(!enabled);
      setIsMuted(enabled);
    } catch (err) {
      setMicBlocked(true);
      console.warn('[SparringRoom] mic toggle failed', err);
    }
  }, []);

  // Called from a user gesture (button) to satisfy the browser autoplay policy when the optimistic
  // startAudio() during connect was blocked.
  const enableAudio = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.startAudio();
      setAudioBlocked(!room.canPlaybackAudio);
    } catch (err) {
      console.warn('[SparringRoom] enable audio failed', err);
    }
  }, []);

  // Ask the agent to wrap up: it delivers the judge's spoken ruling and writes the scorecard, then
  // replies `end_complete`. Resolves once that arrives (so the caller navigates only after the
  // ruling is heard) or after a timeout, so a missing/slow agent never hangs the page.
  const endSession = useCallback(async () => {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) return;
    try {
      const payload = new TextEncoder().encode(JSON.stringify({ type: 'end_session' }));
      await room.localParticipant.publishData(payload, { reliable: true, topic: 'control' });
    } catch (err) {
      console.warn('[SparringRoom] end-session signal failed', err);
      return;
    }
    await new Promise<void>((resolve) => {
      endResolverRef.current = resolve;
      setTimeout(() => {
        if (endResolverRef.current === resolve) endResolverRef.current = null;
        resolve();
      }, END_SESSION_TIMEOUT_MS);
    });
  }, []);

  return {
    mode,
    connectionState,
    activeSpeaker,
    activeTrack,
    audioLevels,
    judgeSpeaking,
    isMuted,
    micBlocked,
    audioBlocked,
    toggleMute,
    enableAudio,
    endSession,
    transcript,
  };
}
