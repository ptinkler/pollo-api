"""add hidden_defaults to chat_conversations

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-16

A chat can switch off any of its defaults (global or its space's) for itself
only: {"character" | "instruction" | "instruction_group": [ids]}, as JSON.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MetadataDB() adds this column on startup too, so skip it if it's there
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_conversations")}
    if "hidden_defaults_json" not in existing:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("hidden_defaults_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("hidden_defaults_json")
