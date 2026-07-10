"""
File: agents/tests/test_config.py
Purpose: Offline tests for the voice_settings plumbing (Track A expressiveness) — the env-parse
    helpers and the default OC/Judge voice_settings dicts main.py feeds into ElevenLabs. Proves the
    wiring/shape; whether the values actually SOUND more expressive needs a live pass.
Depends on: pytest, config
"""

import config


def test_getfloat_parses_and_falls_back(monkeypatch):
    monkeypatch.setenv("X_STYLE", "0.55")
    assert config._getfloat("X_STYLE", 0.3) == 0.55
    assert config._getfloat("X_UNSET", 0.3) == 0.3
    monkeypatch.setenv("X_BAD", "not-a-number")
    assert config._getfloat("X_BAD", 0.3) == 0.3  # malformed → default


def test_getbool_parses_truthy_and_falls_back(monkeypatch):
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("X_BOOL", truthy)
        assert config._getbool("X_BOOL", False) is True
    monkeypatch.setenv("X_BOOL", "0")
    assert config._getbool("X_BOOL", True) is False
    monkeypatch.delenv("X_BOOL", raising=False)
    assert config._getbool("X_BOOL", True) is True  # unset → default


def test_voice_settings_have_the_four_expected_keys():
    expected = {"stability", "similarity_boost", "style", "use_speaker_boost"}
    assert set(config.OC_VOICE_SETTINGS) == expected
    assert set(config.JUDGE_VOICE_SETTINGS) == expected


def test_voice_settings_defaults_match_the_approved_starting_values():
    # These are the Phase-2 starting values; a live pass tunes them via .env.
    assert config.OC_VOICE_SETTINGS == {
        "stability": 0.40,
        "similarity_boost": 0.75,
        "style": 0.30,
        "use_speaker_boost": False,
    }
    assert config.JUDGE_VOICE_SETTINGS == {
        "stability": 0.42,
        "similarity_boost": 0.80,
        "style": 0.38,
        "use_speaker_boost": True,
    }


def test_style_default_is_nonzero_so_delivery_is_not_flat():
    # The whole point of Track A: style was effectively 0 (unset) before. Guard against a
    # regression to flat delivery.
    assert config.OC_VOICE_SETTINGS["style"] > 0
    assert config.JUDGE_VOICE_SETTINGS["style"] > 0
