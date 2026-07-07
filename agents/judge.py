"""
File: agents/judge.py
Purpose: The Judge agent persona. Eventually monitors the exchange, rules on objections raised by
    Opposing Counsel, delivers a spoken closing ruling, and writes the session scorecard back
    through the backend. Driven by prompts/judge.md.
Depends on: llm_router (LLM backend, stays on Fireworks/Gemma), prompts/judge.md, backend
    scorecard persistence, livekit-agents runtime
Related: docs/ARCHITECTURE.md §6/§7, agents/prompts/judge.md, backend/app/models/scorecard.py
Security notes: The ruling and scorecard derive from attorney work product — persist only via the
    backend models, never log their contents.
"""

# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are available
