"""add title_model to chat_settings.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-09

The text model a user picks to name new chats (null = the chat's own model).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a title model to chat settings."""
    # MetadataDB() adds this column on startup too, so skip it if it's there
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_settings")}
    if "title_model" not in existing:
        with op.batch_alter_table("chat_settings") as batch_op:
            batch_op.add_column(sa.Column("title_model", sa.String(200), nullable=True))


def downgrade() -> None:
    """Remove the title model from chat settings."""
    with op.batch_alter_table("chat_settings") as batch_op:
        batch_op.drop_column("title_model")
