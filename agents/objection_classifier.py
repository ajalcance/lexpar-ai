"""
File: agents/objection_classifier.py
Purpose: The bespoke, differentiating piece. Eventually watches Deepgram's live partial
    transcript of the attorney's speech and decides, in real time, when Opposing Counsel should
    interrupt with an objection (leading, hearsay, speculation, etc.). Kept isolated and
    independently testable so interruption behavior can be tuned without touching the pipeline.
Depends on: live partial transcript stream (Deepgram STT), a lightweight classifier/heuristics
Related: docs/ARCHITECTURE.md §6, agents/opposing_counsel.py (acts on its signal),
    docs/DEVELOPER_GUIDELINES.md §6 (highest-priority module to unit test)
Security notes: Processes live transcript text (work product) in memory only — never log it.
"""

# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are available
