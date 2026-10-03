# app/chatbot/schemas.py
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.chatbot import config


class ChatSessionCreate(BaseModel):
    page_url: str | None = None


class ChatSessionResponse(BaseModel):
    session_id: str
    greeting: str
    suggested_prompts: list[str]


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)

    @field_validator("message")
    @classmethod
    def message_within_limit(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > config.MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message must be at most {config.MAX_MESSAGE_LENGTH} characters")
        return v


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class LeadSubmitRequest(BaseModel):
    session_id: str
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    company: str | None = Field(None, max_length=200)
    requirements: str = Field(..., min_length=1, max_length=4000)
    service_interest: str | None = Field(None, max_length=200)
    budget: str | None = Field(None, max_length=100)
    preferred_contact: str | None = Field(None, max_length=100)
    consent: bool

    @field_validator("consent")
    @classmethod
    def consent_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required before we can submit your details")
        return v

    @field_validator("name", "requirements")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field cannot be empty")
        return v


class LeadSubmitResponse(BaseModel):
    status: str
    message: str
