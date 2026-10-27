"""add paused_instructions to chat_conversations

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26

A chat can pause attached instruction snippets/groups (its own or inherited
defaults): they stay attached but aren't sent to the model until resumed.
{"instruction" | "instruction_group": [ids]}, as JSON.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MetadataDB() adds this column on startup too, so skip it if it's there
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("chat_conversations")}
    if "paused_instructions_json" not in existing:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("paused_instructions_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("paused_instructions_json")
