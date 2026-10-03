"""Lead notification email, sent via Resend's REST API.

The marketing site (Next.js) already uses Resend for its contact form, sending
to the same company inbox. This backend is Python, not Node, so rather than
duplicating the Node SDK we call Resend's plain HTTP API directly with the
same account/API key and the same destination address — reusing the existing
email integration at the provider level.
"""
import logging

import httpx

from app.chatbot import config

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailDeliveryError(Exception):
    """Raised when the notification email fails to send. Callers should log
    and continue — a failed notification must never fail the lead submission
    itself, since the lead is already safely stored in the database."""


def _render_lead_email_html(lead: dict) -> str:
    def row(label: str, value: str | None) -> str:
        return f"<p><strong>{label}:</strong> {value or 'Not provided'}</p>"

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
      <h1 style="color:#4f46e5; margin-bottom: 20px;">New Lead from the AI Chatbot</h1>
      <div style="background:#f8fafc; padding:20px; border-radius:8px; margin-bottom:20px;">
        <h2 style="margin-top:0; color:#1e293b;">Contact Details</h2>
        {row("Name", lead.get("name"))}
        {row("Email", lead.get("email"))}
        {row("Company", lead.get("company"))}
        {row("Service interest", lead.get("service_interest"))}
        {row("Estimated budget", lead.get("budget"))}
        {row("Preferred contact method", lead.get("preferred_contact"))}
      </div>
      <div style="background:#ffffff; padding:20px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <h2 style="margin-top:0; color:#1e293b;">Requirements</h2>
        <p style="line-height:1.6; color:#475569; white-space: pre-wrap;">{lead.get("requirements")}</p>
      </div>
      {f'''<div style="background:#ffffff; padding:20px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
        <h2 style="margin-top:0; color:#1e293b;">Conversation Summary</h2>
        <p style="line-height:1.6; color:#475569; white-space: pre-wrap;">{lead.get("conversation_summary")}</p>
      </div>''' if lead.get("conversation_summary") else ""}
      <div style="padding:15px; background:#dbeafe; border-radius:8px;">
        <p style="margin:0; color:#1e40af; font-size:14px;">Source: {lead.get("source", "Website AI Chatbot")}</p>
      </div>
    </div>
    """


async def send_lead_notification(lead: dict) -> None:
    if not config.RESEND_API_KEY:
        raise EmailDeliveryError("RESEND_API_KEY is not configured")

    payload = {
        "from": config.RESEND_FROM_EMAIL,
        "to": [config.LEAD_NOTIFICATION_EMAIL],
        "subject": f"New chatbot lead: {lead.get('name')} ({lead.get('service_interest') or 'General inquiry'})",
        "html": _render_lead_email_html(lead),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise EmailDeliveryError(
                f"Resend API returned {response.status_code}: {response.text}"
            )
    except httpx.HTTPError as exc:
        raise EmailDeliveryError(f"Failed to reach Resend: {exc}") from exc
