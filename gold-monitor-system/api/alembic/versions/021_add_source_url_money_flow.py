"""Add source_url column to etf_holdings and cot_data tables.

Revision ID: 021
Revises: 020
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE etf_holdings
        ADD COLUMN IF NOT EXISTS source_url VARCHAR(512);
    """)
    op.execute("""
        ALTER TABLE cot_data
        ADD COLUMN IF NOT EXISTS source_url VARCHAR(512);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE etf_holdings DROP COLUMN IF EXISTS source_url;")
    op.execute("ALTER TABLE cot_data DROP COLUMN IF EXISTS source_url;")
