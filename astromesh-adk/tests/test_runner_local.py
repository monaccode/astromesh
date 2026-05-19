"""Tests for ADKRuntime (local in-process execution)."""
import pytest

from astromesh_adk.runner import _provider_and_model


def test_provider_and_model_explicit_slash():
    assert _provider_and_model("anthropic/claude-x") == ("anthropic", "claude-x")


def test_provider_and_model_claude_bare():
    assert _provider_and_model("claude-haiku-4-5") == ("anthropic", "claude-haiku-4-5")


def test_provider_and_model_gpt_bare():
    assert _provider_and_model("gpt-4o-mini") == ("openai", "gpt-4o-mini")


def test_provider_and_model_unknown_defaults_openai():
    assert _provider_and_model("mistral-large") == ("openai", "mistral-large")
