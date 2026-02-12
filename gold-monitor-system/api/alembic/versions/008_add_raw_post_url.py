"""Add url column to raw_posts table.

Revision ID: 008
Revises: 007
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw_posts ADD COLUMN IF NOT EXISTS url VARCHAR(2048)")


def downgrade() -> None:
    op.drop_column("raw_posts", "url")
