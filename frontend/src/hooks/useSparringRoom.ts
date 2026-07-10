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
import * as api from '@/lib/api';
import { connectToRoom, disconnectFromRoom } from '@/lib/livekit';
import {
  objectionEventToLine,
  parseObjectionData,
  parseRulingData,
  rulingEventToLine,
} from '@/lib/objectionEvent';
import type { Transcript } from '@/lib/types';

export type SparringMode = 'connecting' | 'live' | 'fallback';
export type ConnStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed';
export type ActiveSpeaker = 'you' | 'opposing_counsel' | null;

/** How long to wait for the agent to join before falling back to the scripted mock. */
const AGENT_JOIN_TIMEOUT_MS = 5000;

/** Force a fallback if the connection neither connects nor fails within this window (stalled ICE). */
const CONNECT_TIMEOUT_MS = 8000;

/** Max wait for the agent to deliver the judge's ruling + write the scorecard before navigating
 *  anyway (covers the judge LLM call + spoken ruling + persistence, or a missing agent). */
const END_SESSION_TIMEOUT_MS = 30000;

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
  const [isMuted, setIsMuted] = useState(false);
  const [micBlocked, setMicBlocked] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [objections, setObjections] = useState<Transcript[]>([]);
  const roomRef = useRef<Room | null>(null);
  // Resolves the endSession() promise when the agent's `end_complete` arrives (ruling delivered +
  // scorecard written), so the page navigates only after the judge has spoken.
  const endResolverRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    setObjections([]); // clear any prior session's objection events
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    let settled = false;
    let connectTimer: ReturnType<typeof setTimeout> | undefined;
    let agentTimer: ReturnType<typeof setTimeout> | undefined;
    const audioEls: HTMLMediaElement[] = [];
    const attachedTracks: RemoteTrack[] = [];

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
      const el = track.attach();
      el.style.display = 'none';
      document.body.appendChild(el);
      audioEls.push(el);
      attachedTracks.push(track); // kept so cleanup can detach() (not just remove the element)
    };

    const updateSpeaker = (speakers: Participant[]) => {
      if (cancelled) return;
      const remoteSpeaking = speakers.some((p) => !p.isLocal);
      const localSpeaking = speakers.some((p) => p.isLocal);
      setActiveSpeaker(remoteSpeaking ? 'opposing_counsel' : localSpeaking ? 'you' : null);
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
          // Gap 3: an objection event from the agent → render it via the existing TranscriptLine.
          const event = parseObjectionData(text);
          if (event) {
            setObjections((prev) => [...prev, objectionEventToLine(event, sessionId)]);
            return;
          }
          // Inline judge ruling ("Sustained/Overruled — <reason>") → render as a judge line.
          const ruling = parseRulingData(text);
          if (ruling) {
            setObjections((prev) => [...prev, rulingEventToLine(ruling, sessionId)]);
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
    isMuted,
    micBlocked,
    audioBlocked,
    toggleMute,
    enableAudio,
    endSession,
    objections,
  };
}
