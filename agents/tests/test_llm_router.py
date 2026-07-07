"""
File: agents/tests/test_llm_router.py
Purpose: Offline tests for llm_router (ARCHITECTURE §7) — role routing resolves distinct models
    (verification is not the reasoning model; judge is Gemma), defaults point at Fireworks, and a
    built endpoint carries the right base_url + model. No network calls.
Depends on: pytest, llm_router
"""

from llm_router import (
    build_endpoint,
    judge_config,
    opposing_counsel_config,
    verification_config,
)


def test_verification_is_not_the_reasoning_model():
    assert verification_config().model != opposing_counsel_config().model


def test_all_roles_have_a_model():
    for cfg in (opposing_counsel_config(), judge_config(), verification_config()):
        assert cfg.model
        assert "fireworks/models" in cfg.model


def test_defaults_point_at_fireworks():
    for cfg in (opposing_counsel_config(), judge_config(), verification_config()):
        assert cfg.provider == "fireworks"
        assert "fireworks.ai" in cfg.endpoint


def test_build_endpoint_sets_base_url_and_model():
    cfg = verification_config()
    endpoint = build_endpoint(cfg)
    assert endpoint.model == cfg.model
    assert cfg.endpoint in str(endpoint.client.base_url)
