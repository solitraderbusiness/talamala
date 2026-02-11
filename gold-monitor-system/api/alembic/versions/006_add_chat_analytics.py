"""Add chat_analytics table and session intent columns.

Revision ID: 006
Revises: 005
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_analytics — one row per user message
    op.create_table(
        "chat_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("intent", sa.String(50), nullable=False),
        sa.Column("topics", postgresql.JSONB, server_default="[]"),
        sa.Column("assets_mentioned", postgresql.JSONB, server_default="[]"),
        sa.Column("had_answer", sa.Boolean, server_default="true"),
        sa.Column("missing_feature", sa.Text, nullable=True),
        sa.Column("suggested_followups", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_chat_analytics_intent", "chat_analytics", ["intent"])
    op.create_index("idx_chat_analytics_created", "chat_analytics", ["created_at"])
    op.create_index("idx_chat_analytics_had_answer", "chat_analytics", ["had_answer"])
    op.create_index(
        "idx_chat_analytics_intent_date", "chat_analytics", ["intent", "created_at"]
    )
    op.create_index("idx_chat_analytics_session", "chat_analytics", ["session_id"])

    # Add columns to chat_sessions
    op.add_column(
        "chat_sessions",
        sa.Column("primary_intent", sa.String(50), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("had_answer_rate", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "had_answer_rate")
    op.drop_column("chat_sessions", "primary_intent")
    op.drop_table("chat_analytics")
