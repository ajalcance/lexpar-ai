"""
File: agents/opposing_counsel.py
Purpose: The Opposing Counsel agent persona. Eventually cross-examines, raises objections, and
    counter-argues against the attorney's live argument, driven by the prompt in
    prompts/opposing_counsel.md and the LLM backend chosen by llm_router.
Depends on: llm_router (LLM backend), prompts/opposing_counsel.md, objection_classifier
    (decides when to interrupt), livekit-agents runtime
Related: docs/ARCHITECTURE.md §6, agents/prompts/opposing_counsel.md
Security notes: Consumes case facts and live transcript (work product) as prompt context —
    never log that context in plaintext.
"""

# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are available
