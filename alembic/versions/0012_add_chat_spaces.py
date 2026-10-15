"""add chat spaces

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15

A space is a chat-only grouping of conversations (chat_conversations.space_id,
null = unfiled) that seeds new chats created in it with its own default
characters and instruction snippets/groups. Unrelated to the generation-side
projects table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MetadataDB() creates this table / adds this column on startup too, so
    # each step is skipped if it already happened.
    insp = sa.inspect(op.get_bind())
    if "chat_spaces" not in insp.get_table_names():
        op.create_table(
            "chat_spaces",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("default_character_ids_json", sa.Text(), nullable=True),
            sa.Column("default_instruction_ids_json", sa.Text(), nullable=True),
            sa.Column("default_instruction_group_ids_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if "space_id" not in {c["name"] for c in insp.get_columns("chat_conversations")}:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("space_id", sa.Integer(), nullable=True))
        if "ix_chat_conversations_space_id" not in {i["name"] for i in insp.get_indexes("chat_conversations")}:
            op.create_index("ix_chat_conversations_space_id", "chat_conversations", ["space_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_conversations_space_id", table_name="chat_conversations")
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("space_id")
    op.drop_table("chat_spaces")
