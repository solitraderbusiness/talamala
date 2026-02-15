"""Add session_type column to chat_sessions for workbench sessions."""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("session_type", sa.String(20), server_default="chat", nullable=False),
    )
    op.create_index("ix_chat_sessions_type", "chat_sessions", ["session_type"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_type", table_name="chat_sessions")
    op.drop_column("chat_sessions", "session_type")
