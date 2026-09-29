"""Allow anonymous/guest conversations

Revision ID: f3a7c9d1e5b8
Revises: a1c3e5f7b9d2
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a7c9d1e5b8'
down_revision: Union[str, None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # conversations is created by Base.metadata.create_all on app startup, so on a fresh
    # database the column/constraint state may already match what we want.
    columns = {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("conversations")}

    if columns.get("user_id", {}).get("nullable") is False:
        op.alter_column("conversations", "user_id", existing_type=sa.Integer(), nullable=True)

    if "guest_id" not in columns:
        op.add_column("conversations", sa.Column("guest_id", sa.String(), nullable=True))
        op.create_index(op.f("ix_conversations_guest_id"), "conversations", ["guest_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_conversations_guest_id"), table_name="conversations")
    op.drop_column("conversations", "guest_id")
    op.alter_column("conversations", "user_id", existing_type=sa.Integer(), nullable=False)
