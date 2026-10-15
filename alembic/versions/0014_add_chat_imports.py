"""add imported chats: their origin, and deleted imports

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-15

Chats imported from a ChatGPT export (web/chatgpt_import.py) remember their
id there and when it last changed, as do their messages, so importing a
newer export only adds what's new. Deleting one records it so it isn't
imported again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONVERSATION_COLUMNS = [
    sa.Column("import_source", sa.String(20), nullable=True),
    sa.Column("import_id", sa.String(100), nullable=True),
    sa.Column("import_updated_at", sa.Float(), nullable=True),
]
MESSAGE_COLUMNS = [sa.Column("import_id", sa.String(100), nullable=True)]


def upgrade() -> None:
    # MetadataDB() adds these on startup too, so skip what's there
    insp = sa.inspect(op.get_bind())
    for table, columns in (("chat_conversations", CONVERSATION_COLUMNS), ("chat_messages", MESSAGE_COLUMNS)):
        existing = {c["name"] for c in insp.get_columns(table)}
        with op.batch_alter_table(table) as batch_op:
            for col in columns:
                if col.name not in existing:
                    batch_op.add_column(col)
    if "ix_chat_conversations_import_id" not in {i["name"] for i in insp.get_indexes("chat_conversations")}:
        op.create_index("ix_chat_conversations_import_id", "chat_conversations", ["import_id"])
    if not insp.has_table("chat_import_skips"):
        op.create_table(
            "chat_import_skips",
            sa.Column("source", sa.String(20), primary_key=True),
            sa.Column("import_id", sa.String(100), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("chat_import_skips")
    op.drop_index("ix_chat_conversations_import_id", table_name="chat_conversations")
    with op.batch_alter_table("chat_messages") as batch_op:
        for col in reversed(MESSAGE_COLUMNS):
            batch_op.drop_column(col.name)
    with op.batch_alter_table("chat_conversations") as batch_op:
        for col in reversed(CONVERSATION_COLUMNS):
            batch_op.drop_column(col.name)
