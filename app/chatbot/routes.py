# app/chatbot/routes.py
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot import config, lead_service, orchestrator, security
from app.chatbot.models import ChatMessage, ChatSession
from app.chatbot.schemas import (
    ChatMessageRequest,
    ChatSessionCreate,
    ChatSessionResponse,
    LeadSubmitRequest,
    LeadSubmitResponse,
)
from app.util.db import get_session

router = APIRouter(
    prefix="/chatbot",
    tags=["Chatbot"],
    dependencies=[Depends(security.verify_internal_caller), Depends(security.enforce_max_body_size)],
)
logger = logging.getLogger(__name__)


@router.post("/session", response_model=ChatSessionResponse)
@security.limiter.limit(config.RATE_LIMIT_SESSION)
async def create_session(
    request: Request,
    payload: ChatSessionCreate,
    db: AsyncSession = Depends(get_session),
):
    if not config.CHATBOT_ENABLED:
        raise HTTPException(status_code=503, detail="Chat assistant is currently disabled")

    session_id = str(uuid.uuid4())
    db.add(ChatSession(session_id=session_id, page_url=payload.page_url))
    await db.commit()

    return ChatSessionResponse(
        session_id=session_id,
        greeting=config.GREETING_MESSAGE,
        suggested_prompts=config.SUGGESTED_PROMPTS,
    )


@router.delete("/session/{session_id}")
@security.limiter.limit(config.RATE_LIMIT_SESSION)
async def reset_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Clears message history for a session (conversation reset). The session
    row itself is kept so the id stays valid for the rest of the browser tab's life."""
    result = await db.execute(select(ChatSession).where(ChatSession.session_id == session_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.commit()
    return {"status": "reset"}


async def _load_history(db: AsyncSession, session_id: str) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(config.MAX_HISTORY_MESSAGES)
    )
    rows = result.scalars().all()[::-1]
    return [{"role": m.role, "content": m.content} for m in rows]


@router.post("/message")
@security.limiter.limit(config.RATE_LIMIT_MESSAGE)
async def send_message(
    request: Request,
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_session),
):
    if not config.CHATBOT_ENABLED:
        raise HTTPException(status_code=503, detail="Chat assistant is currently disabled")

    result = await db.execute(
        select(ChatSession).where(ChatSession.session_id == payload.session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id — create a session first")

    clean_message = security.sanitize_text(payload.message)
    history = await _load_history(db, payload.session_id)

    db.add(ChatMessage(session_id=payload.session_id, role="user", content=clean_message))
    await db.commit()

    async def event_stream():
        tokens: list[str] = []
        sources: list[dict] = []
        try:
            async for event in orchestrator.handle_message(history, clean_message):
                if event["type"] == "sources":
                    sources = event["sources"]
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
                elif event["type"] == "token":
                    tokens.append(event["content"])
                    yield f"data: {json.dumps({'type': 'token', 'content': event['content']})}\n\n"
        except Exception:
            logger.exception("Chatbot turn failed for session %s", payload.session_id)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Something went wrong. Please try again.'})}\n\n"
            return

        answer = "".join(tokens).strip()
        if answer:
            db.add(
                ChatMessage(
                    session_id=payload.session_id,
                    role="assistant",
                    content=answer,
                    sources=sources or None,
                )
            )
            await db.commit()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/lead", response_model=LeadSubmitResponse)
@security.limiter.limit(config.RATE_LIMIT_LEAD)
async def submit_lead(
    request: Request,
    payload: LeadSubmitRequest,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.session_id == payload.session_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Unknown session_id — create a session first")

    lead, is_new = await lead_service.submit_lead(db, payload)

    if is_new:
        message = (
            f"Thanks, {lead.name} — we've received your details and the "
            f"{config.COMPANY_NAME} team will reach out to you at {lead.email} shortly."
        )
    else:
        message = "We already have your details on file for this conversation — our team will be in touch."

    return LeadSubmitResponse(status="ok", message=message)
