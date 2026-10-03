# app/chatbot/models.py
from app.util.db import Base
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

# JSONB on Postgres, plain JSON on any other dialect (e.g. SQLite in tests) — metadata.create_all
# otherwise fails on SQLite, which has no native JSONB type.
JSONType = JSONB().with_variant(JSON(), "sqlite")


class ChatSession(Base):
    """A browser session for the website AI chatbot. No user account required —
    identified by an opaque, client-held session id (see ChatMessage.session_id)."""
    __tablename__ = "chatbot_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)

    # Where the visitor started chatting, for context only (never sent to the LLM as instructions)
    page_url = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """A single turn in a chatbot conversation."""
    __tablename__ = "chatbot_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)

    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)

    # Source chunks used to ground an assistant answer (list of {url, title} dicts), if any
    sources = Column(JSONType, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatLead(Base):
    """A qualified lead captured by the chatbot during a conversation."""
    __tablename__ = "chatbot_leads"
    __table_args__ = (UniqueConstraint("session_id", name="uq_chatbot_leads_session_id"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)

    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    company = Column(String, nullable=True)
    requirements = Column(Text, nullable=False)
    service_interest = Column(String, nullable=True)
    budget = Column(String, nullable=True)
    preferred_contact = Column(String, nullable=True)

    # Short summary of the conversation leading up to the lead, for the notification email
    conversation_summary = Column(Text, nullable=True)

    source = Column(String, nullable=False, default="Website AI Chatbot")
    notified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
