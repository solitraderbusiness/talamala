"""Add gold_articles table for curated expert analysis articles.

Revision ID: 011
Revises: 010
Create Date: 2026-02-12
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS gold_articles (
            id SERIAL PRIMARY KEY,
            title_original VARCHAR(1024) NOT NULL,
            title_fa VARCHAR(1024),
            source_name VARCHAR(256) NOT NULL,
            source_url VARCHAR(2048) NOT NULL,
            source_logo VARCHAR(512),
            author VARCHAR(256),
            published_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            summary_fa TEXT,
            key_takeaways_fa JSONB,
            gold_outlook VARCHAR(16),
            time_horizon VARCHAR(16),
            topics JSONB,
            affected_assets JSONB,
            importance_score FLOAT,
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            original_language VARCHAR(8) DEFAULT 'en',
            word_count_original INTEGER,
            dedupe_hash VARCHAR(64) NOT NULL UNIQUE,
            partial_content BOOLEAN NOT NULL DEFAULT FALSE,
            raw_importance_score FLOAT,
            source_boost FLOAT DEFAULT 0,
            llm_processed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gold_articles_published_at
        ON gold_articles (published_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gold_articles_importance
        ON gold_articles (importance_score)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gold_articles_is_published
        ON gold_articles (is_published)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gold_articles_source_name
        ON gold_articles (source_name)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gold_articles_created_at
        ON gold_articles (created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gold_articles")
