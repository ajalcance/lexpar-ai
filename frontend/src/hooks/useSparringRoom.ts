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
import { objectionEventToLine, parseObjectionData } from '@/lib/objectionEvent';
import type { Transcript } from '@/lib/types';

export type SparringMode = 'connecting' | 'live' | 'fallback';
export type ConnStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed';
export type ActiveSpeaker = 'you' | 'opposing_counsel' | null;

/** How long to wait for the agent to join before falling back to the scripted mock. */
const AGENT_JOIN_TIMEOUT_MS = 5000;

/** Force a fallback if the connection neither connects nor fails within this window (stalled ICE). */
const CONNECT_TIMEOUT_MS = 8000;

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
  const [objections, setObjections] = useState<Transcript[]>([]);
  const roomRef = useRef<Room | null>(null);

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
        room.on(RoomEvent.DataReceived, (payload) => {
          // Gap 3: an objection event from the agent → render it via the existing TranscriptLine.
          if (cancelled) return;
          const event = parseObjectionData(new TextDecoder().decode(payload));
          if (event) {
            setObjections((prev) => [...prev, objectionEventToLine(event, sessionId)]);
          }
        });

        setConnectionState(mapConnectionState(room.state));

        // Publish the mic — this triggers the browser permission prompt.
        try {
          await room.localParticipant.setMicrophoneEnabled(true);
          if (!cancelled) setIsMuted(false);
        } catch {
          if (!cancelled) setMicBlocked(true);
        }

        // Live now if the agent is already here; otherwise show the mock after the timeout while
        // staying connected (a later ParticipantConnected still promotes us to live).
        if (room.remoteParticipants.size > 0) {
          promoteToLive();
        } else {
          agentTimer = setTimeout(() => {
            if (!cancelled) setMode('fallback');
          }, AGENT_JOIN_TIMEOUT_MS);
        }
      } catch {
        clearTimeout(connectTimer);
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
      const room = roomRef.current;
      if (room) {
        void disconnectFromRoom(room);
      }
      roomRef.current = null;
      audioEls.forEach((el) => el.remove());
    };
  }, [sessionId]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const enabled = room.localParticipant.isMicrophoneEnabled;
    try {
      await room.localParticipant.setMicrophoneEnabled(!enabled);
      setIsMuted(enabled);
    } catch {
      setMicBlocked(true);
    }
  }, []);

  return { mode, connectionState, activeSpeaker, isMuted, micBlocked, toggleMute, objections };
}
