from app.chatbot import email_service, orchestrator


def _create_session(client) -> str:
    resp = client.post("/api/chatbot/session", json={"page_url": "https://modax.in/"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["greeting"]
    assert len(body["suggested_prompts"]) >= 1
    return body["session_id"]


def test_create_session_returns_greeting_and_prompts(client):
    session_id = _create_session(client)
    assert isinstance(session_id, str) and len(session_id) > 0


def test_message_requires_known_session(client):
    resp = client.post("/api/chatbot/message", json={"session_id": "does-not-exist", "message": "hi"})
    assert resp.status_code == 404


def test_message_rejects_empty_body(client):
    session_id = _create_session(client)
    resp = client.post("/api/chatbot/message", json={"session_id": session_id, "message": "   "})
    assert resp.status_code == 422


def test_message_streams_tokens_and_sources(client, monkeypatch):
    session_id = _create_session(client)

    async def fake_handle_message(history, user_message):
        yield {"type": "sources", "sources": [{"url": "https://modax.in/services", "title": "Services"}]}
        yield {"type": "token", "content": "We offer "}
        yield {"type": "token", "content": "AI document understanding and more."}

    monkeypatch.setattr(orchestrator, "handle_message", fake_handle_message)

    resp = client.post(
        "/api/chatbot/message",
        json={"session_id": session_id, "message": "What services do you offer?"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "AI document understanding" in resp.text
    assert '"type": "done"' in resp.text or '"type":"done"' in resp.text.replace(" ", "")


def test_message_handles_orchestrator_failure_gracefully(client, monkeypatch):
    session_id = _create_session(client)

    async def failing_handle_message(history, user_message):
        raise RuntimeError("unexpected failure")
        yield  # pragma: no cover

    monkeypatch.setattr(orchestrator, "handle_message", failing_handle_message)

    resp = client.post(
        "/api/chatbot/message",
        json={"session_id": session_id, "message": "What services do you offer?"},
    )
    assert resp.status_code == 200  # the error is reported inside the SSE stream, not as an HTTP error
    assert "Something went wrong" in resp.text


def test_reset_session_clears_history(client, monkeypatch):
    session_id = _create_session(client)

    async def fake_handle_message(history, user_message):
        yield {"type": "sources", "sources": []}
        yield {"type": "token", "content": "Hello!"}

    monkeypatch.setattr(orchestrator, "handle_message", fake_handle_message)
    client.post("/api/chatbot/message", json={"session_id": session_id, "message": "Hi"})

    resp = client.delete(f"/api/chatbot/session/{session_id}")
    assert resp.status_code == 200

    resp = client.delete("/api/chatbot/session/unknown-session")
    assert resp.status_code == 404


def test_lead_submission_happy_path(client, monkeypatch):
    session_id = _create_session(client)

    async def fake_send(lead_dict):
        pass

    monkeypatch.setattr(email_service, "send_lead_notification", fake_send)

    resp = client.post(
        "/api/chatbot/lead",
        json={
            "session_id": session_id,
            "name": "Jane Doe",
            "email": "jane@example.com",
            "requirements": "We need a chatbot for our support site.",
            "service_interest": "AI Assistants",
            "consent": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_lead_submission_requires_known_session(client):
    resp = client.post(
        "/api/chatbot/lead",
        json={
            "session_id": "unknown",
            "name": "Jane Doe",
            "email": "jane@example.com",
            "requirements": "We need a chatbot.",
            "consent": True,
        },
    )
    assert resp.status_code == 404


def test_lead_submission_rejects_invalid_email(client):
    session_id = _create_session(client)
    resp = client.post(
        "/api/chatbot/lead",
        json={
            "session_id": session_id, "name": "Jane Doe", "email": "not-an-email",
            "requirements": "We need a chatbot.", "consent": True,
        },
    )
    assert resp.status_code == 422


def test_lead_submission_rejects_without_consent(client):
    session_id = _create_session(client)
    resp = client.post(
        "/api/chatbot/lead",
        json={
            "session_id": session_id, "name": "Jane Doe", "email": "jane@example.com",
            "requirements": "We need a chatbot.", "consent": False,
        },
    )
    assert resp.status_code == 422


def test_rate_limiting_on_session_creation(client):
    """CHATBOT_RATE_LIMIT_SESSION is set to 2/minute in tests/conftest.py."""
    assert client.post("/api/chatbot/session", json={}).status_code == 200
    assert client.post("/api/chatbot/session", json={}).status_code == 200
    third = client.post("/api/chatbot/session", json={})
    assert third.status_code == 429


def test_internal_api_key_enforced_when_configured(client, monkeypatch):
    from app.chatbot import config

    monkeypatch.setattr(config, "INTERNAL_API_KEY", "shared-secret")
    try:
        resp = client.post("/api/chatbot/session", json={})
        assert resp.status_code == 401

        resp = client.post(
            "/api/chatbot/session", json={}, headers={"X-Chatbot-Key": "shared-secret"}
        )
        assert resp.status_code == 200
    finally:
        monkeypatch.setattr(config, "INTERNAL_API_KEY", "")
