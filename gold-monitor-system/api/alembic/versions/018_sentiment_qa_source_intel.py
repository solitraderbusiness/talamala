"""Add tables for Source Intelligence + Sentiment QA.

New tables:
- source_tags: coverage bucket tags per source
- sentiment_labels: human-labeled gold set for QA
- sentiment_reference_scores: LLM cross-check results
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── source_tags ───────────────────────────────────────────────────
    op.create_table(
        "source_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("tag", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", "tag", name="uq_source_tags_source_tag"),
    )
    op.create_index("ix_source_tags_tag", "source_tags", ["tag"])
    op.create_index("ix_source_tags_source_id", "source_tags", ["source_id"])

    # ── sentiment_labels ──────────────────────────────────────────────
    op.create_table(
        "sentiment_labels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id", UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("direction_label", sa.String(10), nullable=False),
        sa.Column("intensity", sa.Integer, nullable=False),
        sa.Column("relevance", sa.Integer, nullable=False),
        sa.Column("system_direction", sa.String(20)),
        sa.Column("system_alert_score", sa.Integer),
        sa.Column("system_confidence", sa.Float),
        sa.Column("labeler", sa.String(50), server_default="admin"),
        sa.Column("labeled_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("notes", sa.Text),
        sa.CheckConstraint("intensity BETWEEN 1 AND 5", name="ck_sentiment_labels_intensity"),
        sa.CheckConstraint("relevance BETWEEN 1 AND 5", name="ck_sentiment_labels_relevance"),
        sa.CheckConstraint(
            "direction_label IN ('positive', 'negative', 'neutral')",
            name="ck_sentiment_labels_direction",
        ),
    )
    op.create_index("ix_sentiment_labels_labeled_at", "sentiment_labels", ["labeled_at"])
    op.create_index("ix_sentiment_labels_alert_id", "sentiment_labels", ["alert_id"])

    # ── sentiment_reference_scores ────────────────────────────────────
    op.create_table(
        "sentiment_reference_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id", UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("system_direction", sa.String(20)),
        sa.Column("system_score", sa.Integer),
        sa.Column("system_method", sa.String(20)),
        sa.Column("ref_direction", sa.String(20)),
        sa.Column("ref_intensity", sa.Integer),
        sa.Column("ref_confidence", sa.Float),
        sa.Column("ref_model", sa.String(100)),
        sa.Column("ref_reasoning", sa.Text),
        sa.Column("direction_agrees", sa.Boolean),
        sa.Column("trace_id", sa.String(50)),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_ref_scores_scored_at", "sentiment_reference_scores", ["scored_at"])
    op.create_index("ix_ref_scores_alert_id", "sentiment_reference_scores", ["alert_id"])
    op.create_index(
        "ix_ref_scores_disagree", "sentiment_reference_scores",
        ["direction_agrees"],
        postgresql_where=sa.text("direction_agrees = false"),
    )


def downgrade() -> None:
    op.drop_table("sentiment_reference_scores")
    op.drop_table("sentiment_labels")
    op.drop_table("source_tags")
