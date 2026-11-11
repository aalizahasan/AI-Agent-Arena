"""Test Gemini adapter setup without making real model calls."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.interpreter import LLMInterpreter, enforce_explicit_details
from app.models import Interpretation


def test_gemini_uses_google_compatible_endpoint(monkeypatch):
    fake_constructor = MagicMock()
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=fake_constructor))
    model = LLMInterpreter('placeholder-test-key', 'gemini-3.8-flash', 'gemini')
    assert model.provider == 'gemini'
    assert model.model == 'gemini-3.8-flash'
    assert fake_constructor.call_args.kwargs['base_url'] == 'https://generativelanguage.googleapis.com/v1beta/openai/'


def test_openai_remains_optional(monkeypatch):
    fake_constructor = MagicMock()
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=fake_constructor))
    model = LLMInterpreter('placeholder-test-key', 'gpt-4o-mini', 'openai')
    assert model.provider == 'openai'
    assert 'base_url' not in fake_constructor.call_args.kwargs


def test_unsupported_provider_fails_closed():
    try:
        LLMInterpreter('placeholder-test-key', 'unknown-model', 'wrong-provider')
    except ValueError as error:
        assert 'LLM_PROVIDER' in str(error)
    else:
        raise AssertionError('Unknown LLM provider must be rejected')


def test_gemini_extraction_contract():
    parsed = Interpretation(intent='BOOK', requested_date='2026-11-16', requested_time='10:00')
    parsed = enforce_explicit_details('Please book 16 November at 10 AM', parsed)
    assert parsed.requested_date == '2026-11-16'
    assert parsed.requested_time == '10:00'
