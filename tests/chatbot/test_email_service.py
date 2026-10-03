import pytest

from app.chatbot import config, email_service


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    def __init__(self, status_code: int = 200, *args, **kwargs):
        self._status_code = status_code
        self.last_request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.last_request = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(self._status_code)


def _lead() -> dict:
    return {
        "name": "Jane Doe", "email": "jane@example.com", "company": "Acme",
        "requirements": "We need an AI assistant.", "service_interest": "AI Assistants",
        "budget": None, "preferred_contact": None, "conversation_summary": "Visitor: hi\nAssistant: hello",
        "source": "Website AI Chatbot",
    }


async def test_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    with pytest.raises(email_service.EmailDeliveryError):
        await email_service.send_lead_notification(_lead())


async def test_sends_to_configured_recipient(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(config, "LEAD_NOTIFICATION_EMAIL", "team@modax.in")

    fake_client = _FakeAsyncClient(status_code=200)
    monkeypatch.setattr(email_service.httpx, "AsyncClient", lambda *a, **k: fake_client)

    await email_service.send_lead_notification(_lead())

    assert fake_client.last_request["json"]["to"] == ["team@modax.in"]
    assert "Jane Doe" in fake_client.last_request["json"]["subject"]
    assert fake_client.last_request["headers"]["Authorization"] == "Bearer re_test_key"


async def test_raises_on_non_2xx_response(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test_key")
    fake_client = _FakeAsyncClient(status_code=422)
    monkeypatch.setattr(email_service.httpx, "AsyncClient", lambda *a, **k: fake_client)

    with pytest.raises(email_service.EmailDeliveryError):
        await email_service.send_lead_notification(_lead())
