import pytest
from pydantic import ValidationError

from app.chatbot.schemas import ChatMessageRequest, LeadSubmitRequest


def test_message_rejects_empty_string():
    with pytest.raises(ValidationError):
        ChatMessageRequest(session_id="s1", message="   ")


def test_message_rejects_over_length(monkeypatch):
    import app.chatbot.config as config
    monkeypatch.setattr(config, "MAX_MESSAGE_LENGTH", 10)
    with pytest.raises(ValidationError):
        ChatMessageRequest(session_id="s1", message="this message is way too long")


def test_message_accepts_valid_text():
    msg = ChatMessageRequest(session_id="s1", message="What services do you offer?")
    assert msg.message == "What services do you offer?"


def test_lead_requires_valid_email():
    with pytest.raises(ValidationError):
        LeadSubmitRequest(
            session_id="s1", name="Jane Doe", email="not-an-email",
            requirements="We need a chatbot.", consent=True,
        )


def test_lead_requires_consent():
    with pytest.raises(ValidationError):
        LeadSubmitRequest(
            session_id="s1", name="Jane Doe", email="jane@example.com",
            requirements="We need a chatbot.", consent=False,
        )


def test_lead_rejects_blank_name():
    with pytest.raises(ValidationError):
        LeadSubmitRequest(
            session_id="s1", name="   ", email="jane@example.com",
            requirements="We need a chatbot.", consent=True,
        )


def test_valid_lead_passes():
    lead = LeadSubmitRequest(
        session_id="s1", name="Jane Doe", email="jane@example.com",
        company="Acme", requirements="We need a chatbot for our HR site.",
        service_interest="AI Assistants", consent=True,
    )
    assert lead.email == "jane@example.com"
    assert lead.company == "Acme"
