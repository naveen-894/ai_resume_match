import pytest
from fastapi import HTTPException

from app.chatbot import security


def test_sanitize_text_strips_control_chars():
    dirty = "Hello\x00there\x07, how are you?\n"
    assert security.sanitize_text(dirty) == "Hellothere, how are you?"


def test_sanitize_text_preserves_normal_whitespace():
    text = "Line one\nLine two"
    assert security.sanitize_text(text) == "Line one\nLine two"


async def test_verify_internal_caller_noop_when_unset(monkeypatch):
    monkeypatch.setattr(security.config, "INTERNAL_API_KEY", "")
    await security.verify_internal_caller(x_chatbot_key=None)  # should not raise


async def test_verify_internal_caller_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(security.config, "INTERNAL_API_KEY", "expected-secret")
    with pytest.raises(HTTPException) as exc_info:
        await security.verify_internal_caller(x_chatbot_key="wrong")
    assert exc_info.value.status_code == 401


async def test_verify_internal_caller_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(security.config, "INTERNAL_API_KEY", "expected-secret")
    await security.verify_internal_caller(x_chatbot_key="expected-secret")  # should not raise
