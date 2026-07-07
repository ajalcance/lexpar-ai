"""
File: agents/main.py
Purpose: Entrypoint for the LiveKit Agents worker. Eventually joins a session's LiveKit room,
    wires the real-time STT → LLM → TTS pipeline (with VAD + turn detection for barge-in), and
    attaches the Opposing Counsel and Judge agents plus the objection classifier.
Depends on: livekit-agents + STT/LLM/TTS plugins, opposing_counsel, judge, objection_classifier,
    llm_router; a room token issued by backend/app/api/livekit_token.py
Related: docs/ARCHITECTURE.md §6
Security notes: Handles live attorney audio and transcripts (work product). Never persist or log
    raw transcript content in plaintext — write only through the backend's models.
"""

# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are available
