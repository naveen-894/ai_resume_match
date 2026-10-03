"""Add website AI chatbot tables (sessions, messages, leads)

Revision ID: c8f1a4b9d3e7
Revises: f3a7c9d1e5b8
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c8f1a4b9d3e7'
down_revision: Union[str, None] = 'f3a7c9d1e5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "chatbot_sessions" not in existing_tables:
        op.create_table(
            "chatbot_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("page_url", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(op.f("ix_chatbot_sessions_id"), "chatbot_sessions", ["id"])
        op.create_index(
            op.f("ix_chatbot_sessions_session_id"), "chatbot_sessions", ["session_id"], unique=True
        )

    if "chatbot_messages" not in existing_tables:
        op.create_table(
            "chatbot_messages",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("sources", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(op.f("ix_chatbot_messages_id"), "chatbot_messages", ["id"])
        op.create_index(
            op.f("ix_chatbot_messages_session_id"), "chatbot_messages", ["session_id"]
        )

    if "chatbot_leads" not in existing_tables:
        op.create_table(
            "chatbot_leads",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("company", sa.String(), nullable=True),
            sa.Column("requirements", sa.Text(), nullable=False),
            sa.Column("service_interest", sa.String(), nullable=True),
            sa.Column("budget", sa.String(), nullable=True),
            sa.Column("preferred_contact", sa.String(), nullable=True),
            sa.Column("conversation_summary", sa.Text(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="Website AI Chatbot"),
            sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("session_id", name="uq_chatbot_leads_session_id"),
        )
        op.create_index(op.f("ix_chatbot_leads_id"), "chatbot_leads", ["id"])
        op.create_index(op.f("ix_chatbot_leads_session_id"), "chatbot_leads", ["session_id"])
        op.create_index(op.f("ix_chatbot_leads_email"), "chatbot_leads", ["email"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_chatbot_leads_email"), table_name="chatbot_leads")
    op.drop_index(op.f("ix_chatbot_leads_session_id"), table_name="chatbot_leads")
    op.drop_index(op.f("ix_chatbot_leads_id"), table_name="chatbot_leads")
    op.drop_table("chatbot_leads")

    op.drop_index(op.f("ix_chatbot_messages_session_id"), table_name="chatbot_messages")
    op.drop_index(op.f("ix_chatbot_messages_id"), table_name="chatbot_messages")
    op.drop_table("chatbot_messages")

    op.drop_index(op.f("ix_chatbot_sessions_session_id"), table_name="chatbot_sessions")
    op.drop_index(op.f("ix_chatbot_sessions_id"), table_name="chatbot_sessions")
    op.drop_table("chatbot_sessions")
