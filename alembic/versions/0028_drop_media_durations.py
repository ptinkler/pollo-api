"""drop the leftover media_durations table

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-11

A `media_durations` table was added and then backed out: video lengths live in
their own small cache file instead (web/media_cache.py), deliberately not in
this database, so cache rows don't sit among real records. The empty table was
left behind on databases that saw the short-lived version.

Dropping it needs a write lock, which the running app holds, so it happens
here — on the next restart, with everything else.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("media_durations"):
        op.drop_table("media_durations")


def downgrade() -> None:
    # Nothing recreates it: the cache it belonged to is gone.
    pass
