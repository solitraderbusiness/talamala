"""Fix YouTube channel IDs and add metadata_errors column.

- Update 5 monitored_youtube_channels rows with correct channel IDs
- Update 1 live_stream_channels row (Bloomberg) with correct channel ID
- Add metadata_errors column to curated_videos (retry limiter)
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

# (old_id, new_id)
_CHANNEL_ID_UPDATES = [
    ("UCnM5WPKQE7wjFaUMT1kODiA", "UC9ijza42jVR3T6b8bColgvg"),   # Kitco NEWS
    ("UCIALMKvObZNtJ68-rmLjb5A", "UCIALMKvObZNtJ6AmdCLP7Lg"),   # Bloomberg Television
    ("UCsIhwTDCEqwGMaOc0HDqITg", "UCqvaXJ1K3HheTPNjH-KpwXQ"),   # Principles by Ray Dalio
    ("UCIjuLiLHdFxYMTR3NO0Z9Gg", "UCIjuLiLHdFxYtFmWlbTGQRQ"),   # Peter Schiff
    ("UCQMYWFsQMzbjQ4CWAmK5SXQ", "UCVgL_VeHteGecp5nn0NRztQ"),   # Stansberry Research
]


def upgrade() -> None:
    # ── Fix monitored_youtube_channels IDs ─────────────────────────────
    for old_id, new_id in _CHANNEL_ID_UPDATES:
        op.execute(
            sa.text(
                "UPDATE monitored_youtube_channels "
                "SET youtube_channel_id = :new_id "
                "WHERE youtube_channel_id = :old_id"
            ).bindparams(old_id=old_id, new_id=new_id)
        )

    # ── Fix live_stream_channels ID (Bloomberg) ────────────────────────
    op.execute(
        sa.text(
            "UPDATE live_stream_channels "
            "SET youtube_channel_id = :new_id "
            "WHERE youtube_channel_id = :old_id"
        ).bindparams(
            old_id="UCIALMKvObZNtJ68-rmLjb5A",
            new_id="UCIALMKvObZNtJ6AmdCLP7Lg",
        )
    )

    # ── Add metadata_errors column to curated_videos ───────────────────
    op.add_column(
        "curated_videos",
        sa.Column(
            "metadata_errors",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("curated_videos", "metadata_errors")

    # Revert live_stream_channels Bloomberg ID
    op.execute(
        sa.text(
            "UPDATE live_stream_channels "
            "SET youtube_channel_id = :old_id "
            "WHERE youtube_channel_id = :new_id"
        ).bindparams(
            old_id="UCIALMKvObZNtJ68-rmLjb5A",
            new_id="UCIALMKvObZNtJ6AmdCLP7Lg",
        )
    )

    # Revert monitored_youtube_channels IDs
    for old_id, new_id in _CHANNEL_ID_UPDATES:
        op.execute(
            sa.text(
                "UPDATE monitored_youtube_channels "
                "SET youtube_channel_id = :old_id "
                "WHERE youtube_channel_id = :new_id"
            ).bindparams(old_id=old_id, new_id=new_id)
        )
