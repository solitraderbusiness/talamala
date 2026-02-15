"""Create regime_audit_logs table and add new columns to regime_scores.

New table stores one row per regime computation with full provenance:
inputs, indices, scores, probabilities, chosen regime, sources, staleness.

New columns on regime_scores: chosen_regime_raw, chosen_note_fa,
score_semantics, lookahead_safe.

Revision ID: 025
Revises: 024
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── regime_audit_logs ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS regime_audit_logs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ts              DATE NOT NULL,
            inputs_json     JSONB,
            indices_json    JSONB,
            scores_json     JSONB,
            raw_probs       JSONB,
            smoothed_probs  JSONB,
            chosen_regime   VARCHAR(16),
            chosen_regime_raw VARCHAR(16),
            chosen_note_fa  VARCHAR(256),
            sources         JSONB,
            staleness       JSONB,
            extra           JSONB
        );

        CREATE INDEX IF NOT EXISTS idx_regime_audit_ts
            ON regime_audit_logs(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_regime_audit_computed
            ON regime_audit_logs(computed_at DESC);
    """)

    # ── New columns on regime_scores ──────────────────────────────
    op.execute("""
        ALTER TABLE regime_scores
            ADD COLUMN IF NOT EXISTS chosen_regime_raw VARCHAR(16),
            ADD COLUMN IF NOT EXISTS chosen_note_fa VARCHAR(256),
            ADD COLUMN IF NOT EXISTS score_semantics VARCHAR(64),
            ADD COLUMN IF NOT EXISTS lookahead_safe BOOLEAN DEFAULT TRUE;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regime_audit_logs")
    op.execute("""
        ALTER TABLE regime_scores
            DROP COLUMN IF EXISTS chosen_regime_raw,
            DROP COLUMN IF EXISTS chosen_note_fa,
            DROP COLUMN IF EXISTS score_semantics,
            DROP COLUMN IF EXISTS lookahead_safe;
    """)
