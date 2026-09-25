"""add chat_library_items table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25

Holds chat media detached from removed messages (edit/retry), so it
stays in the chat library instead of being orphaned on disk.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() runs create_all() on startup, so skip if it already exists
    if "chat_library_items" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "chat_library_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("media_id", sa.String(50), nullable=False),
        sa.Column("conversation_id", sa.String(50),
                  sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("detached_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_library_items_media_id", "chat_library_items", ["media_id"], unique=True)
    op.create_index("ix_chat_library_items_conversation_id", "chat_library_items", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_library_items_conversation_id", table_name="chat_library_items")
    op.drop_index("ix_chat_library_items_media_id", table_name="chat_library_items")
    op.drop_table("chat_library_items")
