"""media_durations cache table

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-10

A video's length is read by opening the file with OpenCV, which on a NAS costs
a fraction of a second each — enough to make listing the media library take the
best part of a minute. This table remembers what's been read, keyed by path and
the mtime it was read at. It's a cache of what's on disk, not user data, so it
isn't tenant-scoped and is safe to drop.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MetadataDB() creates missing tables on startup too, so skip it if it's there
    if not sa.inspect(op.get_bind()).has_table("media_durations"):
        op.create_table(
            "media_durations",
            sa.Column("path", sa.String(length=1024), primary_key=True),
            sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
            sa.Column("seconds", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("media_durations")
