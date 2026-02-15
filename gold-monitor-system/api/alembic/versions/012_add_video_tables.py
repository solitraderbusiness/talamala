"""Add video tables for curated YouTube videos module.

Revision ID: 012
Revises: 011
Create Date: 2026-02-12
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS curated_videos (
            id SERIAL PRIMARY KEY,
            youtube_id VARCHAR(20) NOT NULL UNIQUE,
            title_original VARCHAR(1024),
            title_fa VARCHAR(1024),
            channel_name VARCHAR(256),
            channel_id VARCHAR(64),
            thumbnail_url VARCHAR(512),
            duration_seconds INTEGER,
            view_count INTEGER,
            published_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            transcript TEXT,
            summary_fa TEXT,
            key_points_fa JSONB,
            topics JSONB,
            category VARCHAR(32),
            gold_outlook VARCHAR(16),
            relevance_score FLOAT,
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            llm_processed BOOLEAN NOT NULL DEFAULT FALSE,
            added_by VARCHAR(16) DEFAULT 'auto',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_curated_videos_published_at
        ON curated_videos (published_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_curated_videos_is_published
        ON curated_videos (is_published)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_curated_videos_category
        ON curated_videos (category)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_curated_videos_relevance
        ON curated_videos (relevance_score)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_curated_videos_created_at
        ON curated_videos (created_at)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS live_stream_channels (
            id SERIAL PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            name_fa VARCHAR(256),
            youtube_channel_id VARCHAR(64) NOT NULL UNIQUE,
            thumbnail_url VARCHAR(512),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS monitored_youtube_channels (
            id SERIAL PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            youtube_channel_id VARCHAR(64) NOT NULL UNIQUE,
            rss_url VARCHAR(512),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            auto_publish BOOLEAN NOT NULL DEFAULT FALSE,
            always_relevant BOOLEAN NOT NULL DEFAULT FALSE,
            min_duration_seconds INTEGER DEFAULT 120,
            max_age_days INTEGER DEFAULT 14,
            last_checked_at TIMESTAMPTZ,
            last_video_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS video_chat_logs (
            id SERIAL PRIMARY KEY,
            video_id INTEGER NOT NULL,
            ip_address VARCHAR(45),
            question TEXT NOT NULL,
            answer TEXT,
            tokens_used INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_video_chat_logs_video_id
        ON video_chat_logs (video_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_video_chat_logs_created_at
        ON video_chat_logs (created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS video_chat_logs")
    op.execute("DROP TABLE IF EXISTS monitored_youtube_channels")
    op.execute("DROP TABLE IF EXISTS live_stream_channels")
    op.execute("DROP TABLE IF EXISTS curated_videos")
