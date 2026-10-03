from app.chatbot import email_service, lead_service
from app.chatbot.models import ChatMessage, ChatSession
from app.chatbot.schemas import LeadSubmitRequest


def _lead_payload(**overrides):
    defaults = dict(
        session_id="sess-1", name="Jane Doe", email="jane@example.com",
        company="Acme Co", requirements="We need an AI assistant for our support site.",
        service_interest="AI Assistants", consent=True,
    )
    defaults.update(overrides)
    return LeadSubmitRequest(**defaults)


async def test_submit_lead_persists_and_sends_notification(db_session, monkeypatch):
    sent = {}

    async def fake_send(lead_dict):
        sent.update(lead_dict)

    monkeypatch.setattr(email_service, "send_lead_notification", fake_send)

    db_session.add(ChatSession(session_id="sess-1"))
    await db_session.commit()

    lead, is_new = await lead_service.submit_lead(db_session, _lead_payload())

    assert is_new is True
    assert lead.id is not None
    assert lead.source == "Website AI Chatbot"
    assert lead.notified_at is not None
    assert sent["email"] == "jane@example.com"


async def test_submit_lead_includes_conversation_summary(db_session, monkeypatch):
    async def fake_send(lead_dict):
        pass

    monkeypatch.setattr(email_service, "send_lead_notification", fake_send)

    db_session.add(ChatSession(session_id="sess-2"))
    db_session.add(ChatMessage(session_id="sess-2", role="user", content="What services do you offer?"))
    db_session.add(ChatMessage(session_id="sess-2", role="assistant", content="We build custom AI tools."))
    await db_session.commit()

    lead, _ = await lead_service.submit_lead(db_session, _lead_payload(session_id="sess-2"))

    assert "What services do you offer?" in lead.conversation_summary
    assert "We build custom AI tools." in lead.conversation_summary


async def test_duplicate_submission_is_idempotent(db_session, monkeypatch):
    calls = []

    async def fake_send(lead_dict):
        calls.append(lead_dict)

    monkeypatch.setattr(email_service, "send_lead_notification", fake_send)

    db_session.add(ChatSession(session_id="sess-3"))
    await db_session.commit()

    payload = _lead_payload(session_id="sess-3")
    first_lead, first_is_new = await lead_service.submit_lead(db_session, payload)
    second_lead, second_is_new = await lead_service.submit_lead(db_session, payload)

    assert first_is_new is True
    assert second_is_new is False
    assert first_lead.id == second_lead.id
    assert len(calls) == 1, "notification email must only be sent once per session"


async def test_submission_survives_email_failure(db_session, monkeypatch):
    async def failing_send(lead_dict):
        raise email_service.EmailDeliveryError("resend is down")

    monkeypatch.setattr(email_service, "send_lead_notification", failing_send)

    db_session.add(ChatSession(session_id="sess-4"))
    await db_session.commit()

    lead, is_new = await lead_service.submit_lead(db_session, _lead_payload(session_id="sess-4"))

    assert is_new is True
    assert lead.id is not None
    assert lead.notified_at is None
