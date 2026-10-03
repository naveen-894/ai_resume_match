"""Lead capture: validates, persists, and triggers the notification email for
leads submitted by the chatbot."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot import email_service
from app.chatbot.models import ChatLead, ChatMessage
from app.chatbot.schemas import LeadSubmitRequest

logger = logging.getLogger(__name__)

SUMMARY_MAX_MESSAGES = 20
SUMMARY_MAX_CHARS = 2000


async def _build_conversation_summary(db: AsyncSession, session_id: str) -> str | None:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(SUMMARY_MAX_MESSAGES)
    )
    messages = result.scalars().all()
    if not messages:
        return None

    lines = [f"{'Visitor' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages]
    summary = "\n".join(lines)
    return summary[:SUMMARY_MAX_CHARS]


async def submit_lead(db: AsyncSession, payload: LeadSubmitRequest) -> tuple[ChatLead, bool]:
    """Returns (lead, is_new). Submitting twice for the same session_id is a
    no-op that returns the existing lead — prevents duplicate submissions and
    duplicate notification emails from a double-click or retry."""
    existing = await db.execute(
        select(ChatLead).where(ChatLead.session_id == payload.session_id)
    )
    lead = existing.scalar_one_or_none()
    if lead is not None:
        return lead, False

    summary = await _build_conversation_summary(db, payload.session_id)

    lead = ChatLead(
        session_id=payload.session_id,
        name=payload.name,
        email=payload.email,
        company=payload.company,
        requirements=payload.requirements,
        service_interest=payload.service_interest,
        budget=payload.budget,
        preferred_contact=payload.preferred_contact,
        conversation_summary=summary,
        source="Website AI Chatbot",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    try:
        await email_service.send_lead_notification(
            {
                "name": lead.name,
                "email": lead.email,
                "company": lead.company,
                "requirements": lead.requirements,
                "service_interest": lead.service_interest,
                "budget": lead.budget,
                "preferred_contact": lead.preferred_contact,
                "conversation_summary": lead.conversation_summary,
                "source": lead.source,
            }
        )
        lead.notified_at = datetime.now(timezone.utc)
        await db.commit()
    except email_service.EmailDeliveryError:
        # The lead is already safely stored; a notification failure shouldn't fail the request.
        logger.exception("Lead notification email failed for session %s", payload.session_id)

    return lead, True
