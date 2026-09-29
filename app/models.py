# models.py
from app.util.db import Base
from sqlalchemy import Column, Float, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    credits = Column(Float, default=3.0)  # Free trial credits
    hashed_password = Column(String)

    conversations = relationship("Conversation", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    # relation to user (nullable: anonymous/guest conversations have no user)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="conversations")

    # opaque client-generated id identifying an anonymous guest (mutually exclusive with user_id)
    guest_id = Column(String, nullable=True, index=True)

    jd_text = Column(Text, nullable=True)
    resume_text = Column(Text, nullable=True)

    jd_file_url = Column(String, nullable=True)
    resume_file_url = Column(String, nullable=True)

    thread_id = Column(String, nullable=False)

    # Final output of the match graph, keyed by node name (same shape as the streamed chunks)
    match_result = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # auto update on UPDATE
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String, nullable=False)  # "user" or "assistant"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())