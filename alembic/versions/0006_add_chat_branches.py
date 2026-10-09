"""add chat_messages.parent_id and chat_conversations.current_leaf_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05

Chat branching: messages form a tree, so editing or retrying an earlier
turn adds a sibling branch instead of deleting what came after it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MetadataDB() adds (and backfills) these columns on startup too, so each
    # step is skipped if it already happened.
    insp = sa.inspect(op.get_bind())
    if "parent_id" not in {c["name"] for c in insp.get_columns("chat_messages")}:
        with op.batch_alter_table("chat_messages") as batch_op:
            batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        # Chats so far were linear: each message's parent is the one before it
        op.execute(
            "UPDATE chat_messages SET parent_id = (SELECT MAX(p.id) FROM chat_messages p "
            "WHERE p.conversation_id = chat_messages.conversation_id AND p.id < chat_messages.id)"
        )
    if "current_leaf_id" not in {c["name"] for c in insp.get_columns("chat_conversations")}:
        with op.batch_alter_table("chat_conversations") as batch_op:
            batch_op.add_column(sa.Column("current_leaf_id", sa.Integer(), nullable=True))
        op.execute(
            "UPDATE chat_conversations SET current_leaf_id = (SELECT MAX(m.id) "
            "FROM chat_messages m WHERE m.conversation_id = chat_conversations.id)"
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_conversations") as batch_op:
        batch_op.drop_column("current_leaf_id")
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("parent_id")
