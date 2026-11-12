"""add upload_prefs_json to users.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-09

Per-user source-media hosting preferences (which temp host to upload source
images/audio/video to for Pollo to fetch, the expiry, and a self-host base
URL). JSON on the users row; null means the instance default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add upload preferences to users."""
    # MetadataDB() adds this column on startup too, so skip it if it's there
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "upload_prefs_json" not in existing:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("upload_prefs_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove upload preferences from users."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("upload_prefs_json")
