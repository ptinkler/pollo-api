"""add branch origin, pinning and composer settings to chat_conversations

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09

A chat branched off another remembers where it came from (and what the
copied messages had cost); chats can be pinned to the top of the list; and
each chat keeps the composer settings it was last used with.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = [
    sa.Column("forked_from_id", sa.String(50), nullable=True),
    sa.Column("forked_from_message_id", sa.Integer(), nullable=True),
    sa.Column("inherited_cost", sa.Float(), nullable=True),
    sa.Column("inherited_credits", sa.Integer(), nullable=True),
    sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("settings_json", sa.Text(), nullable=True),
]


def upgrade() -> None:
    # MetadataDB() adds these columns on startup too, so skip what's there
    insp = sa.inspect(op.get_bind())
    existing = {c["name"] for c in insp.get_columns("chat_conversations")}
    with op.batch_alter_table("chat_conversations") as batch_op:
        for col in COLUMNS:
            if col.name not in existing:
                batch_op.add_column(col)
    if "ix_chat_conversations_forked_from_id" not in {i["name"] for i in insp.get_indexes("chat_conversations")}:
        op.create_index("ix_chat_conversations_forked_from_id", "chat_conversations", ["forked_from_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_conversations_forked_from_id", table_name="chat_conversations")
    with op.batch_alter_table("chat_conversations") as batch_op:
        for col in reversed(COLUMNS):
            batch_op.drop_column(col.name)
