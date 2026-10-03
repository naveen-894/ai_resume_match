"""Shared test fixtures.

Sets up env vars and an isolated in-memory SQLite database *before* importing
the FastAPI app, so tests never touch the real Postgres instance or make real
calls to OpenAI/Pinecone/Resend (those are mocked per-test where needed).
"""
import os

os.environ.setdefault("HOST", "localhost")
os.environ.setdefault("PORT", "5432")
os.environ.setdefault("NAME", "test_db")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("PASSWORD", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

# Deliberately low session-creation limit so test_rate_limiting can trigger a
# 429 without needing hundreds of requests; the autouse `reset_rate_limits`
# fixture below keeps this isolated between tests.
os.environ.setdefault("CHATBOT_RATE_LIMIT_SESSION", "2/minute")
os.environ.setdefault("CHATBOT_RATE_LIMIT_MESSAGE", "1000/minute")
os.environ.setdefault("CHATBOT_RATE_LIMIT_LEAD", "1000/hour")
os.environ.setdefault("CHATBOT_INTERNAL_API_KEY", "")  # unset -> internal-caller check is a no-op

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.chatbot.models import ChatLead, ChatMessage, ChatSession
from app.main import app
from app.util.db import Base, get_session

# Only the chatbot's own tables — avoids touching app/models.py's Postgres-only
# JSONB column (Conversation.match_result), which SQLite can't compile.
_CHATBOT_TABLES = [ChatSession.__table__, ChatMessage.__table__, ChatLead.__table__]

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_session():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session


@pytest_asyncio.fixture(autouse=True)
async def _fresh_schema():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_CHATBOT_TABLES)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_CHATBOT_TABLES)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Isolates slowapi's in-memory counters between tests."""
    from app.chatbot.security import limiter

    try:
        limiter._storage.reset()
    except AttributeError:
        pass
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session
