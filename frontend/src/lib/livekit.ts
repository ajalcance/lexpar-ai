/**
 * File: src/lib/livekit.ts
 * Purpose: Thin wrapper over livekit-client for joining/leaving a real-time room. Installed
 *   and typed now so the real voice pipeline drops in here later; the current scripted mock
 *   session does not call these yet.
 * Depends on: livekit-client, lib/types.ts
 * Related: agents/main.py (the worker that joins the same room), lib/api.ts (getLiveKitToken),
 *   docs/ARCHITECTURE.md §6
 * Security notes: The access token grants entry to a session's audio room — treat it like a
 *   credential. Fetch it per-session from the backend (api.getLiveKitToken), never hardcode.
 */

import { Room } from 'livekit-client';
import type { LiveKitAccess } from '@/lib/types';

/** Connect to the LiveKit room described by a freshly issued access token. */
export async function connectToRoom(access: LiveKitAccess): Promise<Room> {
  const room = new Room();
  await room.connect(access.url, access.token);
  return room;
}

/** Leave and tear down a connected room. */
export async function disconnectFromRoom(room: Room): Promise<void> {
  await room.disconnect();
}
