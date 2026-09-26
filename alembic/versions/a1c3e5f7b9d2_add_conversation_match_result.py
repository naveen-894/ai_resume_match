"""Add match_result to conversations

Revision ID: a1c3e5f7b9d2
Revises: 6d7b8dfb3d1e
Create Date: 2026-09-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, None] = '6d7b8dfb3d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # conversations is created by Base.metadata.create_all on app startup, so on a fresh
    # database the column may already exist.
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("conversations")}
    if "match_result" not in columns:
        op.add_column('conversations', sa.Column('match_result', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'match_result')
